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
from archkeel.ir.codec import observation_payload, parse_contract, parse_observation
from archkeel.ir.collection_features import required_resolution_features
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.diagnostics import DiagnosticKind
from archkeel.ir.facts import (
    BASE_RESOLUTION_FEATURES,
    CALL_ARGUMENTS_FEATURE,
    CONSTRUCT_SELECTORS_FEATURE,
    EXTENDED_CALL_BINDING_ORIGINS,
    EXTENDED_CALL_BINDINGS_FEATURE,
    GATED_RESOLUTION_FEATURES,
    GUARDED_EFFECTS_FEATURE,
    NUMERIC_OPERANDS_FEATURE,
    RULE_FAMILY_NOT_COLLECTED_KIND,
    SOURCE_ROLES_FEATURE,
    SourceFacts,
    SourceSectionName,
    call_binding,
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
    "sample/store.py": (
        "class Store:\n"
        "    def page(self):\n"
        "        return None\n\n\n"
        "def fetch(query: str) -> None:\n"
        "    return None\n"
    ),
    "sample/core.py": (
        "from .store import Store, fetch\n\n"
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
        "    Store().page()\n"
        '    fetch("select 1")\n'
        "    if flat:\n"
        "        return retired_cursor\n"
        "    return local\n\n\n"
        "def slot(nonce: int) -> int:\n"
        "    return nonce % 3\n"
    ),
}
RULES = {
    "ownership": _rule(
        "source_ownership",
        id="OWN",
        source="sample.core",
        mode="retired",
        symbols=["sample.core.retired_cursor"],
        roles=["definition", "read"],
    ),
    "selector": _rule(
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
    "guarded": _rule(
        "forbidden_effect_under_condition",
        id="GUARD",
        source="sample.core",
        target="sample.core._effect",
        condition={"kind": "parameter", "owner": "sample.core.run", "name": "seeded"},
    ),
    "call_owner": _rule(
        "call_owner",
        id="OWNER",
        source="sample",
        target="sample.store.Store.page",
        allowed_sources=[],
        exact_sources=[],
    ),
    "call_argument": _rule(
        "forbidden_call_argument",
        id="ARG",
        source="sample.core",
        target="sample.store.fetch",
        parameter="query",
    ),
    "numeric": _rule(
        "bounded_numeric_operand",
        id="NUM",
        source="sample.core",
        form="both",
        terminal_suffix="nonce",
        minimum_value=4,
    ),
}
# The independent oracle: the families each rule needs, written out and not derived.
NEEDS = {
    "ownership": frozenset({SOURCE_ROLES_FEATURE}),
    "selector": frozenset({CONSTRUCT_SELECTORS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE}),
    "guarded": frozenset(
        {GUARDED_EFFECTS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE, CALL_ARGUMENTS_FEATURE}
    ),
    "call_owner": frozenset({EXTENDED_CALL_BINDINGS_FEATURE}),
    "call_argument": frozenset({CALL_ARGUMENTS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE}),
    "numeric": frozenset({NUMERIC_OPERANDS_FEATURE}),
}


def _contract(*names: str, mounted: bool = False) -> dict[str, object]:
    rules = [RULES[name] for name in names]
    component = _component("all", ["sample"])
    if mounted:
        return {
            "schema_version": "3.14.0",
            "components": [{**component, "inside": "inside.json"}],
            "rules": [],
        }
    return {"schema_version": "3.14.0", "components": [component], "rules": rules}


def _write_tree(root: Path, contract: dict[str, object], *names: str, mounted: bool) -> None:
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
            "rules": [RULES[name] for name in names],
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
    calls = _records(facts, SourceSectionName.CALLS)
    constructs = _records(facts, SourceSectionName.CONSTRUCTS)
    found: set[str] = set()
    if any(
        item.kind == "source_role" or item.data.get("local_source_binding") is True
        for item in references
    ):
        found.add(SOURCE_ROLES_FEATURE)
    if any(item.kind == "construct_selector" for item in constructs):
        found.add(CONSTRUCT_SELECTORS_FEATURE)
    if any(item.data.get("guarded_effect") for item in calls):
        found.add(GUARDED_EFFECTS_FEATURE)
    if any(
        (binding := call_binding(item.data.get("call_binding"))) is not None
        and binding.origin in EXTENDED_CALL_BINDING_ORIGINS
        for item in calls
    ):
        found.add(EXTENDED_CALL_BINDINGS_FEATURE)
    if any(item.data.get("call_arguments") is not None for item in calls):
        found.add(CALL_ARGUMENTS_FEATURE)
    if any(item.kind == "numeric_operand" for item in constructs):
        found.add(NUMERIC_OPERANDS_FEATURE)
    return frozenset(found)


def _witnesses(facts: SourceFacts) -> list[str]:
    """The class-body evidence ids that constructed-receiver proofs replay."""
    ids = (
        item.data.get("instance_member_scope_evidence_id")
        for item in _records(facts, SourceSectionName.SYMBOLS)
    )
    return [identifier for identifier in ids if isinstance(identifier, str)]


def _declared_in_order(*families: str) -> tuple[str, ...]:
    return (
        *BASE_RESOLUTION_FEATURES,
        *(feature for feature in GATED_RESOLUTION_FEATURES if feature in families),
    )


def _needs(*names: str) -> frozenset[str]:
    return frozenset().union(*(NEEDS[name] for name in names))


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("names", [(), *((name,) for name in RULES)])
def test_only_the_families_a_declared_rule_uses_are_collected(tmp_path, names, mounted):
    _write_tree(tmp_path, _contract(*names, mounted=mounted), *names, mounted=mounted)

    result, facts = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert facts.capabilities.resolution_features == _declared_in_order(*_needs(*names))
    assert _present(facts) == _needs(*names)
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


@pytest.mark.parametrize("name", [None, *RULES])
def test_member_write_witnesses_follow_extended_bindings_and_selectors(tmp_path, name):
    names = () if name is None else (name,)
    _write_tree(tmp_path, _contract(*names), *names, mounted=False)

    _, facts = _observe(tmp_path)

    witnessed = bool(_needs(*names) & {EXTENDED_CALL_BINDINGS_FEATURE, CONSTRUCT_SELECTORS_FEATURE})
    [connection, store] = [
        item
        for item in _records(facts, SourceSectionName.SYMBOLS)
        if item.data.get("qualified_name") in {"sample.core.Connection", "sample.store.Store"}
    ]
    # The whole class body is one evidence excerpt, so a scan that never replays it omits it.
    assert len(_witnesses(facts)) == (2 if witnessed else 0)
    for item in (connection, store):
        assert len(item.evidence_ids) == (2 if witnessed else 1)
        assert item.data.get("instance_member_writes") is not None


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
    assert len(_witnesses(facts)) == 2


@pytest.mark.parametrize("name", list(RULES))
def test_a_rule_whose_family_was_not_collected_is_a_coverage_failure_never_a_pass(tmp_path, name):
    _write_tree(tmp_path, _contract(name), name, mounted=False)
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
    assert failure.subject == RULES[name]["id"]
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
@pytest.mark.parametrize("name", list(RULES))
def test_uncollected_rule_gets_no_receipt_and_no_violation(tmp_path, name, mounted):
    _write_tree(tmp_path, _contract(name, mounted=mounted), name, mounted=mounted)

    result, facts = _observe(tmp_path, drop_features=True)

    assert not _present(facts)
    observation = result.observation
    assert observation is not None
    [failure] = [
        item
        for item in observation.coverage.failures
        if item.kind == RULE_FAMILY_NOT_COLLECTED_KIND
    ]
    assert [item.rpartition(":")[2] for item in failure.rule_ids] == [RULES[name]["id"]]
    assert dict(failure.data.entries)["families"] == tuple(sorted(NEEDS[name]))
    assert not observation.records("violations")
    assert not [
        item
        for item in observation.records("scope_observations") or ()
        if item.kind == "rule_evaluation"
        and RULES[name]["id"] in [rule.rpartition(":")[2] for rule in item.rule_ids]
    ]
    [row] = rule_assessments(observation, undecided_by_rule={})
    assert row.status != "PASS" and not row.evaluation_proven
    assert any(
        item.kind is DiagnosticKind.RULE_UNSUPPORTED_BY_PROFILE for item in result.diagnostics
    )


@pytest.mark.parametrize("name", list(RULES))
def test_snapshot_analysis_requests_the_families_its_own_contract_declares(tmp_path, name):
    _write_tree(tmp_path, _contract(name), name, mounted=False)

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
    _write_tree(tmp_path, _contract("ownership", "guarded"), "ownership", "guarded", mounted=False)
    recording = _Recording(observer_for(Language.PYTHON).collector)
    request_features: list[tuple[str, ...]] = []
    kept_features = tuple(sorted(NEEDS["guarded"]))

    class _OnlyGuarded:
        def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
            assert isinstance(request.resolver, PythonSettings)
            request_features.append(request.resolver.features)
            kept = replace(request.resolver, features=kept_features)
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

    assert request_features == [tuple(sorted(_needs("ownership", "guarded")))]
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

    catalog = {SOURCE_ROLES_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE, CALL_ARGUMENTS_FEATURE}
    assert required_resolution_features(parsed(_argument())) == catalog
    assert required_resolution_features(parsed(_use())) == catalog
    selector_less = _rule(
        "forbidden_construct", id="PLAIN", source="sample", constructs=["broad_except"]
    )
    plain = parse_contract({"schema_version": "3.14.0", "components": [], "rules": [selector_less]})
    assert required_resolution_features(plain) == frozenset()
    for name, needs in NEEDS.items():
        single = parse_contract(
            {"schema_version": "3.14.0", "components": [], "rules": [RULES[name]]}
        )
        assert required_resolution_features(single) == needs
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
        [BASE_RESOLUTION_FEATURES[0]],
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


@pytest.mark.parametrize("features", [(), tuple(sorted(GATED_RESOLUTION_FEATURES))])
def test_v7_response_round_trips_what_the_collector_declared(tmp_path, features):
    _write_tree(tmp_path, _contract(), mounted=False)
    request = _request(*features, root=str(tmp_path))

    facts = collect(request)
    response = CollectionResponse(facts, ProtocolVersion.V7)
    encoded = encode_response(response)

    assert facts.capabilities.resolution_features == collected_resolution_features(
        ProtocolVersion.V7, request.resolver.features
    )
    assert _present(facts) == frozenset(features)
    _schema_validator().validate(json.loads(encoded))
    assert decode_response(encoded) == response


def test_a_collector_older_than_protocol_7_cannot_name_the_new_families(tmp_path):
    # Review (#662): its records of a family it cannot declare count as not collected.
    _write_tree(tmp_path, _contract(), mounted=False)
    request = _request(root=str(tmp_path), version=ProtocolVersion.V6)
    facts = collect(request)
    unnamed = {SOURCE_ROLES_FEATURE, CONSTRUCT_SELECTORS_FEATURE, NUMERIC_OPERANDS_FEATURE}
    legacy = replace(
        facts,
        capabilities=replace(
            facts.capabilities,
            resolution_features=tuple(
                item for item in facts.capabilities.resolution_features if item not in unnamed
            ),
        ),
    )
    assert _present(legacy) & unnamed

    decoded = decode_response(encode_response(CollectionResponse(legacy, ProtocolVersion.V6)))

    assert not _present(decoded.facts) & unnamed


def _without(facts: SourceFacts, family: str) -> SourceFacts:
    return replace(
        facts,
        capabilities=replace(
            facts.capabilities,
            resolution_features=tuple(
                item for item in facts.capabilities.resolution_features if item != family
            ),
        ),
    )


@pytest.mark.parametrize("family", GATED_RESOLUTION_FEATURES)
def test_records_of_an_undeclared_family_are_rejected(tmp_path, family):
    _write_tree(tmp_path, _contract(), mounted=False)
    facts = collect(_request(family, root=str(tmp_path)))
    assert family in _present(facts)

    with pytest.raises(ProtocolError, match="declared (Python )?capability"):
        encode_response(CollectionResponse(_without(facts, family), ProtocolVersion.V7))


@pytest.mark.parametrize("family", [EXTENDED_CALL_BINDINGS_FEATURE, CONSTRUCT_SELECTORS_FEATURE])
def test_a_member_write_witness_needs_one_of_the_families_that_replay_it(tmp_path, family):
    _write_tree(tmp_path, _contract(), mounted=False)
    facts = collect(_request(family, root=str(tmp_path)))
    assert _witnesses(facts)

    with pytest.raises(ProtocolError, match="member-write witnesses require"):
        encode_response(CollectionResponse(_without(facts, family), ProtocolVersion.V7))


def test_a_scan_without_witnesses_validates_without_a_class_body_excerpt(tmp_path):
    _write_tree(tmp_path, _contract(), mounted=False)

    facts = collect(_request(root=str(tmp_path)))

    assert not _witnesses(facts)
    assert decode_response(encode_response(CollectionResponse(facts, ProtocolVersion.V7)))


def test_a_scan_without_call_arguments_still_writes_the_field_and_round_trips(tmp_path):
    _write_tree(tmp_path, _contract("numeric"), "numeric", mounted=False)

    result, _ = _observe(tmp_path)

    assert result.observation is not None
    calls = result.observation.records("calls")
    assert calls
    # The saved-observation reader still demands an explicit field, null when nothing was written.
    assert all(
        "call_arguments" in dict(call.data.entries) and call.data.get("call_arguments") is None
        for call in calls
    )
    assert parse_observation(observation_payload(result.observation)) == result.observation


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
