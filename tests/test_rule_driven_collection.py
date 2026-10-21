# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-257: a gated fact family is collected only for a contract whose rule uses it."""

import json
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_catalog_policy_native import _argument, _raw, _use
from test_exact_module_ownership import _component, _rule

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.python.collect import collect
from archkeel.check.observe import Observer
from archkeel.check.ports import Language, ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import analyze_snapshot, observer_for
from archkeel.ir.codec import parse_contract
from archkeel.ir.collection_features import required_resolution_features
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.diagnostics import DiagnosticKind
from archkeel.ir.facts import (
    BASE_RESOLUTION_FEATURES,
    CONSTRUCT_SELECTORS_FEATURE,
    GATED_RESOLUTION_FEATURES,
    GUARDED_EFFECTS_FEATURE,
    RULE_FAMILY_NOT_COLLECTED_KIND,
    SOURCE_ROLES_FEATURE,
    SourceFacts,
    SourceSectionName,
)
from archkeel.ir.facts_codec import (
    ProtocolError,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
    collected_resolution_features,
)

ROOT = Path(__file__).parents[1]
FILES = {
    "sample/__init__.py": "",
    "sample/core.py": (
        "retired_cursor = 0\n\n\n"
        "class Connection:\n"
        "    backend: str\n\n\n"
        "def _effect():\n"
        "    return None\n\n\n"
        "def run(conn: Connection, seeded: bool, name=None):\n"
        '    local = name or "x"\n'
        "    if seeded:\n"
        "        _effect()\n"
        '    flat = conn.backend == "flat"\n'
        "    if flat:\n"
        "        return retired_cursor\n"
        "    return local\n"
    ),
}
RULES = {
    SOURCE_ROLES_FEATURE: _rule(
        "source_ownership",
        id="OWN",
        source="sample.core",
        mode="retired",
        symbols=["sample.core.retired_cursor"],
        roles=["definition", "read"],
    ),
    CONSTRUCT_SELECTORS_FEATURE: _rule(
        "forbidden_construct",
        id="SEL",
        source="sample",
        constructs=["string_literal_compare"],
        selector={
            "receiver": "sample.core.Connection",
            "member": "backend",
            "role": "equality",
            "literal": "flat",
        },
    ),
    GUARDED_EFFECTS_FEATURE: _rule(
        "forbidden_effect_under_condition",
        id="GUARD",
        source="sample.core",
        target="sample.core._effect",
        condition={"kind": "parameter", "owner": "sample.core.run", "name": "seeded"},
    ),
}


def _contract(*families: str, mounted: bool = False) -> dict[str, object]:
    rules = [RULES[family] for family in families]
    component = _component("all", ["sample"])
    if mounted:
        return {
            "schema_version": "3.14.0",
            "components": [{**component, "inside": "inside.json"}],
            "rules": [],
        }
    return {"schema_version": "3.14.0", "components": [component], "rules": rules}


def _write_tree(root: Path, contract: dict[str, object], *families: str, mounted: bool) -> None:
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Decision.\n",
        "contract.json": json.dumps(contract),
        **FILES,
    }
    if mounted:
        inside = {
            "schema_version": "3.14.0",
            "components": [],
            "rules": [RULES[family] for family in families],
        }
        files["inside.json"] = json.dumps(inside)
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)


@dataclass
class _Recording:
    """Keeps the facts the real provider collector returned for one observation."""

    inner: object
    drop_features: bool = False
    facts: list[SourceFacts] = field(default_factory=list)

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        if self.drop_features and isinstance(request.resolver, PythonSettings):
            request = replace(request, resolver=replace(request.resolver, features=()))
        result = self.inner.collect(request)  # type: ignore[attr-defined]
        if isinstance(result, SourceFacts):
            self.facts.append(result)
        return result


def _observe(root: Path, *, drop_features: bool = False):
    recording = _Recording(observer_for(Language.PYTHON).collector, drop_features)
    result = Observer(recording)(
        root,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    [facts] = recording.facts
    return result, facts


def _records(facts: SourceFacts, name: SourceSectionName):
    return next(section.records for section in facts.sections if section.name is name)


def _present(facts: SourceFacts) -> frozenset[str]:
    """The gated families whose records actually appear in the collected facts."""
    references = _records(facts, SourceSectionName.REFERENCES)
    found: set[str] = set()
    if any(
        item.kind == "source_role" or item.data.get("local_source_binding") is True
        for item in references
    ):
        found.add(SOURCE_ROLES_FEATURE)
    if any(
        item.kind == "construct_selector" for item in _records(facts, SourceSectionName.CONSTRUCTS)
    ):
        found.add(CONSTRUCT_SELECTORS_FEATURE)
    if any(item.data.get("guarded_effect") for item in _records(facts, SourceSectionName.CALLS)):
        found.add(GUARDED_EFFECTS_FEATURE)
    return frozenset(found)


def _declared_in_order(*families: str) -> tuple[str, ...]:
    return (
        *BASE_RESOLUTION_FEATURES,
        *(feature for feature in GATED_RESOLUTION_FEATURES if feature in families),
    )


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("families", [(), *((family,) for family in RULES)])
def test_only_the_families_a_declared_rule_uses_are_collected(tmp_path, families, mounted):
    _write_tree(tmp_path, _contract(*families, mounted=mounted), *families, mounted=mounted)

    result, facts = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert facts.capabilities.resolution_features == _declared_in_order(*families)
    assert _present(facts) == frozenset(families)
    # The base facts the report reads stay collected whatever the contract declares.
    assert _records(facts, SourceSectionName.CALLS)
    assert any(
        item.kind == "value_reference" for item in _records(facts, SourceSectionName.REFERENCES)
    )
    assert all(
        failure.kind != RULE_FAMILY_NOT_COLLECTED_KIND
        for failure in result.observation.coverage.failures
    )
    for row in rule_assessments(result.observation, undecided_by_rule={}):
        assert row.status == "FAIL" and row.evaluation_proven


def test_the_witness_stays_while_extended_call_bindings_are_always_collected(tmp_path):
    # Constructed-receiver proofs of the always-collected extended bindings replay this witness.
    _write_tree(tmp_path, _contract(), mounted=False)

    _, facts = _observe(tmp_path)

    [connection] = [
        item
        for item in _records(facts, SourceSectionName.SYMBOLS)
        if item.data.get("qualified_name") == "sample.core.Connection"
    ]
    assert isinstance(connection.data.get("instance_member_scope_evidence_id"), str)


@pytest.mark.parametrize("version", [ProtocolVersion.V3, ProtocolVersion.V6])
def test_protocols_before_7_collect_every_family(tmp_path, version):
    _write_tree(tmp_path, _contract(), mounted=False)
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("sample",), "sample"),
        PythonSettings(),
        version,
    )

    facts = collect(request)

    assert facts.capabilities.resolution_features == _declared_in_order(*GATED_RESOLUTION_FEATURES)
    assert _present(facts) == frozenset(GATED_RESOLUTION_FEATURES)


@pytest.mark.parametrize("family", list(RULES))
def test_a_rule_whose_family_was_not_collected_is_a_coverage_failure_never_a_pass(tmp_path, family):
    _write_tree(tmp_path, _contract(family), family, mounted=False)
    for command in (
        ("init", "-q"),
        ("config", "user.email", "arch@example.invalid"),
        ("config", "user.name", "Archkeel test"),
        ("add", "."),
        ("commit", "-q", "-m", "tree"),
    ):
        subprocess.run(["git", *command], cwd=tmp_path, check=True, capture_output=True)
    recording = _Recording(observer_for(Language.PYTHON).collector, drop_features=True)

    result, encoded = run_report(
        tmp_path,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=Observer(recording),
    )

    [facts] = recording.facts
    assert not _present(facts)
    assert result.exit_code == 2
    [failure] = [
        item
        for item in result.diagnostics
        if item.kind is DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE
    ]
    assert failure.subject == RULES[family]["id"]
    assert result.observation_complete == "UNKNOWN"
    assert encoded is not None
    saved = tmp_path / "saved-report.json"
    saved.write_bytes(encoded)
    replay = run_saved_report(saved)
    assert replay.exit_code == 2
    assert [(item.kind, item.subject) for item in replay.diagnostics] == [
        (item.kind, item.subject) for item in result.diagnostics
    ]


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("family", list(RULES))
def test_uncollected_rule_gets_no_receipt_and_no_violation(tmp_path, family, mounted):
    _write_tree(tmp_path, _contract(family, mounted=mounted), family, mounted=mounted)

    result, facts = _observe(tmp_path, drop_features=True)

    assert not _present(facts)
    observation = result.observation
    assert observation is not None
    [failure] = [
        item
        for item in observation.coverage.failures
        if item.kind == RULE_FAMILY_NOT_COLLECTED_KIND
    ]
    assert [item.rpartition(":")[2] for item in failure.rule_ids] == [RULES[family]["id"]]
    assert dict(failure.data.entries)["families"] == (family,)
    assert not observation.records("violations")
    assert not [
        item
        for item in observation.records("scope_observations") or ()
        if item.kind == "rule_evaluation"
        and RULES[family]["id"] in [rule.rpartition(":")[2] for rule in item.rule_ids]
    ]
    [row] = rule_assessments(observation, undecided_by_rule={})
    assert row.status != "PASS" and not row.evaluation_proven
    assert any(
        item.kind is DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE for item in result.diagnostics
    )


@pytest.mark.parametrize("family", list(RULES))
def test_snapshot_analysis_requests_the_families_its_own_contract_declares(tmp_path, family):
    _write_tree(tmp_path, _contract(family), family, mounted=False)

    payload, _ = analyze_snapshot(
        tmp_path,
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )

    assert not [
        item
        for item in payload["coverage"]["failures"]  # type: ignore[index, union-attr]
        if item["kind"] == RULE_FAMILY_NOT_COLLECTED_KIND  # type: ignore[index]
    ]
    assert payload["violations"]


def test_unrelated_rules_keep_their_results_beside_an_uncollected_rule(tmp_path):
    contract = _contract(SOURCE_ROLES_FEATURE, GUARDED_EFFECTS_FEATURE)
    _write_tree(tmp_path, contract, SOURCE_ROLES_FEATURE, GUARDED_EFFECTS_FEATURE, mounted=False)
    recording = _Recording(observer_for(Language.PYTHON).collector)
    request_features: list[tuple[str, ...]] = []

    class _OnlyGuarded:
        def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
            assert isinstance(request.resolver, PythonSettings)
            request_features.append(request.resolver.features)
            kept = replace(request.resolver, features=(GUARDED_EFFECTS_FEATURE,))
            return recording.collect(replace(request, resolver=kept))

    result = Observer(_OnlyGuarded())(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )

    assert request_features == [(GUARDED_EFFECTS_FEATURE, SOURCE_ROLES_FEATURE)]
    assert result.observation is not None
    states = {
        row.id: (row.status, row.evaluation_proven)
        for row in rule_assessments(result.observation, undecided_by_rule={})
    }
    assert states["GUARD"][0] == "FAIL"
    assert states["OWN"] == ("UNKNOWN", False)


def test_required_features_follow_the_rule_kinds_including_mounted_rules():
    def parsed(*rules: dict[str, object]):
        return parse_contract(_raw(*rules))

    assert required_resolution_features(parsed(_argument())) == {SOURCE_ROLES_FEATURE}
    assert required_resolution_features(parsed(_use())) == {SOURCE_ROLES_FEATURE}
    selector_less = _rule(
        "forbidden_construct", id="PLAIN", source="sample", constructs=["broad_except"]
    )
    plain = parse_contract({"schema_version": "3.14.0", "components": [], "rules": [selector_less]})
    assert required_resolution_features(plain) == frozenset()
    every = parse_contract(
        {"schema_version": "3.14.0", "components": [], "rules": list(RULES.values())}
    )
    assert required_resolution_features(every) == frozenset(GATED_RESOLUTION_FEATURES)


def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads((ROOT / "schema/source-facts.schema.json").read_bytes()))


def _request(*features: str, version=ProtocolVersion.V7, root="/source-project"):
    return CollectionRequest(
        SnapshotInput(root, "a" * 40, False),
        SourceScope(("sample",), "sample"),
        PythonSettings(features=tuple(features)),
        version,
    )


def test_v7_request_carries_sorted_features_and_round_trips():
    request = _request(CONSTRUCT_SELECTORS_FEATURE, SOURCE_ROLES_FEATURE)

    encoded = encode_request(request)

    assert json.loads(encoded)["resolver"]["features"] == [
        CONSTRUCT_SELECTORS_FEATURE,
        SOURCE_ROLES_FEATURE,
    ]
    _schema_validator().validate(json.loads(encoded))
    assert decode_request(encoded) == request


def test_v7_request_without_features_is_valid_and_means_base_only():
    encoded = encode_request(_request())

    assert json.loads(encoded)["resolver"]["features"] == []
    _schema_validator().validate(json.loads(encoded))
    assert decode_request(encoded).resolver == PythonSettings()


@pytest.mark.parametrize(
    "features",
    [
        [SOURCE_ROLES_FEATURE, SOURCE_ROLES_FEATURE],
        [SOURCE_ROLES_FEATURE, CONSTRUCT_SELECTORS_FEATURE],
        ["call_arguments"],
        ["unknown_family"],
        [1],
    ],
)
def test_v7_request_rejects_unsorted_duplicate_or_unknown_features(features):
    payload = json.loads(encode_request(_request()))
    payload["resolver"]["features"] = features

    with pytest.raises(ProtocolError):
        decode_request(json.dumps(payload).encode())


@pytest.mark.parametrize("version", [ProtocolVersion.V3, ProtocolVersion.V6])
def test_older_requests_carry_no_features_on_the_wire(version):
    request = _request(SOURCE_ROLES_FEATURE, version=version)

    encoded = encode_request(request)

    assert "features" not in json.loads(encoded)["resolver"]
    assert encoded == encode_request(replace(request, resolver=PythonSettings()))
    payload = json.loads(encoded)
    payload["resolver"]["features"] = []
    with pytest.raises(ProtocolError):
        decode_request(json.dumps(payload).encode())


def test_v7_response_round_trips_what_the_collector_declared(tmp_path):
    _write_tree(tmp_path, _contract(), mounted=False)
    request = _request(SOURCE_ROLES_FEATURE, root=str(tmp_path))

    facts = collect(request)
    response = CollectionResponse(facts, ProtocolVersion.V7)
    encoded = encode_response(response)

    assert facts.capabilities.resolution_features == collected_resolution_features(
        ProtocolVersion.V7, request.resolver.features
    )
    _schema_validator().validate(json.loads(encoded))
    assert decode_response(encoded) == response


@pytest.mark.parametrize("family", [SOURCE_ROLES_FEATURE, CONSTRUCT_SELECTORS_FEATURE])
def test_records_of_an_undeclared_family_are_rejected(tmp_path, family):
    _write_tree(tmp_path, _contract(), mounted=False)
    facts = collect(_request(family, root=str(tmp_path)))
    undeclared = replace(
        facts,
        capabilities=replace(
            facts.capabilities,
            resolution_features=tuple(
                item for item in facts.capabilities.resolution_features if item != family
            ),
        ),
    )

    with pytest.raises(ProtocolError, match="require their declared capability"):
        encode_response(CollectionResponse(undeclared, ProtocolVersion.V7))


def test_response_features_that_differ_from_the_request_are_a_protocol_error(tmp_path):
    _write_tree(tmp_path, _contract(), mounted=False)
    request = _request(root=str(tmp_path))
    facts = collect(request)
    extra = replace(
        facts,
        capabilities=replace(
            facts.capabilities,
            resolution_features=(*facts.capabilities.resolution_features, SOURCE_ROLES_FEATURE),
        ),
    )
    payload = encode_response(CollectionResponse(extra, ProtocolVersion.V7)).decode()
    script = f"import sys\nsys.stdin.read()\nprint({payload!r})\n"

    result = ProcessCollector((sys.executable, "-B", "-c", script)).collect(request)

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "resolution features disagree" in result.message

    honest = encode_response(CollectionResponse(facts, ProtocolVersion.V7)).decode()
    script = f"import sys\nsys.stdin.read()\nprint({honest!r})\n"
    assert isinstance(
        ProcessCollector((sys.executable, "-B", "-c", script)).collect(request), SourceFacts
    )
