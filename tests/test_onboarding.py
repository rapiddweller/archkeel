# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from archkeel.analyzer import observe
from archkeel.check.onboarding import detect_source, interface_entries
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.decisions import open_decisions
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    CompleteAssignmentRule,
    DiagnosticError,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    in_scope,
)

_REAL_RATIONALE = "The owners decided this on purpose."

ROOT = Path(__file__).parents[1]


def _contract(path: Path) -> ArchitectureContract:
    return parse_contract(decode_json(path.read_bytes()))


def _repository(root: Path, packages: tuple[str, ...] = ("archkeel",)) -> Path:
    for package in packages:
        shutil.copytree(
            ROOT / "src/archkeel",
            root / "src" / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    for args in (
        ("init", "-q"),
        ("config", "user.email", "init@example.invalid"),
        ("config", "user.name", "Archkeel init"),
        ("add", "."),
        ("commit", "-qm", "snapshot"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def _init(root: Path, capsys: pytest.CaptureFixture) -> dict:
    assert main(["init", "--root", str(root), "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_init_drafts_no_dependency_rule_but_still_drafts_structural_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    result = _init(root, capsys)
    assert result["artifact"] == "architecture-contract.json"

    draft = _contract(root / "architecture-contract.json")
    assert not any(
        isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule) for rule in draft.rules
    )
    assert any(isinstance(rule, CompleteAssignmentRule) for rule in draft.rules)
    assert any(isinstance(rule, NoComponentCyclesRule) for rule in draft.rules)
    assert any(isinstance(rule, InterfaceBoundaryRule) for rule in draft.rules)

    # Every other component imports archkeel.ir.model, so ir always gets a public entry for
    # it; pin a concrete case instead of only asserting properties that hold vacuously.
    ir_component = next(component for component in draft.components if component.label == "ir")
    assert ir_component.public is not None
    assert "archkeel.ir.model" in ir_component.public

    assert main(["init", "--root", str(root), "--json", "--force"]) == 0
    capsys.readouterr()
    redraft = _contract(root / "architecture-contract.json")
    for component, again in zip(draft.components, redraft.components, strict=True):
        assert component.public == again.public, "drafted public entries must be deterministic"
        if component.public is None:
            continue
        assert list(component.public) == sorted(set(component.public))
        for entry in component.public:
            module, _, name = entry.partition(":")
            assert not (name or module.rsplit(".", 1)[-1]).startswith("_")
            assert any(in_scope(module, package) for package in component.packages)


def test_init_drafts_component_sizes_and_names_the_largest(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-38: a per-child draft hides size; the draft must carry it instead of just names."""
    root = _repository(tmp_path)
    result = _init(root, capsys)

    draft = _contract(root / "architecture-contract.json")
    labels = {component.label for component in draft.components}
    sizes = {item["label"]: item for item in result["draft_sizes"]}
    assert set(sizes) == labels
    assert all(sizes[label]["modules"] > 0 for label in labels)

    document = (root / "docs/architecture/architecture.md").read_text()
    assert "| Component | Package | Modules | Inner edges | Responsibility |" in document
    for label in labels:
        row = next(line for line in document.splitlines() if line.startswith(f"| `{label}` |"))
        assert f"| {sizes[label]['modules']} | {sizes[label]['inner_edges']} |" in row

    # `analyzer` is Archkeel's own densest top-level package by a wide margin (AD-33).
    assert sizes["analyzer"]["modules"] > sizes["ir"]["modules"]
    assert sizes["analyzer"]["modules"] > sizes["cli"]["modules"]


def test_init_graph_with_private_component_validates_without_graph_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    private_package = root / "src/archkeel/_compat"
    private_package.mkdir()
    (private_package / "__init__.py").write_text("from . import helper\n")
    (private_package / "helper.py").write_text("VALUE = 1\n")
    (root / "src/archkeel/uses_compat.py").write_text(
        "from ._compat import helper\n\nVALUE = helper.VALUE\n"
    )

    _init(root, capsys)
    main(["validate", "--root", str(root), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert "graph.drift" not in {item["code"] for item in result["diagnostics"]}


def test_init_opens_no_second_level(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """AD-20: a level is opened by an architect deciding to, never by init drafting one."""
    root = _repository(tmp_path)
    _init(root, capsys)

    draft = _contract(root / "architecture-contract.json")
    assert draft.components, "the draft must name components for the assertion to mean anything"
    assert all(component.inside is None for component in draft.components)


def test_init_open_decisions_are_sorted_and_cover_every_ordered_pair_exactly_once(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    result = _init(root, capsys)
    decisions = result["open_decisions"]
    assert decisions, "archkeel's own components observe each other"

    sites = [item["import_sites"] for item in decisions]
    assert sites == sorted(sites, reverse=True), "heaviest observed edges must come first"

    draft = _contract(root / "architecture-contract.json")
    labels = [component.label for component in draft.components]
    expected_pairs = {
        (source, target) for source in labels for target in labels if source != target
    }
    pairs = [(item["source"], item["target"]) for item in decisions]
    assert len(pairs) == len(set(pairs)), "every ordered pair appears at most once"
    assert set(pairs) == expected_pairs, "every ordered pair appears at least once"

    heaviest = decisions[0]
    assert heaviest["observed"] is (heaviest["import_sites"] > 0)


def test_open_decision_options_round_trip_through_parse_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    result = _init(root, capsys)
    contract_path = root / "architecture-contract.json"
    raw = json.loads(contract_path.read_bytes())
    decision = result["open_decisions"][0]

    for key, rule_type in (
        ("allowed_dependency", AllowedDependencyRule),
        ("forbidden_dependency", ForbiddenDependencyRule),
    ):
        option = {**decision["options"][key], "rationale": _REAL_RATIONALE}
        candidate = json.dumps({**raw, "rules": [*raw["rules"], option]}).encode()
        parsed = parse_contract(decode_json(candidate))
        added = parsed.rules[-1]
        assert isinstance(added, rule_type)
        assert added.id == option["id"]
        assert added.source == decision["source_package"]
        assert added.target == decision["target_package"]


def test_deciding_every_open_pair_from_init_options_makes_validate_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    result = _init(root, capsys)
    contract_path = root / "architecture-contract.json"
    raw = json.loads(contract_path.read_bytes())

    decisions = [
        {
            **item["options"]["allowed_dependency" if item["observed"] else "forbidden_dependency"],
            "rationale": _REAL_RATIONALE,
        }
        for item in result["open_decisions"]
    ]
    raw["rules"] = [
        {**rule, "rationale": _REAL_RATIONALE} if rule["rationale"].startswith("TODO") else rule
        for rule in raw["rules"]
    ] + decisions
    contract_path.write_text(json.dumps(raw, indent=2) + "\n")

    assert main(["validate", "--root", str(root), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["diagnostics"] == []
    assert validated["open_decisions"] == []
    # AD-16: every rule here still carries init's decided_by: agent placeholder verbatim.
    agent_decided, total_rules = validated["agent_decisions"]
    assert agent_decided == total_rules == len(raw["rules"])


def test_open_decision_import_sites_match_a_ground_truth_count_from_imports(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The regression from issue: package-level truncation undercounted nested packages.

    `init` drafts no dependency rule, so every ordered pair among Archkeel's own components
    is an open decision; its `import_sites` must equal the number of raw `imports` records
    that cross that pair, independently grouped here through the drafted contract's own
    `component_for`, not through `_component_import_sites` itself.
    """
    root = _repository(tmp_path)
    _init(root, capsys)
    contract = _contract(root / "architecture-contract.json")

    config = ScanConfig(("src/archkeel",), "archkeel", "architecture-contract.json", "")
    _, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    ground_truth: Counter[tuple[str, str]] = Counter()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is not None and target is not None and source != target:
            ground_truth[(source.label, target.label)] += 1

    labels = [component.label for component in contract.components]
    expected = {
        (source, target): ground_truth.get((source, target), 0)
        for source in labels
        for target in labels
        if source != target
    }
    decisions = open_decisions(observation)
    actual = {(item.source, item.target): item.import_sites for item in decisions}
    assert actual == expected


def test_init_never_replaces_existing_files_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    (root / "archkeel.toml").write_text("[scan]\n")
    assert main(["init", "--root", str(root), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "existing_files" and diagnostic["subject"] == "archkeel.toml"
    assert (root / "archkeel.toml").read_text() == "[scan]\n"
    assert main(["init", "--root", str(root), "--json", "--force"]) == 0


def test_init_asks_for_the_source_when_the_package_is_ambiguous(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path, ("alpha", "beta"))
    assert main(["init", "--root", str(root), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert (
        diagnostic["kind"] == "scope_empty" and "src/alpha, src/beta" in diagnostic["unknown_claim"]
    )
    assert not (root / "archkeel.toml").exists()


def test_init_picks_the_package_the_project_is_named_after(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # AD-47: the copied pyproject.toml declares `name = "archkeel"`; `tests_pkg` sits beside it.
    root = _repository(tmp_path, ("archkeel", "tests_pkg"))
    _init(root, capsys)
    assert (
        'roots = ["src/archkeel"]\nnamespace = "archkeel"\n' in (root / "archkeel.toml").read_text()
    )


def test_init_stays_ambiguous_when_no_package_matches_the_project_name(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path, ("archkeel_core", "tests_pkg"))
    assert main(["init", "--root", str(root), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "scope_empty"
    assert "[project] name (archkeel)" in diagnostic["unknown_claim"]
    assert "src/archkeel_core, src/tests_pkg" in diagnostic["unknown_claim"]
    assert not (root / "archkeel.toml").exists()


def _flat_layout(root: Path, pyproject: str | None) -> Path:
    for package in ("archkeel_core", "tests_pkg"):
        (root / package).mkdir()
        (root / package / "__init__.py").touch()
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject)
    return root


@pytest.mark.parametrize("name", ["archkeel_core", "Archkeel-Core", "archkeel.core"])
def test_detect_source_matches_the_project_name_in_wheel_file_name_form(
    tmp_path: Path, name: str
) -> None:
    root = _flat_layout(tmp_path, f'[project]\nname = "{name}"\n')
    assert detect_source(root) == ("archkeel_core", "archkeel_core")


@pytest.mark.parametrize("pyproject", [None, "[project\n", '[project]\nversion = "1"\n'])
def test_detect_source_fails_closed_without_a_readable_project_name(
    tmp_path: Path, pyproject: str | None
) -> None:
    with pytest.raises(DiagnosticError) as raised:
        detect_source(_flat_layout(tmp_path, pyproject))
    assert raised.value.diagnostic.kind == "scope_empty"
    assert "[project] name (missing); found archkeel_core, tests_pkg." in (
        raised.value.diagnostic.unknown_claim
    )


def test_interface_entries_applies_the_ad9_module_entry_rule() -> None:
    # __all__ present -> module entry regardless of how many names are used.
    assert interface_entries("pkg.mod", {"a"}, False, True, {"a", "b"}) == ["pkg.mod"]
    # Whole-module or star import -> module entry regardless of names.
    assert interface_entries("pkg.mod", set(), True, False, set()) == ["pkg.mod"]
    # 2 of 4 public names used -> half rule qualifies -> one module entry.
    assert interface_entries("pkg.mod", {"a", "b"}, False, False, {"a", "b", "c", "d"}) == [
        "pkg.mod"
    ]
    # 1 of 4 -> below half -> a symbol entry per used name.
    assert interface_entries("pkg.mod", {"a"}, False, False, {"a", "b", "c", "d"}) == ["pkg.mod:a"]
    # Underscore names are never proposed, and they do not count toward the half rule.
    assert interface_entries(
        "pkg.mod", {"_hidden", "shown"}, False, False, {"shown", "b", "c", "d"}
    ) == ["pkg.mod:shown"]
