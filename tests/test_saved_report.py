# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Saved reports retain recorded evidence and never scan or write a repository."""

import json
import shutil

import pytest
from test_analyzer import _observe_one_rule
from test_architecture_projection import _repository
from test_boundary_type_allowances import _ALLOWANCE, _observe_app
from test_dart_profile import _committed, _component
from test_exact_type_ignore import RULE as TYPE_IGNORE_RULE
from test_exact_type_ignore import SOURCE as TYPE_IGNORE_SOURCE
from test_result_schema import validator as validator
from test_target_graph import _nested_repository
from test_typescript_onboarding import arguments, collector, repository

from archkeel.check.report import run_report, run_saved_report
from archkeel.cli import build_parser, main
from archkeel.cli.observe import observe
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, result_bytes


@pytest.mark.parametrize("selector", [None, "CORE", "store"])
def test_saved_architecture_query_matches_live_bytes_without_repository(
    tmp_path, monkeypatch, capsys, selector, validator
):
    root, config = _repository(tmp_path)
    live, packet = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component=selector
    )
    assert live.exit_code == 0 and live.declared_rules == "FAIL"
    saved = tmp_path / "architecture.json"
    saved.write_bytes(packet)
    shutil.rmtree(root)
    query_root = tmp_path / "query"
    query_root.mkdir()
    monkeypatch.chdir(query_root)
    arguments = ["report", "--input", str(saved), "--only", "architecture", "--json"]
    if selector is not None:
        arguments += ["--component", selector]
    outputs = []
    for _ in range(2):
        assert main(arguments) == 0
        outputs.append(capsys.readouterr().out.encode())
    assert outputs == [result_bytes(live), result_bytes(live)]
    assert saved.read_bytes() == packet
    assert list(query_root.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["architecture.json", "query"]
    payload = json.loads(outputs[0])
    assert not list(validator.iter_errors(payload))
    assert payload["coverage"]["files_discovered"] == 5
    assert payload["declared_rules"] == "FAIL"
    assert bool(payload["filtered_violations"]) is (selector != "store")
    assert payload["architecture_projection"]["source"] == json.loads(packet)["source"]


@pytest.mark.parametrize("only, rule", [("violations", "NO-OTHER"), ("calls", None)])
def test_saved_query_reuses_existing_facets(tmp_path, capsys, only, rule):
    root, config = _repository(tmp_path)
    live, packet = run_report(
        root,
        config=config,
        analyzer=observe,
        component="core",
        rule=rule,
        only_violations=only == "violations",
        only_calls=only == "calls",
    )
    saved = tmp_path / "architecture.json"
    saved.write_bytes(packet)
    arguments = ["report", "--input", str(saved), "--only", only, "--component", "core", "--json"]
    if rule is not None:
        arguments += ["--rule", rule]
    assert main(arguments) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == json.loads(result_bytes(live))


@pytest.mark.parametrize("option", ["--root", "--config", "--baseline", "--output"])
def test_saved_query_rejects_live_or_writing_options_before_reading_input(tmp_path, capsys, option):
    saved = tmp_path / "missing.json"
    assert main(["report", "--input", str(saved), option, str(saved), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"][0]["kind"] == "parse_error"
    assert "--input cannot be combined" in payload["diagnostics"][0]["unknown_claim"]
    assert option in payload["diagnostics"][0]["unknown_claim"]
    assert not saved.exists() and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content", [b"[1]", b"{", b"{}"])
def test_saved_query_rejects_malformed_packet_with_named_diagnostic(tmp_path, capsys, content):
    saved = tmp_path / "architecture.json"
    saved.write_bytes(content)
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["diagnostics"][0]["kind"] == "parse_error"
    assert payload["diagnostics"][0]["subject"] == str(saved)
    assert saved.read_bytes() == content


@pytest.mark.parametrize(
    "fault",
    [
        "evidence",
        "rule",
        "fact",
        "comparison_source",
        "source_scope",
        "source_package",
        "source_package_null",
        "source_package_missing",
        "shared_module_path",
        "source_file",
        "source_definition",
        "module_file",
    ],
)
def test_saved_query_rejects_dangling_or_foreign_source_references(tmp_path, capsys, fault):
    root, config = (
        _nested_repository(tmp_path) if fault == "comparison_source" else _repository(tmp_path)
    )
    live, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert live.exit_code == 0
    raw = decode_canonical_model(json.loads(packet))
    if fault == "comparison_source":
        receipt = next(row for row in raw["scope_observations"] if row["data"].get("comparison"))
        receipt["data"]["comparison"]["assessments"][0]["observed_ids"] = ["OTHER-SOURCE"]
    elif fault in {"source_package", "source_package_null", "source_package_missing"}:
        if fault == "source_package_missing":
            del raw["imports"][0]["data"]["source_package"]
        else:
            raw["imports"][0]["data"]["source_package"] = (
                None if fault == "source_package_null" else "foreign"
            )
    elif fault == "shared_module_path":
        module = next(
            row for row in raw["modules"] if row["data"]["qualified_name"] == "sample.idle"
        )
        module["data"]["file"] = "sample/core.py"
        for identifier in module["evidence_ids"]:
            next(row for row in raw["evidence"] if row["id"] == identifier)["file"] = (
                "sample/core.py"
            )
    elif fault == "source_scope":
        raw["imports"][0]["data"]["source_module"] = "sample.other"
    elif fault == "source_definition":
        raw["imports"][0]["data"]["source_definition_id"] = next(
            row["id"] for row in raw["modules"] if row["data"]["qualified_name"] == "sample.other"
        )
    elif fault == "module_file":
        next(row for row in raw["modules"] if row["data"]["qualified_name"] == "sample.idle")[
            "data"
        ]["file"] = "sample/core.py"
    elif fault == "source_file":
        source_evidence = raw["imports"][0]["evidence_ids"][0]
        next(row for row in raw["evidence"] if row["id"] == source_evidence)["file"] = (
            "sample/store.py"
        )
    else:
        raw["violations"][0][f"{fault}_ids"] = ["MISSING"]
    saved = tmp_path / "invalid.json"
    saved.write_bytes(canonical_report_bytes(raw))
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["declared_rules"] == "UNKNOWN"
    assert payload["diagnostics"][0]["kind"] == "parse_error"
    assert payload.get("architecture_projection") is None
    if fault in {"source_package", "source_package_null", "source_package_missing"}:
        assert "import source package disagrees" in payload["diagnostics"][0]["unknown_claim"]
    elif fault == "shared_module_path":
        assert "duplicate module path" in payload["diagnostics"][0]["unknown_claim"]


def test_saved_partial_coverage_retains_unknown_and_unmeasured_relationships(tmp_path, capsys):
    root, config = _repository(tmp_path)
    (root / "sample/broken.py").write_text("def broken(:\n")
    live, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert live.exit_code == 2
    saved = tmp_path / "partial.json"
    saved.write_bytes(packet)
    shutil.rmtree(root)
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 2
    output = capsys.readouterr().out.encode()
    assert output == result_bytes(live)
    payload = json.loads(output)
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["coverage"] == json.loads(result_bytes(live))["coverage"]
    view = payload["architecture_projection"]
    assert view["status"] == "UNKNOWN" and view["unknowns"]
    assert view["levels"][0]["used"] is None
    assert all(row["status"] != "PASS" for row in view["components"])


def test_saved_runtime_requirement_is_checked_against_recorded_runtime(tmp_path, capsys):
    root, config = _repository(tmp_path)
    _, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    raw = decode_canonical_model(json.loads(packet))
    raw["runtime"]["required"] = ">=9.0"
    saved = tmp_path / "runtime.json"
    saved.write_bytes(canonical_report_bytes(raw))
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_complete"] == "UNKNOWN"
    assert payload["diagnostics"][0]["kind"] == "runtime_mismatch"
    assert raw["runtime"]["version"] in payload["diagnostics"][0]["subject"]


def test_saved_query_unknown_component_keeps_existing_named_remedy(tmp_path, capsys):
    root, config = _repository(tmp_path)
    _, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    saved = tmp_path / "architecture.json"
    saved.write_bytes(packet)
    assert (
        main(
            [
                "report",
                "--input",
                str(saved),
                "--only",
                "architecture",
                "--component",
                "missing",
                "--json",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"][0]["kind"] == "filter_unknown"
    assert "--component" in payload["diagnostics"][0]["subject"]


def test_report_help_distinguishes_recorded_evidence_from_fresh_scan(capsys):
    with pytest.raises(SystemExit) as outcome:
        build_parser().parse_args(["report", "--help"])
    assert outcome.value.code == 0
    help_text = capsys.readouterr().out
    assert "--input" in help_text
    assert "saved snapshot" in help_text
    assert "current working tree" in help_text


def test_saved_query_missing_file_is_named_without_creating_artifacts(tmp_path, capsys):
    saved = tmp_path / "missing.json"
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"][0]["subject"] == str(saved)
    assert payload["diagnostics"][0]["kind"] == "parse_error"
    assert list(tmp_path.iterdir()) == []


def test_saved_nested_scope_preserves_target_assessments(tmp_path, capsys):
    root, config = _nested_repository(tmp_path)
    live, packet = run_report(
        root, config=config, analyzer=observe, only_architecture=True, component="core:service"
    )
    assert live.exit_code == 0
    saved = tmp_path / "nested.json"
    saved.write_bytes(packet)
    shutil.rmtree(root)
    assert (
        main(
            [
                "report",
                "--input",
                str(saved),
                "--only",
                "architecture",
                "--component",
                "core:service",
                "--json",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.encode() == result_bytes(live)


@pytest.mark.parametrize("only", ["calls", "architecture"])
def test_saved_query_rejects_rule_facet_for_non_violation_modes(tmp_path, capsys, only):
    saved = tmp_path / "missing.json"
    assert (
        main(["report", "--input", str(saved), "--only", only, "--rule", "NO-OTHER", "--json"]) == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--rule narrows violations" in payload["diagnostics"][0]["unknown_claim"]
    assert list(tmp_path.iterdir()) == []


def test_saved_dart_query_preserves_unmeasured_source_sections(tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    config = _committed(
        root,
        {"lib/main.dart": "import 'store.dart';\n", "lib/store.dart": ""},
        {
            "components": [
                _component("core", "app.main", namespace="app.main", public=["app.main"]),
                _component("store", "app.store", namespace="app.store", public=["app.store"]),
            ]
        },
    )
    live, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert live.exit_code == 0
    saved = tmp_path / "dart.json"
    saved.write_bytes(packet)
    shutil.rmtree(root)
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 0
    assert capsys.readouterr().out.encode() == result_bytes(live)
    raw = decode_canonical_model(json.loads(packet))
    assert raw["coverage"]["calls_analyzed"] is None and raw["symbols"] is None


def test_saved_typescript_query_matches_native_cli_without_collector_or_repository(
    tmp_path, monkeypatch, capsys
):
    root = repository(
        tmp_path / "repo", {"src/main.ts": "import './store.js';", "src/store.ts": "export {};"}
    )
    assert main([*arguments(root), *collector()]) == 0
    capsys.readouterr()
    saved = tmp_path / "typescript.json"
    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "architecture",
                "--output",
                str(saved),
                "--json",
            ]
        )
        == 0
    )
    live = capsys.readouterr().out.encode()
    packet = saved.read_bytes()
    shutil.rmtree(root)
    query_root = tmp_path / "query"
    query_root.mkdir()
    monkeypatch.chdir(query_root)
    monkeypatch.setenv("PATH", "")
    assert main(["report", "--input", str(saved), "--only", "architecture", "--json"]) == 0
    assert capsys.readouterr().out.encode() == live
    assert list(query_root.iterdir()) == [] and saved.read_bytes() == packet
    raw = decode_canonical_model(json.loads(packet))
    assert raw["calls"] is None and raw["symbols"] is None


@pytest.mark.parametrize("kind", ["boundary_type_allowance", "type_ignore_allowance"])
@pytest.mark.parametrize("fault", [None, "evidence", "rule", "fact", "source_kind"])
def test_saved_core_allowance_keeps_trace_checks_without_raw_source_payload(tmp_path, kind, fault):
    if kind == "boundary_type_allowance":
        observed = _observe_app(tmp_path / "repo", _ALLOWANCE)
    else:
        (tmp_path / "repo").mkdir()
        observed = _observe_one_rule(
            tmp_path / "repo", TYPE_IGNORE_RULE, {"operations.py": TYPE_IGNORE_SOURCE}
        )
    raw = decode_canonical_model(json.loads(canonical_report_bytes(observed.observation)))
    allowance = next(row for row in raw["typing_signals"] if row["kind"] == kind)
    assert "owner" not in allowance["data"] and "source_module" not in allowance["data"]
    if fault == "source_kind":
        allowance["kind"] = "object_annotation"
    elif fault is not None:
        allowance[f"{fault}_ids"] = ["MISSING"]
    saved = tmp_path / "allowance.json"
    saved.write_bytes(canonical_report_bytes(raw))
    shutil.rmtree(tmp_path / "repo")
    result = run_saved_report(saved, only_architecture=True)
    if fault is None:
        assert result.exit_code == 0 and not result.diagnostics
        assert result.coverage == observed.coverage
    else:
        assert result.exit_code == 2 and result.observation_complete == "UNKNOWN"
        assert result.diagnostics[0].kind == "parse_error"
