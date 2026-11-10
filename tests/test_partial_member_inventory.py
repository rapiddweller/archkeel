# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unrelated resolver gaps do not erase certified direct native members."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from collector_pin import trusted
from dart_native_helpers import collect_native_dart

from archkeel.analyzer.typescript.collect import collect as collect_typescript
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.facts import RecordData, ResolutionInput, SourceFacts
from archkeel.ir.member_inventory import MEMBER_INVENTORY_PROOF, member_inventory_proof
from archkeel.ir.model import TARGET_GRAPH_RECORD_KINDS, Observation
from archkeel.ir.protocol import CollectionError, CollectionRequest
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.source_graph import observed_graph


@dataclass(frozen=True)
class _Collector:
    language: str

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        return (
            collect_native_dart(request) if self.language == "dart" else collect_typescript(request)
        )


def _entity(identity, kind, name, language, parent=None, **details):
    return {
        "id": identity,
        "kind": kind,
        "qualified_name": name,
        "language": language,
        "parent_id": parent,
        "presence": "planned",
        "responsibilities": ["Own the independently declared source role."],
        "provenance": ["docs/target.md"],
        **details,
    }


def _intent(language: str, model: str, gap: str):
    entities = [
        _entity("model", "module", model, language, "app"),
        _entity("gap", "module", gap, language, "app"),
        _entity("data", "class", f"{model}.Data", language, "model"),
        _entity("value", "attribute", f"{model}.Data.value", language, "data"),
        _entity("run", "method", f"{model}.Data.run", language, "data"),
    ]
    if language == "dart":
        entities.extend(
            [
                _entity("widget", "class", f"{gap}.Widget", language, "gap"),
                _entity(
                    "unknown",
                    "method",
                    f"{gap}.Widget.Widget",
                    language,
                    "widget",
                    signature={
                        "parameters": [
                            {
                                "name": "key",
                                "kind": "keyword_only",
                                "annotation": "String",
                                "default_known": True,
                            }
                        ],
                        "returns": "Widget",
                    },
                ),
            ]
        )
    else:
        entities.append(
            _entity(
                "unknown",
                "function",
                f"{gap}.load",
                language,
                "gap",
                signature={
                    "parameters": [
                        {
                            "name": "x",
                            "kind": "positional",
                            "annotation": "string",
                            "default_known": True,
                        }
                    ],
                    "returns": "number",
                },
            )
        )
    return {
        "schema_version": "1.0.0",
        "entities": entities,
        "scopes": [
            {
                "scope_id": "data",
                "mode": "closed",
                "entity_kinds": ["attribute", "method"],
                "rationale": "Own exactly the direct Data declarations.",
                "provenance": ["docs/target.md"],
            }
        ],
    }


def _project(root: Path, language: str) -> ScanConfig:
    source = "lib" if language == "dart" else "src"
    namespace = "commerce" if language == "dart" else "demo"
    suffix = "dart" if language == "dart" else "ts"
    model = "commerce.model" if language == "dart" else "demo.src.model_x2e_ts"
    gap = "commerce.gap" if language == "dart" else "demo.src.gap_x2e_ts"
    (root / source).mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("Data owns its explicit value and run declarations.\n")
    (root / source / f"model.{suffix}").write_text(
        "class Data { String value = 'ready'; void run() {} }\n"
        if language == "dart"
        else "export class Data { value: string; run(): void {} }\n"
    )
    (root / source / f"gap.{suffix}").write_text(
        "class Widget extends External { Widget({super.key}); }\n"
        if language == "dart"
        else "const id = './model'; import(id);\n"
        "export function load(x: number): number { return x; }\n"
    )
    if language == "dart":
        (root / "pubspec.yaml").write_text(
            "name: commerce\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n"
        )
    else:
        (root / "tsconfig.json").write_text(json.dumps({"include": ["src/**/*.ts"]}))
    (root / "architecture-contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.2.0",
                "components": [
                    {
                        "id": "app",
                        "label": "app",
                        "role": "component",
                        "namespace": namespace,
                        "packages": [namespace],
                        "exact_modules": [model, gap],
                        "responsibilities": ["Own the two native source libraries."],
                        "forbidden_responsibilities": [],
                        "decided_by": "architect",
                        "provenance": ["docs/target.md"],
                    }
                ],
                "rules": [],
                "declarations": {"uml": _intent(language, model, gap)},
            }
        )
    )
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
        ("add", "-A"),
        ("-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(("git", *args), cwd=root, check=True, capture_output=True)
    return ScanConfig(
        (source,), namespace, "architecture-contract.json", "unused", language=language
    )


def _live(root: Path, language: str):
    config = _project(root, language)
    result, encoded = run_report(root, config=config, analyzer=trusted(_Collector(language)))
    assert encoded is not None
    return result, encoded, parse_observation(decode_canonical_model(json.loads(encoded)))


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_unrelated_resolution_gap_keeps_direct_member_inventory_proven(tmp_path, language):
    result, encoded, model = _live(tmp_path, language)
    report = architecture_report(model)
    assert result.coverage.status == "FAIL" and result.diagnostics
    assert (
        model.coverage.files_discovered
        == model.coverage.files_read
        == model.coverage.files_parsed
        == 2
    )
    assert report.comparison is not None
    inventory = next(
        a
        for a in report.comparison.assessments
        if a.subject_id == "data" and a.aspect == "completeness"
    )
    assert inventory.status == "PASS", inventory
    assert any(
        a.status != "PASS" and a.subject_id == "unknown" for a in report.comparison.assessments
    )
    saved_path = tmp_path / "architecture.json"
    saved_path.write_bytes(encoded)
    saved = run_saved_report(saved_path)
    assert saved.exit_code == result.exit_code
    assert saved.rule_assessments == result.rule_assessments


@pytest.fixture(scope="module", params=["dart", "typescript"])
def certified(request, tmp_path_factory):
    _, _, model = _live(tmp_path_factory.mktemp(request.param), request.param)
    proof = next(
        r for r in model.records("scope_observations") or () if r.kind == MEMBER_INVENTORY_PROOF
    )
    inputs = tuple(
        ResolutionInput(row.get("path"), row.get("digest"), row.get("role"))
        for row in proof.data.get("inputs")
    )
    return model, inputs


@pytest.mark.parametrize("state", ["runtime_uncertain", "conditional", "ambiguous"])
def test_inventory_proof_ownership_tracks_declarations_instead_of_runtime_flags(certified, state):
    model, inputs = certified
    owner = next(
        item
        for item in model.records("symbols") or ()
        if item.kind == "class" and item.data.get("name") == "Data"
    )
    values = dict(owner.data.entries)
    if state == "conditional":
        values["definition_contexts"] = (RecordData((("kind", "if"), ("branch", "body"))),)
    else:
        values.update(
            source_binding_unique=False,
            source_member_binding_static=False,
            class_header_static=False,
        )
    changed = replace(owner, data=RecordData(tuple(values.items())))
    symbols = tuple(
        changed if item.id == owner.id else item for item in model.records("symbols") or ()
    )
    if state == "ambiguous":
        symbols += (replace(changed, id="other-definition"),)
    model = replace(
        model,
        sections=tuple(
            replace(section, records=symbols) if section.name == "symbols" else section
            for section in model.sections
        ),
    )
    proof = member_inventory_proof(model, inputs)
    assert (proof is not None and owner.id in proof.fact_ids) is (state == "runtime_uncertain")


@pytest.mark.parametrize(
    "alter",
    [
        "foreign_module",
        "foreign_source_module",
        "foreign_subject",
        "unrecognized_dimension",
        "unrecognized_field",
        "boolean_line",
        "invalid_reason",
        "missing_reason",
    ],
)
def test_contradictory_gap_localization_cannot_mint_inventory_proof(certified, alter):
    model, inputs = certified
    gap = model.coverage.failures[0]
    data = dict(gap.data.entries)
    if alter == "foreign_module":
        data["module"] = "outside.foreign"
    elif alter == "foreign_source_module":
        data["source_module"] = "outside.foreign"
    elif alter == "unrecognized_dimension":
        data["resolution_dimension"] = "declarations"
    elif alter == "unrecognized_field":
        data["opaque_impact"] = True
    elif alter == "boolean_line":
        site = next(e for e in model.evidence if e.id == gap.evidence_ids[0])
        data.update(file=site.file, line=True)
    elif alter == "invalid_reason":
        data["reason"] = False
    elif alter == "missing_reason":
        data.pop("reason", None)
        data.pop("message", None)
    gap = replace(
        gap,
        data=RecordData(tuple(sorted(data.items()))),
        subjects=("outside.foreign",) if alter == "foreign_subject" else gap.subjects,
    )
    changed = replace(model, coverage=replace(model.coverage, failures=(gap,)))
    assert member_inventory_proof(changed, inputs) is None


@pytest.mark.parametrize(
    "version,required,state",
    [
        ("3.10.9", ">=3.11", "declared"),
        ("٣.١١.١٢", ">=3.11", "declared"),
        ("3.11.12", ">=999", "declared"),
        ("3.11.12", ">=3.11", "metadata_invalid"),
    ],
)
def test_invalid_matching_runtime_metadata_cannot_mint_inventory_proof(
    certified,
    version,
    required,
    state,
):
    model, inputs = certified
    changed = replace(
        model,
        runtime=replace(model.runtime, version=version, required=required, requirement_state=state),
    )
    assert member_inventory_proof(changed, inputs) is None


def _inventory_is_complete(model: Observation) -> bool:
    graph = observed_graph(model)
    owner = next((e for e in graph.entities if e.qualified_name.rsplit(".", 1)[-1] == "Data"), None)
    if owner is None:
        return False
    inventory = [c for c in graph.coverage if c.scope_id == owner.id and c.entity_kinds]
    return bool(inventory) and all(c.status == "complete" for c in inventory)


@pytest.mark.parametrize(
    "alter",
    [
        "source",
        "contract",
        "producer",
        "runtime",
        "parse_count",
        "evidence",
        "fact",
        "permission",
        "legacy",
    ],
)
def test_changed_snapshot_cannot_replay_certified_member_inventory(certified, alter):
    model, _ = certified
    if alter == "source":
        changed = replace(model, source=replace(model.source, source_digest="a" * 64))
    elif alter == "contract":
        changed = replace(model, contract=replace(model.contract, digest="a" * 64))
    elif alter == "producer":
        changed = replace(model, producer=replace(model.producer, code_digest="a" * 64))
    elif alter == "runtime":
        changed = replace(model, runtime=replace(model.runtime, version="3.12.10"))
    elif alter == "parse_count":
        changed = replace(model, coverage=replace(model.coverage, files_parsed=1))
    elif alter == "evidence":
        changed = replace(
            model, evidence=(replace(model.evidence[0], excerpt="changed"), *model.evidence[1:])
        )
    elif alter == "fact":
        changed = replace(
            model,
            sections=tuple(
                replace(
                    s,
                    records=tuple(
                        replace(r, title="changed") if r.kind == "class" else r for r in s.records
                    ),
                )
                if s.name == "symbols"
                else s
                for s in model.sections
            ),
        )
    elif alter == "permission":
        changed = replace(
            model,
            sections=tuple(
                replace(
                    s,
                    records=tuple(
                        replace(r, title="changed")
                        if r.kind not in TARGET_GRAPH_RECORD_KINDS
                        else r
                        for r in s.records
                    ),
                )
                if s.name == "declarations"
                else s
                for s in model.sections
            ),
        )
    else:
        changed = replace(
            model,
            sections=tuple(
                replace(s, records=tuple(r for r in s.records if r.kind != MEMBER_INVENTORY_PROOF))
                if s.name == "scope_observations"
                else s
                for s in model.sections
            ),
        )
    assert not _inventory_is_complete(changed)
    assert architecture_report(changed).comparison is None


def test_changed_target_cannot_replay_inventory_comparison(certified):
    model, _ = certified
    changed = replace(
        model,
        sections=tuple(
            replace(
                s,
                records=tuple(
                    replace(r, title="different independent Target")
                    if r.kind in TARGET_GRAPH_RECORD_KINDS
                    else r
                    for r in s.records
                ),
            )
            if s.name == "declarations"
            else s
            for s in model.sections
        ),
    )
    assert _inventory_is_complete(changed)
    assert architecture_report(changed).comparison is None


def _unbound_inventory_snapshot(model, alter):
    raw = decode_canonical_model(json.loads(canonical_report_bytes(model)))
    if alter == "proof_and_binding":
        raw["scope_observations"] = [
            r for r in raw["scope_observations"] if r["kind"] != MEMBER_INVENTORY_PROOF
        ]
    receipt = next(r for r in raw["scope_observations"] if r["kind"] == "rule_evaluation")
    if alter in {"proof_and_binding", "binding_only", "changed_target"}:
        receipt["data"].pop("member_inventory_binding")
        receipt["data"].pop("member_inventory_target")
    elif alter == "null_binding":
        receipt["data"]["member_inventory_binding"] = None
        receipt["data"]["member_inventory_target"] = None
    elif alter == "missing_target":
        receipt["data"].pop("member_inventory_target")
    else:
        receipt["data"]["member_inventory_target"] = "wrong-target"
    if alter == "changed_target":
        declaration = next(r for r in raw["declarations"] if r["kind"] in TARGET_GRAPH_RECORD_KINDS)
        value = next(e for e in declaration["data"]["target"]["entities"] if e["id"] == "value")
        value["qualified_name"] = value["qualified_name"].removesuffix("value") + "other"
    return parse_observation(raw)


@pytest.mark.parametrize(
    "alter",
    [
        "proof_and_binding",
        "binding_only",
        "null_binding",
        "missing_target",
        "wrong_target",
        "changed_target",
    ],
)
def test_partial_closed_inventory_cannot_replay_unbound_cached_pass(certified, alter):
    model, _ = certified
    changed = _unbound_inventory_snapshot(model, alter)
    if alter == "changed_target":
        from archkeel.check.uml_compare import compare_graphs

        report = architecture_report(changed)
        assert _inventory_is_complete(changed)
        assert compare_graphs(report.observed, report.target).status == "FAIL"
    assert architecture_report(changed).comparison is None


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_stripped_legacy_all_pass_inventory_is_withheld_on_saved_replay(tmp_path, language):
    config = _project(tmp_path, language)
    _target_without_gap_detail(tmp_path)
    _, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert architecture_report(model).comparison.status == "PASS"
    changed = _unbound_inventory_snapshot(model, "proof_and_binding")
    saved_path = tmp_path / "architecture.json"
    saved_path.write_bytes(canonical_report_bytes(changed))
    reloaded = parse_observation(decode_canonical_model(json.loads(saved_path.read_bytes())))
    assert not _inventory_is_complete(reloaded)
    assert architecture_report(reloaded).comparison is None
    saved = run_saved_report(saved_path)
    assert saved.exit_code == 2 and saved.coverage.status == "FAIL"


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_legacy_partial_open_scope_keeps_known_comparison(tmp_path, language):
    config = _project(tmp_path, language)
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["declarations"]["uml"]["scopes"][0]["mode"] = "open"
    path.write_text(json.dumps(contract))
    _, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status in {"FAIL", "UNKNOWN"}
    changed = _unbound_inventory_snapshot(model, "proof_and_binding")
    assert architecture_report(changed).comparison == comparison


@pytest.mark.parametrize("local_gap", [False, True])
def test_partial_owner_with_closed_attributes_and_open_methods_keeps_known_comparison(
    tmp_path, local_gap
):
    config = _project(tmp_path, "typescript")
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    closed = contract["declarations"]["uml"]["scopes"][0]
    closed["entity_kinds"] = ["attribute"]
    contract["declarations"]["uml"]["scopes"].append(
        {**closed, "mode": "open", "entity_kinds": ["method"]}
    )
    path.write_text(json.dumps(contract))
    source = tmp_path / "src/model.ts"
    if local_gap:
        source.write_text(source.read_text() + "const id = './gap'; import(id);\n")
    result, encoded = run_report(
        tmp_path, config=config, analyzer=trusted(_Collector("typescript"))
    )
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert _inventory_is_complete(model) is not local_gap
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL"
    scopes = [
        a for a in comparison.assessments if a.subject_id == "data" and a.aspect == "completeness"
    ]
    assert {a.status for a in scopes} == ({"PASS", "UNKNOWN"} if local_gap else {"PASS"})
    assert any(a.aspect == "signature" and a.status == "FAIL" for a in comparison.assessments)
    saved_path = tmp_path / "architecture.json"
    saved_path.write_bytes(encoded)
    assert run_saved_report(saved_path).rule_assessments == result.rule_assessments
    if not local_gap:
        changed = _unbound_inventory_snapshot(model, "proof_and_binding")
        assert architecture_report(changed).comparison is None


@pytest.mark.parametrize("alter", ["schema", "inputs", "owner", "duplicate"])
def test_malformed_inventory_proof_cannot_replay_comparison(certified, alter):
    model, _ = certified
    proof = next(
        r for r in model.records("scope_observations") or () if r.kind == MEMBER_INVENTORY_PROOF
    )
    data = dict(proof.data.entries)
    if alter == "schema":
        data["schema_version"] = "99.0.0"
    elif alter == "inputs":
        data["inputs"] = None
    changed_proof = replace(
        proof,
        data=RecordData(tuple(sorted(data.items()))),
        fact_ids=("foreign-owner",) if alter == "owner" else proof.fact_ids,
    )
    changed = replace(
        model,
        sections=tuple(
            replace(
                s,
                records=tuple(changed_proof if r is proof else r for r in s.records)
                + ((changed_proof,) if alter == "duplicate" else ()),
            )
            if s.name == "scope_observations"
            else s
            for s in model.sections
        ),
    )
    assert not _inventory_is_complete(changed)
    assert architecture_report(changed).comparison is None


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_local_resolver_gap_keeps_direct_inventory_unknown(tmp_path, language):
    config = _project(tmp_path, language)
    relative = "lib/model.dart" if language == "dart" else "src/model.ts"
    path = tmp_path / relative
    path.write_text(
        path.read_text()
        + (
            "class Other extends External { Other({super.key}); }\n"
            if language == "dart"
            else "const id = './gap'; import(id);\n"
        )
    )
    _, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert not _inventory_is_complete(model)
    assert not any(
        r.kind == MEMBER_INVENTORY_PROOF for r in model.records("scope_observations") or ()
    )


@pytest.mark.parametrize("part_state", ["complete", "gap", "missing", "broken"])
def test_dart_owned_part_closure_is_required_for_inventory(tmp_path, part_state):
    config = _project(tmp_path, "dart")
    source = (tmp_path / "lib/model.dart").read_text()
    (tmp_path / "lib/model.dart").write_text("part 'data.part.dart';\n")
    content = "part of 'model.dart';\n" + source
    if part_state == "gap":
        content += "class Other extends External { Other({super.key}); }\n"
    if part_state == "broken":
        content += "class Broken { ???\n"
    if part_state != "missing":
        (tmp_path / "lib/data.part.dart").write_text(content)
    _, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector("dart")))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert _inventory_is_complete(model) is (part_state == "complete")


@pytest.mark.parametrize("diagnostic", ["runtime_mismatch", "contract_invalid"])
def test_late_diagnostic_revokes_inventory_before_serialization(tmp_path, monkeypatch, diagnostic):
    import archkeel.check.report as report_module
    from archkeel.ir.model import Diagnostic

    config = _project(tmp_path, "dart")
    original = report_module.observe_repository

    def late_failure(*args, **kwargs):
        result = original(*args, **kwargs)
        assert _inventory_is_complete(result.observation)
        return replace(
            result,
            diagnostics=(
                *result.diagnostics,
                Diagnostic(
                    diagnostic,
                    "late",
                    "late validity failure",
                    "repeat",
                    code="contract.invalid" if diagnostic == "contract_invalid" else None,
                ),
            ),
        )

    monkeypatch.setattr(report_module, "observe_repository", late_failure)
    fresh, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector("dart")))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert not _inventory_is_complete(model)
    assert architecture_report(model).comparison is None
    saved_path = tmp_path / "architecture.json"
    saved_path.write_bytes(encoded)
    saved = run_saved_report(saved_path)
    assert saved.rule_assessments == fresh.rule_assessments


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_repeat_native_collection_has_identical_inventory_proof(tmp_path, language):
    config = _project(tmp_path, language)
    models = []
    for _ in range(2):
        _, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
        models.append(parse_observation(decode_canonical_model(json.loads(encoded))))
    proofs = [
        next(r for r in m.records("scope_observations") or () if r.kind == MEMBER_INVENTORY_PROOF)
        for m in models
    ]
    assert proofs[0] == proofs[1]
    assert architecture_report(models[0]).comparison == architecture_report(models[1]).comparison


@pytest.mark.parametrize("language", ["dart", "typescript"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_certified_inventory_retains_missing_and_extra_member_fail(tmp_path, language, change):
    config = _project(tmp_path, language)
    path = tmp_path / ("lib/model.dart" if language == "dart" else "src/model.ts")
    source = path.read_text()
    if change == "missing":
        source = source.replace(
            "String value = 'ready'; " if language == "dart" else "value: string; ", ""
        )
    else:
        source = source.replace(
            "void run()" if language == "dart" else "run()",
            "String extra = 'extra'; void run()" if language == "dart" else "extra: string; run()",
        )
    path.write_text(source)
    result, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert _inventory_is_complete(model)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assert any(
        a.status == "FAIL" and a.subject_id == ("value" if change == "missing" else "data")
        for a in comparison.assessments
    )
    uml = next(r for r in result.rule_assessments if r.kind == "uml_target")
    assert uml.status == "FAIL" and not uml.evaluation_proven


def _target_without_gap_detail(root: Path, *, signature_only: bool = False) -> None:
    path = root / "architecture-contract.json"
    target = json.loads(path.read_text())
    uml = target["declarations"]["uml"]
    if signature_only:
        uml["entities"] = [e for e in uml["entities"] if e["id"] in {"gap", "unknown"}]
        uml["entities"][-1]["signature"]["parameters"][0]["annotation"] = "number"
        uml["scopes"] = []
    else:
        uml["entities"] = [e for e in uml["entities"] if e["id"] not in {"unknown", "widget"}]
    path.write_text(json.dumps(target))


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_only_certified_closed_inventory_target_retains_partial_pass_comparison(tmp_path, language):
    config = _project(tmp_path, language)
    _target_without_gap_detail(tmp_path)
    result, encoded = run_report(tmp_path, config=config, analyzer=trusted(_Collector(language)))
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS"
    assert model.coverage.status == "FAIL" and result.exit_code == 2
    uml = next(r for r in result.rule_assessments if r.kind == "uml_target")
    assert uml.status == "UNKNOWN" and not uml.evaluation_proven
    saved_path = tmp_path / "architecture.json"
    saved_path.write_bytes(encoded)
    assert run_saved_report(saved_path).rule_assessments == result.rule_assessments


def test_unrelated_inventory_does_not_retain_signature_only_partial_pass(tmp_path):
    config = _project(tmp_path, "typescript")
    _target_without_gap_detail(tmp_path, signature_only=True)
    observer = trusted(_Collector("typescript"))
    candidate = observer(
        tmp_path,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=True,
        contract_root=tmp_path,
        language="typescript",
    )
    assert _inventory_is_complete(candidate.observation)
    _, encoded = run_report(tmp_path, config=config, analyzer=observer)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert architecture_report(model).comparison is None
