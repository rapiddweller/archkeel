# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.validation import COMPONENT_GRAPH_MARKER, TARGET_GRAPH_MARKER
from archkeel.cli import main
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay

ROOT = Path(__file__).parents[1]
_PROBE = (
    "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
    "# SPDX-License-Identifier: MIT\n"
    '"""Getattr probe for the baseline demo."""\n\n'
    "from __future__ import annotations\n\n\n"
    "def read(box: object) -> object:\n"
    '    return getattr(box, "value")\n'
)


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
    baseline = "architecture-baseline.json"
    assert main(["validate", "--root", str(ROOT), "--baseline", baseline]) == 0
    summary = capsys.readouterr().out
    assert "Independent verdicts" in summary and not summary.startswith("{")
    assert main(["validate", "--root", str(ROOT), "--baseline", baseline, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_report_missing_config_is_unknown(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["report", "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "UNKNOWN"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "UNKNOWN"


def test_config_selects_a_second_scope_and_every_result_names_its_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-101: the shop sample's tests/ is checked by its own file at the same root, and a
    result names the roots it scanned, so a green product run is not read as covering tests."""
    root = _prepare_repo(tmp_path, {})
    tests = ["--root", str(root), "--config", "archkeel-tests.toml"]

    assert main(["validate", "--root", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["scan_roots"] == ["shop"]
    assert main(["validate", *tests, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["scan_roots"] == ["tests"]

    output = tmp_path / "tests.json"
    assert main(["report", *tests, "--output", str(output), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["scan_roots"] == ["tests"]
    architecture = json.loads(output.read_text())
    assert architecture["source"]["scope"] == ["tests/**/*.py"]
    assert architecture["contract"]["path"] == "tests/architecture-contract.json"

    assert main(["validate", "--root", str(root), "--config", "missing.toml", "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["subject"] == str(root / "missing.toml")
    assert "cannot read missing.toml" in diagnostic["unknown_claim"]


def _two_code_bases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> Path:
    """#149's repository: the shop sample at the root and the Dart app in mobile/, each with
    the baseline of its own debt, a getattr probe in one and dart:io in the other."""
    repo = _prepare_repo(tmp_path, {"shop/model/probe.py": _PROBE})
    app = repo / "mobile"
    shutil.copytree(DART_FIXTURE_DIR, app)
    apply_overlay(app, next(item for item in CATALOG if item.id == "dart-forbidden-dart-io").files)
    for root in (repo, app):
        monkeypatch.chdir(root)
        assert (
            main(["validate", "--baseline", "architecture-baseline.json", "--write-baseline"]) == 0
        )
    capsys.readouterr()
    monkeypatch.chdir(repo)
    for args in (["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "mobile"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return repo


def _root_relative_claim(repo: Path, option: str, value: str) -> str:
    return (
        f"The architecture contract cannot be validated: {option} {value} is relative to "
        f"--root {repo / 'mobile'}: it names {repo / 'mobile' / value}, which does not exist, "
        f"not {repo / value}; pass {option} {value.removeprefix('mobile/')}"
    )


def test_baseline_is_read_relative_to_root_like_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """AD-103 (#149): from the repository root, the app's check reads the app's baseline.

    Before, --baseline was read from the working directory, so this run read the backend's
    file and reported one new and one resolved violation that were a wrong file, not a
    regression. The root-prefixed spelling that used to be right names nothing now, and says
    so instead of reading or writing one directory too deep.
    """
    repo = _two_code_bases(tmp_path, monkeypatch, capsys)
    app = ["validate", "--root", "mobile", "--json"]

    assert main([*app, "--baseline", "architecture-baseline.json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["baseline_new"], result["baseline_resolved"], result["failures"]) == (0, 0, [])

    prefixed = "mobile/architecture-baseline.json"
    for write in ([], ["--write-baseline"]):
        assert main([*app, "--baseline", prefixed, *write]) == 2
        diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
        assert [(item["subject"], item["unknown_claim"]) for item in diagnostics] == [
            (str(repo / "mobile" / prefixed), _root_relative_claim(repo, "--baseline", prefixed))
        ]
    assert not (repo / "mobile/mobile").exists()


def test_amendment_is_written_and_read_relative_to_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """AD-103: --amendment, and so --write-amendment, follow --baseline's rule."""
    repo = _two_code_bases(tmp_path, monkeypatch, capsys)
    against = ["validate", "--root", "mobile", "--baseline", "architecture-baseline.json"]
    against += ["--against", "HEAD", "--json"]
    decided = ["--decided-by", "Jordan (architect)", "--rationale", "the app's own record"]

    assert main([*against, "--amendment", "widening.json", "--write-amendment", *decided]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] == str(repo / "mobile/widening.json")
    assert not (repo / "widening.json").exists()
    assert main([*against, "--amendment", "widening.json"]) == 0
    capsys.readouterr()

    prefixed = "mobile/widening.json"
    assert main([*against, "--amendment", prefixed]) == 2
    diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
    assert [(item["subject"], item["unknown_claim"]) for item in diagnostics] == [
        (str(repo / "mobile" / prefixed), _root_relative_claim(repo, "--amendment", prefixed))
    ]


@pytest.mark.parametrize("option", ["--baseline", "--amendment"])
@pytest.mark.parametrize(
    ("value", "claim"),
    [
        ("{root}/known-violations.json", "{option} must be a safe POSIX relative path"),
        ("../known-violations.json", "{option} must be a safe POSIX relative path"),
        ("outside.json", "{option} escapes repository root"),
    ],
    ids=["absolute", "parent", "symlink"],
)
def test_root_relative_inputs_stay_inside_the_root(
    tmp_path: Path, capsys: pytest.CaptureFixture, option: str, value: str, claim: str
) -> None:
    """AD-103: the containment --config has, an absolute path included, whatever exists there."""
    root = _prepare_repo(tmp_path, {})
    (tmp_path / "known-violations.json").write_text("{}")
    (root / "known-violations.json").write_text("{}")
    (root / "outside.json").symlink_to(tmp_path / "known-violations.json")
    against = ["--against", "HEAD"] if option == "--amendment" else []
    path = value.format(root=root)

    assert main(["validate", "--root", str(root), *against, option, path, "--json"]) == 2
    diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
    assert [(item["subject"], item["unknown_claim"]) for item in diagnostics] == [
        (
            str(root / path),
            "The architecture contract cannot be validated: " + claim.format(option=option),
        )
    ]


def test_validate_self_and_json_are_identical(capsys: pytest.CaptureFixture) -> None:
    baseline = "architecture-baseline.json"
    assert main(["validate", "--root", str(ROOT), "--baseline", baseline]) == 0
    default = capsys.readouterr().out
    assert main(["validate", "--root", str(ROOT), "--baseline", baseline, "--json"]) == 0
    explicit = capsys.readouterr().out
    assert explicit == default
    result = json.loads(explicit)
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == "UNKNOWN"  # AD-72, see test_validation.py


def test_validate_write_graph_regenerates_both_marked_graphs(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-46/AD-57: a contract edit leaves both marked graphs stale, one flag rewrites both.

    The shop sample's target graph agrees with its observed graph today, so renaming a
    component makes both stale at once, and --write-graph regenerates both in the one page.
    """
    contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    render = next(item for item in contract["components"] if item["label"] == "render")
    render["label"] = "view"
    root = _prepare_repo(tmp_path, {"architecture-contract.json": json.dumps(contract)})
    page = root / "docs/architecture/shop.md"
    before = page.read_text()

    assert main(["validate", "--root", str(root), "--json"]) == 2
    diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
    assert [item["code"] for item in diagnostics] == ["graph.drift", "graph.drift"]
    assert {"archkeel validate --write-graph" in item["remedy"] for item in diagnostics} == {True}

    assert main(["validate", "--root", str(root), "--write-graph", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"] == []
    assert result["artifact"] == "docs/architecture/shop.md"
    # The page's own `flowchart LR` stays; the edges are sorted the way `init` writes them,
    # and both markers' bodies change identically, since the two graphs draw the same edges.
    old_body = (
        "flowchart LR\n"
        "    app --> model\n    app --> store\n    cli --> app\n"
        "    cli --> render\n    render --> model\n    store --> model\n"
    )
    new_body = (
        "flowchart LR\n"
        "    app --> model\n    app --> store\n    cli --> app\n"
        "    cli --> view\n    store --> model\n    view --> model\n"
    )
    assert before.count(old_body) == 2
    assert page.read_text() == before.replace(old_body, new_body)
    assert COMPONENT_GRAPH_MARKER in before and TARGET_GRAPH_MARKER in before

    assert main(["validate", "--root", str(root), "--write-graph", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] is None


def test_validate_baseline_writes_then_gates_on_new_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-52: the red target's whole loop, through the CLI: write, pass, then grow."""
    root = _prepare_repo(tmp_path, {"shop/model/probe.py": _PROBE})
    baseline = root / "known-violations.json"
    arguments = ["validate", "--root", str(root), "--baseline", baseline.name, "--json"]

    assert main([*arguments, "--write-baseline"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] == str(baseline)
    assert json.loads(baseline.read_text())["violations"] == [
        {"count": 1, "rules": ["CONSTRUCT-NO-DYNAMIC"], "subjects": ["shop.model.probe.read"]}
    ]

    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["failures"] == []

    (root / "shop/model/probe_two.py").write_text(_PROBE)
    assert main(arguments) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"] == []
    assert result["failures"] == [
        "new violation: CONSTRUCT-NO-DYNAMIC | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)"
    ]
    assert (result["baseline_new"], result["baseline_resolved"]) == (1, 0)
    before = baseline.read_bytes()
    assert main([*arguments, "--write-baseline"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["artifact"] is None
    assert (result["baseline_new"], result["baseline_resolved"]) == (1, 0)
    assert baseline.read_bytes() == before

    assert main([*arguments, "--write-baseline", "--accept-new"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["artifact"] == str(baseline)
    assert (result["baseline_new"], result["baseline_resolved"]) == (1, 0)


def test_validate_write_baseline_needs_a_baseline_path(capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "--root", str(ROOT), "--write-baseline", "--json"]) == 2
    claim = json.loads(capsys.readouterr().out)["diagnostics"][0]["unknown_claim"]
    assert "--write-baseline needs --baseline" in claim


def test_validate_accept_new_needs_write_baseline(capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "--root", str(ROOT), "--accept-new", "--json"]) == 2
    claim = json.loads(capsys.readouterr().out)["diagnostics"][0]["unknown_claim"]
    assert "--accept-new needs --write-baseline" in claim


def test_validate_configuration_error_has_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["validate", "--root", str(tmp_path), "--json"]) == 2
    diagnostic = json.loads(capsys.readouterr().out)["diagnostics"][0]
    assert diagnostic["kind"] == "contract_invalid"
    assert diagnostic["pointer"] == ""
