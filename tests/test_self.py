# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Archkeel with its bundled analyzer and verify the saved D-self evidence."""

import json
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.model import Observation

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"
COMPONENT_GRAPH = "<!-- archkeel-component-graph -->"


def _contract() -> dict:
    return json.loads((ROOT / "architecture-contract.json").read_bytes())


def _components(contract: dict) -> dict[str, tuple[str, ...]]:
    components = {
        component["label"]: tuple(component["packages"]) for component in contract["components"]
    }
    packages = [(label, package) for label, values in components.items() for package in values]
    for index, (left_label, left) in enumerate(packages):
        for right_label, right in packages[index + 1 :]:
            if left_label != right_label:
                assert not (
                    left == right or left.startswith(right + ".") or right.startswith(left + ".")
                )
    return components


def _component_for(module: str, components: dict[str, tuple[str, ...]]) -> str | None:
    owners = [
        label
        for label, packages in components.items()
        if any(module == package or module.startswith(package + ".") for package in packages)
    ]
    assert len(owners) <= 1, (module, owners)
    return owners[0] if owners else None


def _observed_edges(
    observation: Observation, components: dict[str, tuple[str, ...]]
) -> set[tuple[str, str]]:
    edges = set()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        assert isinstance(source_module, str) and isinstance(target_module, str)
        source = _component_for(source_module, components)
        target = _component_for(target_module, components)
        if source is not None and target is not None and source != target:
            edges.add((source, target))
    return edges


@pytest.fixture(scope="module")
def self_observation(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    output = tmp_path_factory.mktemp("self-report") / "architecture.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(ROOT),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert output.with_name("architecture.report.html").is_file()
    result = json.loads(run.stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == result["declared_rules"] == "PASS"
    assert result["expectation_fulfilled"] == "n/a"
    return parse_observation(decode_canonical_model(json.loads(output.read_bytes())))


def test_self_report_is_complete_and_matches_saved_evidence(self_observation: Observation) -> None:
    observed = self_observation
    artifact = (FIXTURE / "architecture.json").read_bytes()
    provenance = json.loads((FIXTURE / "provenance.json").read_bytes())
    saved = parse_observation(decode_canonical_model(json.loads(artifact)))
    assert observed.records("violations") == ()
    assert all(record.kind != "rule-without-subjects" for record in observed.records("unknowns"))
    coverage = observed.coverage
    assert coverage.status == coverage.rules == "PASS"
    assert coverage.files_discovered == coverage.files_read == coverage.files_parsed > 0
    assert coverage.failures == ()
    assert observed.python_version == saved.python_version
    assert observed.source.source_digest == saved.source.source_digest
    assert observed.contract.digest == saved.contract.digest
    assert observed.analyzer.code_digest == saved.analyzer.code_digest
    assert coverage == saved.coverage
    assert provenance == {
        "analyzer_digest": saved.analyzer.code_digest,
        "checker_digest": package_digest(),
        "source_digest": saved.source.source_digest,
        "contract_digest": saved.contract.digest,
        "artifact_digest": sha256(artifact).hexdigest(),
        "command": "archkeel report --root . --output fixtures/D-self/architecture.json",
        "exit_code": 0,
        "python_version": saved.python_version,
    }


def test_self_contract_covers_modules_and_analyzer_interface(self_observation: Observation) -> None:
    contract = _contract()
    packages = {
        package for component in contract["components"] for package in component["packages"]
    }
    public_api = set(contract["public_api"])
    forbidden_ir = {
        rule["target"] for rule in contract["rules"] if rule["source"] == "archkeel.analyzer"
    }
    for module in self_observation.records("modules"):
        name = module.data.get("qualified_name")
        assert isinstance(name, str)
        if name != "archkeel":
            assert any(name == package or name.startswith(package + ".") for package in packages), (
                name
            )
        if name.startswith("archkeel.ir.") and name not in public_api:
            assert any(
                name == prefix or name.startswith(prefix + ".") for prefix in forbidden_ir
            ), name
    for record in self_observation.records("imports"):
        source = record.data.get("source_module")
        target = record.data.get("target_module")
        assert isinstance(source, str) and isinstance(target, str)
        if (source == "archkeel.analyzer" or source.startswith("archkeel.analyzer.")) and (
            target == "archkeel.ir" or target.startswith("archkeel.ir.")
        ):
            assert target in public_api, (source, target)


def test_self_contract_closes_every_component_pair(self_observation: Observation) -> None:
    contract = _contract()
    components = _components(contract)
    package_owner = {
        package: label for label, packages in components.items() for package in packages
    }
    forbidden = [
        (package_owner[rule["source"]], package_owner[rule["target"]])
        for rule in contract["rules"]
        if rule["kind"] == "forbidden_dependency"
        and rule["source"] in package_owner
        and rule["target"] in package_owner
    ]
    rule_keys = [
        (
            rule["kind"],
            rule["source"],
            rule["target"],
            rule.get("target_symbol"),
            rule["include_type_checking"],
        )
        for rule in contract["rules"]
    ]
    observed = _observed_edges(self_observation, components)
    expected = {
        (source, target) for source in components for target in components if source != target
    }
    assert len(forbidden) == len(set(forbidden))
    assert len(rule_keys) == len(set(rule_keys))
    assert observed.isdisjoint(forbidden)
    assert observed | set(forbidden) == expected


def test_contract_rationales_explain_more_than_the_rule() -> None:
    repeated = re.compile(r"(?:The )?\S+ does not depend on \S+\.", re.IGNORECASE)
    assert [
        rule["id"] for rule in _contract()["rules"] if repeated.fullmatch(rule["rationale"])
    ] == []


def test_component_graph_matches_observed_edges(self_observation: Observation) -> None:
    components = _components(_contract())
    graphs = []
    for path in (ROOT / "docs/architecture/archkeel.md", ROOT / "README.md"):
        fragments = path.read_text().split(COMPONENT_GRAPH)
        for fragment in fragments[1:]:
            mermaid = fragment.split("```mermaid\n", 1)[1].split("```", 1)[0]
            graphs.append(
                {
                    match.groups()
                    for line in mermaid.splitlines()
                    if (
                        match := re.fullmatch(
                            r"\s*([a-z][a-z0-9_]*)\s*-->\s*([a-z][a-z0-9_]*)\s*", line
                        )
                    )
                }
            )
    assert len(graphs) == 1
    assert graphs[0] == _observed_edges(self_observation, components)
