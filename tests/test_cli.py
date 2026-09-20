# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.validation import COMPONENT_GRAPH_MARKER
from archkeel.cli import main
from fixtures.demo_catalog_support import FIXTURE_DIR

ROOT = Path(__file__).parents[1]


def test_check_requires_explicit_inputs(capsys: pytest.CaptureFixture) -> None:
    assert main(["check"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == "command-line arguments"
    )


def test_report_has_no_external_analyzer_option() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--analyzer-root" not in result.stdout


def test_skill_install_writes_the_packaged_instructions(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["skill", "install", "claude", "--root", str(tmp_path), "--json"]) == 0
    path = Path(json.loads(capsys.readouterr().out)["path"])
    assert path == tmp_path / ".claude/skills/archkeel/SKILL.md"
    assert "archkeel validate --json" in path.read_text()


@pytest.mark.parametrize("command", ["init", "report", "validate", "check", "skill"])
def test_every_command_help_explains_purpose_and_exit_codes(command: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", command, "--help"],
        capture_output=True,
        text=True,
        env={"NO_COLOR": "1", "COLUMNS": "100", "PATH": ""},
    )
    assert result.returncode == 0
    assert "Exit codes:" in result.stdout
    assert "Example" in result.stdout


def test_no_arguments_prints_the_command_overview(capsys: pytest.CaptureFixture) -> None:
    assert main([]) == 0
    overview = capsys.readouterr().out
    assert all(name in overview for name in ("report", "validate", "check", "--version"))


def test_interactive_terminal_gets_a_summary_and_json_stays_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert main(["validate", "--root", str(ROOT)]) == 0
    summary = capsys.readouterr().out
    assert "Independent verdicts" in summary and not summary.startswith("{")
    assert main(["validate", "--root", str(ROOT), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_report_missing_config_is_unknown(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["report", "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "UNKNOWN"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "UNKNOWN"


def test_validate_self_and_json_are_identical(capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "--root", str(ROOT)]) == 0
    default = capsys.readouterr().out
    assert main(["validate", "--root", str(ROOT), "--json"]) == 0
    explicit = capsys.readouterr().out
    assert explicit == default
    result = json.loads(explicit)
    assert result["observation_complete"] == result["declared_rules"] == "PASS"


def test_validate_write_graph_regenerates_only_the_marked_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-46: a contract edit leaves the marked graph stale, and one flag rewrites that block."""
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    render = next(item for item in contract["components"] if item["label"] == "render")
    render["label"] = "view"
    root = _prepare_repo(tmp_path, {"architecture-contract.json": json.dumps(contract)})
    page = root / "docs/architecture/shop.md"
    before = page.read_text()

    assert main(["validate", "--root", str(root), "--json"]) == 2
    (drift,) = json.loads(capsys.readouterr().out)["diagnostics"]
    assert drift["code"] == "graph.drift"
    assert "archkeel validate --write-graph" in drift["remedy"]

    assert main(["validate", "--root", str(root), "--write-graph", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"] == []
    assert result["artifact"] == "docs/architecture/shop.md"
    head, _, graph = page.read_text().partition(COMPONENT_GRAPH_MARKER)
    assert head == before.partition(COMPONENT_GRAPH_MARKER)[0]
    # The page's own `flowchart LR` stays; the edges are sorted the way `init` writes them.
    assert graph == (
        "\n```mermaid\nflowchart LR\n"
        "    app --> model\n    app --> store\n    cli --> app\n"
        "    cli --> view\n    store --> model\n    view --> model\n```\n"
    )

    assert main(["validate", "--root", str(root), "--write-graph", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] is None


def test_validate_baseline_writes_then_gates_on_new_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-52: the red target's whole loop, through the CLI: write, pass, then grow."""
    probe = (
        "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
        "# SPDX-License-Identifier: MIT\n"
        '"""Getattr probe for the baseline demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def read(box: object) -> object:\n"
        '    return getattr(box, "value")\n'
    )
    root = _prepare_repo(tmp_path, {"shop/model/probe.py": probe})
    baseline = root / "known-violations.json"
    arguments = ["validate", "--root", str(root), "--baseline", str(baseline), "--json"]

    assert main([*arguments, "--write-baseline"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] == str(baseline)
    assert json.loads(baseline.read_text())["violations"] == [
        {"count": 1, "rules": ["CONSTRUCT-NO-DYNAMIC"], "subjects": ["shop.model.probe.read"]}
    ]

    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["failures"] == []

    (root / "shop/model/probe_two.py").write_text(probe)
    assert main(arguments) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"] == []
    assert result["failures"] == [
        "new violation: CONSTRUCT-NO-DYNAMIC | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)"
    ]


def test_validate_write_baseline_needs_a_baseline_path(capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "--root", str(ROOT), "--write-baseline", "--json"]) == 2
    claim = json.loads(capsys.readouterr().out)["diagnostics"][0]["unknown_claim"]
    assert "--write-baseline needs --baseline" in claim


def test_validate_configuration_error_has_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["validate", "--root", str(tmp_path), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "contract_invalid"
    assert diagnostic["pointer"] == ""
