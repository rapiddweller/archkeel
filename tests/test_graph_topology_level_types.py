# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Core topology has one module/package domain without closing open record metadata."""

import copy
import json
import subprocess
import sys
from dataclasses import replace
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_source_trust_boundary import _decode, _observation, _payload
from test_uml_evaluation import _model

from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.evaluation.topology import (
    aggregate_edges,
    cycle_sections,
    transitive_path_records,
)
from archkeel.check.ports import ScanConfig
from archkeel.ir import model
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import classified, parse_record, record_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.structure import module_edges
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARDS = {"GRAPH-TOPOLOGY-AGGREGATE-CONTROL", "GRAPH-TOPOLOGY-READ-CONTROL"}
PORTS = {
    "GRAPH-TOPOLOGY-level",
    "GRAPH-TOPOLOGY-reader",
    "GRAPH-TOPOLOGY-aggregate",
    "GRAPH-TOPOLOGY-cycles",
}


def _imports():
    return [
        classified(
            item_id=identity,
            evidence_class=model.EvidenceClass.FACT,
            area="imports",
            kind="import",
            title=identity,
            data={
                "source_module": source,
                "target_module": target,
                "source_package": source.rpartition(".")[0],
                "target_package": target.rpartition(".")[0],
                "under_type_checking": False,
            },
        )
        for identity, source, target in (
            ("a-b", "sample.a.one", "sample.b.two"),
            ("b-a", "sample.b.two", "sample.a.one"),
        )
    ]


def _level_type():
    assert "GraphTopologyLevel" in vars(model)
    return model.GraphTopologyLevel


def test_actual_edge_producer_exposes_the_missing_nominal_level():
    scan = evaluate_source(
        _decode(_payload()),
        parse_contract({"schema_version": "2.1.0", "components": [], "rules": []}),
        roots=("src",),
        namespace="project",
    )
    assert scan.dependency_edges
    assert isinstance(scan.dependency_edges[0]["data"]["level"], StrEnum)


def test_actual_edge_cycle_and_transitive_producers_share_the_same_topology_domain():
    level = _level_type()
    modules = {"sample.a.one", "sample.b.two"}
    edges, pairs = aggregate_edges(
        _imports(), level=level.MODULE, internal_modules=modules, namespace="sample"
    )
    packages, package_pairs = aggregate_edges(
        _imports(), level=level.PACKAGE, internal_modules=modules, namespace="sample"
    )
    assert all(row["data"]["level"] is level.MODULE for row in edges)
    assert all(row["data"]["level"] is level.PACKAGE for row in packages)
    module_cycles, cycles = cycle_sections(
        modules=[
            {"data": {"qualified_name": name, "package": name.rpartition(".")[0]}}
            for name in sorted(modules)
        ],
        packages=["sample.a", "sample.b"],
        module_edges=edges,
        module_edge_pairs=pairs,
        package_edges=packages,
        package_edge_pairs=package_pairs,
    )
    assert len(module_cycles) == 1
    assert module_cycles[0]["data"]["level"] is level.MODULE
    assert {row["data"]["level"] for row in cycles} == {level.MODULE, level.PACKAGE}
    paths = transitive_path_records(["sample.a", "sample.b"], [("sample.a", "sample.b")])
    assert paths and all(row["data"]["level"] is level.PACKAGE for row in paths)
    assert all(
        json.loads(json.dumps(row))["data"]["level"] in {"module", "package"}
        for row in [*edges, *packages, *cycles, *paths]
    )
    assert level is not model.CycleLevel
    assert {member.value for member in level} == {"module", "package"}


@pytest.mark.parametrize(
    "raw", ["module", "package", "component", "future", None, True, 3, {"level": "module"}]
)
def test_optional_topology_reader_preserves_original_open_record_data(raw):
    reader = getattr(model, "parse_graph_topology_level", None)
    assert callable(reader)
    record = classified(
        item_id="opaque",
        evidence_class=model.EvidenceClass.FACT,
        area="future",
        kind="future_kind",
        title="opaque",
        data={"level": raw, "metadata": {"level": "future-nested"}},
    )
    parsed = parse_record(record)
    recognized = reader(parsed.data.get("level"))
    if raw in ("module", "package"):
        assert recognized is _level_type()(raw)
    else:
        assert recognized is None
    assert record_payload(parsed) == record


@pytest.mark.parametrize(
    "raw,selected",
    [("module", True), ("package", False), ("component", False), ("future", False), (None, False)],
)
def test_real_module_edge_reader_keeps_future_wire_and_kind_open(tmp_path, raw, selected):
    observation = _observation(tmp_path, _decode(_payload()))
    source = next(
        row for row in observation.records("dependency_edges") if row.data.get("level") == "module"
    )
    wire = record_payload(source)
    wire["kind"] = "future_kind"
    wire["data"]["level"] = raw
    record = parse_record(wire)
    observation = replace(
        observation,
        sections=tuple(
            replace(section, records=(record,)) if section.name == "dependency_edges" else section
            for section in observation.sections
        ),
    )
    expected = (("project.app", "project.store", 1),) if selected else ()
    assert module_edges(observation) == expected
    assert record_payload(record) == wire


def _authored_target(*, include_guards=True):
    ir = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    check = json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    target = copy.deepcopy(ir)
    target.pop("$schema", None)
    target["components"].extend(check["components"])
    target["declarations"]["modules"] = []
    wanted = PORTS | {"IR-DEPENDENCY-model", "IR-COMPARISON-structure", "GRAPH-TOPOLOGY-module"}
    entities = [*ir["declarations"]["uml"]["entities"], *check["declarations"]["uml"]["entities"]]
    target["declarations"]["uml"].update(
        entities=[entity for entity in entities if entity["id"] in wanted],
        relationships=[],
        scopes=[],
    )
    assert {entity["id"] for entity in target["declarations"]["uml"]["entities"]} == wanted
    target["rules"] = [
        rule for rule in [*ir["rules"], *check["rules"]] if include_guards and rule["id"] in GUARDS
    ]
    assert {rule["id"] for rule in target["rules"]} == (GUARDS if include_guards else set())
    return target


def _native_repository(tmp_path, *, include_guards=True):
    target = _authored_target(include_guards=include_guards)
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/check/evaluation/__init__.py": "",
        "contract.json": json.dumps(target),
    }
    for item in [
        *target["components"],
        *target["rules"],
        *target["declarations"]["uml"]["entities"],
    ]:
        for path in item["provenance"]:
            files[path] = (ROOT / path).read_text()
    for path in ("ir/model.py", "ir/structure.py", "check/evaluation/topology.py"):
        files["archkeel/" + path] = (ROOT / "src/archkeel" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_authored_topology_ports_are_required_and_parse():
    parse_contract(_authored_target())
    required = (
        (ROOT / "Makefile").read_text().split("pr-test:", 1)[1].split("pr-report-test:", 1)[0]
    )
    assert "tests/test_graph_topology_level_types.py" in required


def test_actual_topology_ports_and_native_controls_are_proven(tmp_path):
    root, config = _native_repository(tmp_path)
    observation = _model(root, config)
    comparison = architecture_report(observation).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    guards = [
        row for row in rule_assessments(observation, undecided_by_rule={}) if row.id in GUARDS
    ]
    assert len(guards) == 2 and all(
        row.status == "PASS" and row.evaluation_proven for row in guards
    )
    assert not trace_valid_violations(observation)


@pytest.mark.parametrize(
    "path,nominal,weak,subject,aspect",
    [
        (
            "ir/model.py",
            "class GraphTopologyLevel(StrEnum):",
            "class GraphTopologyLevel:",
            "GRAPH-TOPOLOGY-level",
            "kind",
        ),
        (
            "ir/model.py",
            "-> GraphTopologyLevel | None:",
            "-> str | None:",
            "GRAPH-TOPOLOGY-reader",
            "signature",
        ),
        (
            "check/evaluation/topology.py",
            "level: GraphTopologyLevel",
            "level: str",
            "GRAPH-TOPOLOGY-aggregate",
            "signature",
        ),
        (
            "check/evaluation/topology.py",
            "    level: GraphTopologyLevel,",
            "    level: str,",
            "GRAPH-TOPOLOGY-cycles",
            "signature",
        ),
    ],
)
def test_actual_topology_port_mutation_fails_unchanged_authored_target(
    tmp_path, path, nominal, weak, subject, aspect
):
    root, config = _native_repository(tmp_path, include_guards=False)
    source = root / "archkeel" / path
    original = source.read_text()
    if subject == "GRAPH-TOPOLOGY-cycles":
        prefix, separator, operation = original.partition("def _cycle_records(")
        assert separator and nominal in operation
        mutated = prefix + separator + operation.replace(nominal, weak, 1)
    else:
        assert nominal in original
        mutated = original.replace(nominal, weak, 1)
    source.write_text(mutated)
    authored = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.subject_id == subject and row.aspect == aspect and row.status == "FAIL"
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == authored


@pytest.mark.parametrize(
    "path,nominal,weak,guard",
    [
        (
            "check/evaluation/topology.py",
            "level == GraphTopologyLevel.MODULE",
            'level == "module"',
            "GRAPH-TOPOLOGY-AGGREGATE-CONTROL",
        ),
        (
            "ir/structure.py",
            "is not GraphTopologyLevel.MODULE",
            '!= "module"',
            "GRAPH-TOPOLOGY-READ-CONTROL",
        ),
    ],
)
def test_actual_topology_control_mutation_fails_unchanged_policy(
    tmp_path, path, nominal, weak, guard
):
    root, config = _native_repository(tmp_path)
    source = root / "archkeel" / path
    original = source.read_text()
    assert nominal in original
    source.write_text(original.replace(nominal, weak, 1))
    authored = (root / "contract.json").read_bytes()
    observation = _model(root, config)
    assessment = next(
        row for row in rule_assessments(observation, undecided_by_rule={}) if row.id == guard
    )
    assert assessment.status == "FAIL" and assessment.evaluation_proven
    assert any(guard in row.rule_ids for row in trace_valid_violations(observation))
    assert (root / "contract.json").read_bytes() == authored


def test_actual_topology_ports_reject_raw_strings_and_other_level_domain(tmp_path):
    common = """from archkeel.check.evaluation.topology import aggregate_edges, _cycle_records
from archkeel.ir.model import CycleLevel, GraphTopologyLevel
from archkeel.ir.facts_codec import RawRecord
def check(records: list[RawRecord]) -> None:
"""
    cases = {
        "canonical": """    aggregate_edges(records,level=GraphTopologyLevel.MODULE,internal_modules=set(),namespace="sample")
    _cycle_records(level=GraphTopologyLevel.PACKAGE,nodes=(),edges=(),edge_records=records)
""",
        "raw-aggregate": '    aggregate_edges(records,level="module",internal_modules=set(),namespace="sample")\n',
        "wrong-aggregate": '    aggregate_edges(records,level=CycleLevel.MODULE,internal_modules=set(),namespace="sample")\n',
        "raw-cycles": '    _cycle_records(level="package",nodes=(),edges=(),edge_records=records)\n',
        "wrong-cycles": "    _cycle_records(level=CycleLevel.MODULE,nodes=(),edges=(),edge_records=records)\n",
    }
    for name, body in cases.items():
        path = tmp_path / (name.replace("-", "_") + ".py")
        path.write_text(common + body)
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert (result.returncode == 0) == (name == "canonical"), result.stdout + result.stderr
        if name != "canonical":
            assert "[arg-type]" in result.stdout
