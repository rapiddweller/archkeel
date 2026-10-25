# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-266: the first hour. `init` reads its own observation aloud, and `--adopt` takes it in."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from test_onboarding import _repository

from archkeel.check import onboarding
from archkeel.check.onboarding import ADOPTED_RATIONALE, CONTRACT_PATH, run_init
from archkeel.cli import main
from archkeel.cli.config import ADOPTED_BASELINE_PATH as BASELINE_PATH
from archkeel.cli.guide import GUIDE_PATH
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import FirstLook, RunResult
from archkeel.render.summary import init_summary

_JUDGEMENT = re.compile(r"\b(good|bad|healthy|large|small|too)\b", re.IGNORECASE)
_NEXT_STEPS = (
    "1. archkeel report            # read the overview and the first findings",
    "2. open test-artifacts/architecture/architecture.report.html   "
    "# the Explorer; click a name to select a component",
    "3. archkeel init --force --adopt   # or write the target yourself "
    "(see docs/getting-started.md)",
)


def _cyclic_repository(root: Path) -> Path:
    """The same project as `_repository`, with `ir.model` importing `cli.app` back."""
    _repository(root)
    model = root / "src" / "archkeel" / "ir" / "model.py"
    model.write_text("from archkeel.cli.app import VALUE as CLI_VALUE\n" + model.read_text())
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "cycle"], cwd=root, check=True, capture_output=True)
    return root


def _first_look_lines(sentence: str) -> list[str]:
    start = sentence.index("First look:")
    end = sentence.index("Next steps:")
    return [line.strip() for line in sentence[start:end].splitlines()[1:] if line.strip()]


def _init_json(root: Path, capsys: pytest.CaptureFixture, *extra: str) -> tuple[int, dict]:
    code = main(["init", "--root", str(root), "--json", "--full", *extra])
    return code, json.loads(capsys.readouterr().out)


def _observed_pairs(payload: dict) -> set[tuple[str, str]]:
    return {
        (item["source"], item["target"]) for item in payload["open_decisions"] if item["observed"]
    }


def _contract(root: Path) -> dict:
    return json.loads((root / CONTRACT_PATH).read_bytes())


def test_first_look_reports_a_module_cycle_when_there_is_one(tmp_path: Path) -> None:
    result, _ = run_init(
        _cyclic_repository(tmp_path), source=None, namespace=None, force=False, analyzer=observe
    )

    lines = _first_look_lines(init_summary(result).sentence)

    assert "Module cycles: 1 (largest: 2 modules)" in lines


def test_first_look_says_none_when_there_is_no_module_cycle(tmp_path: Path) -> None:
    result, _ = run_init(
        _repository(tmp_path), source=None, namespace=None, force=False, analyzer=observe
    )

    lines = _first_look_lines(init_summary(result).sentence)

    assert "Module cycles: none" in lines
    assert "Most imported module: archkeel.ir.model (3 modules import it)" in lines
    assert any(line.startswith("Largest component: ") for line in lines)
    assert any(re.fullmatch(r"Files parsed: \d+ of \d+", line) for line in lines)
    assert any(re.fullmatch(r"Calls resolved: (not measured|\d+\.\d\d %)", line) for line in lines)
    assert "Positions left UNKNOWN: 0" in lines


@pytest.mark.parametrize("cyclic", [False, True])
def test_first_look_and_next_steps_state_facts_without_judgement(
    tmp_path: Path, cyclic: bool
) -> None:
    root = _cyclic_repository(tmp_path) if cyclic else _repository(tmp_path)
    result, _ = run_init(root, source=None, namespace=None, force=False, analyzer=observe)
    sentence = init_summary(result).sentence

    lines = _first_look_lines(sentence)

    assert len(lines) == 6
    assert not [line for line in lines if _JUDGEMENT.search(line)]
    stripped = [line.strip() for line in sentence.splitlines()]
    for step in _NEXT_STEPS:
        assert step in stripped


def test_first_look_wording_for_one_importer_a_tie_and_no_measured_calls() -> None:
    look = FirstLook(
        files_parsed=2,
        files_discovered=2,
        call_resolution_percent=None,
        module_cycles=0,
        largest_module_cycle=0,
        most_imported_module="pkg.one",
        most_importers=1,
        largest_component="alpha",
        largest_component_ties=2,
        largest_component_modules=5,
        unknown_positions=0,
    )
    result = RunResult(
        "init",
        0,
        observation_complete="PASS",
        expectation_fulfilled="n/a",
        artifact="architecture-contract.json",
        first_look=look,
    )

    lines = _first_look_lines(init_summary(result).sentence)
    isolated = init_summary(
        RunResult(
            "init",
            0,
            observation_complete="PASS",
            expectation_fulfilled="n/a",
            artifact="architecture-contract.json",
            first_look=FirstLook(2, 2, 0.0, 0, 0, None, 0, None, 0, 0, 0),
        )
    )

    assert lines == [
        "Files parsed: 2 of 2",
        "Calls resolved: not measured",
        "Module cycles: none",
        "Most imported module: pkg.one (1 module imports it)",
        "Largest component: tie of 2 components (5 modules each)",
        "Positions left UNKNOWN: 0",
    ]
    assert "Most imported module: none" in _first_look_lines(isolated.sentence)
    assert "Largest component: none" in _first_look_lines(isolated.sentence)


def test_init_json_carries_one_first_look_object(tmp_path: Path, capsys) -> None:
    code, payload = _init_json(_repository(tmp_path), capsys)

    assert code == 0
    look = payload["first_look"]
    assert set(look) == {
        "files_parsed",
        "files_discovered",
        "call_resolution_percent",
        "module_cycles",
        "largest_module_cycle",
        "most_imported_module",
        "most_importers",
        "largest_component",
        "largest_component_ties",
        "largest_component_modules",
        "unknown_positions",
    }
    assert look["module_cycles"] == 0 and look["largest_module_cycle"] == 0
    assert look["most_imported_module"] == "archkeel.ir.model" and look["most_importers"] == 3


def test_other_results_keep_their_shape_without_first_look(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    main(["init", "--root", str(root), "--json"])
    capsys.readouterr()

    main(["validate", "--root", str(root), "--json"])
    assert "first_look" not in json.loads(capsys.readouterr().out)


def test_plain_init_writes_no_requires_and_no_complete_requires(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)

    assert main(["init", "--root", str(root)]) == 0

    contract = _contract(root)
    assert all("requires" not in component for component in contract["components"])
    assert all(rule["kind"] != "complete_requires" for rule in contract["rules"])
    assert not (root / "architecture-baseline.json").exists()


def test_adopt_writes_one_agent_requires_entry_per_observed_crossing(
    tmp_path: Path, capsys
) -> None:
    root = _repository(tmp_path)
    _, plain = _init_json(root, capsys)
    observed = _observed_pairs(plain)
    code, adopted = _init_json(root, capsys, "--adopt", "--force")
    assert code == 0

    entries = {
        (component["label"], requirement["component"]): requirement
        for component in _contract(root)["components"]
        for requirement in component.get("requires", [])
    }

    assert set(entries) == observed and observed
    for requirement in entries.values():
        assert requirement["decided_by"] == "agent"
        assert requirement["rationale"] == ADOPTED_RATIONALE
        assert requirement["through"]
    assert adopted["open_decision_count"] == 0


def test_adopt_names_the_imported_symbol_or_the_whole_module(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys, "--adopt")

    ports = {
        requirement["component"]: requirement["through"]
        for component in _contract(root)["components"]
        for requirement in component.get("requires", [])
        if component["label"] == "check"
    }

    assert ports == {"ir": ["archkeel.ir.model"], "cli": ["archkeel.cli.app"]}


def test_adopt_adds_one_complete_requires_rule_and_no_placeholder_rationale(
    tmp_path: Path, capsys
) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys, "--adopt")

    rules = _contract(root)["rules"]
    complete = [rule for rule in rules if rule["kind"] == "complete_requires"]

    assert len(complete) == 1 and complete[0]["decided_by"] == "agent"
    assert all(rule["rationale"] == ADOPTED_RATIONALE for rule in rules)
    assert parse_contract(decode_json((root / CONTRACT_PATH).read_bytes())) is not None


def test_adopt_writes_a_baseline_and_validate_exits_zero(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    code, _ = _init_json(root, capsys, "--adopt")
    assert code == 0 and (root / BASELINE_PATH).is_file()

    assert main(["validate", "--root", str(root), "--baseline", BASELINE_PATH, "--json"]) == 0


def test_a_new_import_inside_an_adopted_pair_makes_validate_exit_one(
    tmp_path: Path, capsys
) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys, "--adopt")
    (root / "src/archkeel/ir/extra.py").write_text("VALUE = 2\n")
    rules = root / "src/archkeel/check/rules.py"
    rules.write_text(
        "from archkeel.ir import extra\nfrom archkeel.ir import model\n"
        "from .nested import extra as nested_extra\n"
        "VALUE = model.VALUE + nested_extra.VALUE + extra.VALUE\n"
    )

    assert main(["validate", "--root", str(root), "--baseline", BASELINE_PATH, "--json"]) == 1


def test_adopted_entries_count_as_agent_decisions_and_nothing_else(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys)
    main(["validate", "--root", str(root), "--json"])
    plain = json.loads(capsys.readouterr().out)["agent_decisions"]
    _init_json(root, capsys, "--adopt", "--force")
    main(["validate", "--root", str(root), "--baseline", BASELINE_PATH, "--json"])
    adopted = json.loads(capsys.readouterr().out)["agent_decisions"]

    requires = sum(
        len(component.get("requires", [])) for component in _contract(root)["components"]
    )
    # The adoption adds one agent entry per requires and the complete_requires rule, nothing more.
    assert adopted == [plain[0] + requires + 1, plain[1] + requires + 1]


def test_rerunning_init_without_force_refuses_and_keeps_the_adopted_contract(
    tmp_path: Path, capsys
) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys, "--adopt")
    before = (root / CONTRACT_PATH).read_bytes()

    assert main(["init", "--root", str(root), "--adopt"]) == 2
    assert (root / CONTRACT_PATH).read_bytes() == before


def test_init_force_adopt_replaces_the_baseline(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    _init_json(root, capsys, "--adopt")
    (root / BASELINE_PATH).write_text(
        '{"schema_version": "1.3.0", "budgets": {}, "violations": []}\n'
    )

    assert main(["init", "--root", str(root), "--adopt", "--force"]) == 0
    assert main(["validate", "--root", str(root), "--baseline", BASELINE_PATH, "--json"]) == 0


def test_adopted_crossings_are_the_pairs_init_observed(tmp_path: Path, capsys) -> None:
    root = _repository(tmp_path)
    _, plain = _init_json(root, capsys)
    observed = _observed_pairs(plain)
    _init_json(root, capsys, "--adopt", "--force")

    adopted = {
        (component["label"], requirement["component"])
        for component in _contract(root)["components"]
        for requirement in component.get("requires", [])
    }

    assert adopted == observed


def _tree(root: Path) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_init_writes_the_guide_that_archkeel_guide_would_write(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)

    code, _ = _init_json(root, capsys, "--adopt")
    assert code == 0
    written = (root / GUIDE_PATH).read_bytes()

    assert main(["guide", "--root", str(root), "--output", "elsewhere.md"]) == 0
    assert written == (root / "elsewhere.md").read_bytes()
    assert main(["guide", "--root", str(root), "--check"]) == 0


def test_init_force_adopt_writes_a_guide_that_counts_the_adopted_requires(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    assert _init_json(root, capsys)[0] == 0

    code, _ = _init_json(root, capsys, "--adopt", "--force")

    requires = sum(
        len(component.get("requires", [])) for component in _contract(root)["components"]
    )
    assert code == 0 and requires > 0
    assert f"- Requires entries: {requires}." in (root / GUIDE_PATH).read_text(encoding="utf-8")
    assert main(["guide", "--root", str(root), "--check"]) == 0


def test_init_refuses_an_existing_guide_without_force_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    guide = root / GUIDE_PATH
    guide.parent.mkdir(parents=True)
    guide.write_text("hand written\n", encoding="utf-8")
    before = _tree(root)

    code, payload = _init_json(root, capsys)

    assert code == 2
    assert GUIDE_PATH in json.dumps(payload)
    assert _tree(root) == before


def test_init_that_fails_writes_no_guide_and_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _repository(tmp_path)
    before = _tree(root)

    code = main(["init", "--root", str(root), "--language", "typescript", "--json"])

    assert code == 2
    capsys.readouterr()
    assert not (root / GUIDE_PATH).exists()
    assert _tree(root) == before


def test_interactive_init_names_the_guide_among_the_written_files(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    # A wide terminal keeps Rich from splitting the long temporary path.
    monkeypatch.setenv("COLUMNS", "400")

    assert main(["init", "--root", str(root)]) == 0

    assert "contract-guide.md" in capsys.readouterr().out


def test_init_guard_and_guide_command_name_the_same_path() -> None:
    # init guards the path it never writes itself, so the two copies must stay equal.
    assert onboarding.GUIDE_PATH == GUIDE_PATH
