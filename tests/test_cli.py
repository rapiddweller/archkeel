# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_report_159_160 import _flow_data

from archkeel.check.validation import COMPONENT_GRAPH_MARKER, TARGET_GRAPH_MARKER
from archkeel.cli import main
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import baseline_bytes
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay, contract_rule_field

ROOT = Path(__file__).parents[1]
_PROBE = (
    "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
    "# SPDX-License-Identifier: MIT\n"
    '"""Getattr probe for the baseline demo."""\n\n'
    "from __future__ import annotations\n\n\n"
    "def read(box: object) -> object:\n"
    '    return getattr(box, "value")\n'
)


def test_json_stdout_preserves_unicode_on_a_legacy_encoded_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project-↔-🚀"
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["report", "--root", str(root), "--json"]) == 2
    stream.flush()
    result = json.loads(output.getvalue().decode("utf-8"))
    assert str(root) in result["diagnostics"][0]["subject"]


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {})
    baseline = str(root / "architecture-baseline.json")
    arguments = ["validate", "--root", str(root), "--baseline", baseline]
    assert main([*arguments, "--write-baseline", "--json"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert main(arguments) == 0
    summary = capsys.readouterr().out
    assert "Independent verdicts" in summary and not summary.startswith("{")
    assert main([*arguments, "--json"]) == 0
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
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
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


_BASELINE_CLAIM = "The validation baseline cannot be read: "
_AMENDMENT_CLAIM = "The contract-widening amendment cannot be read: "


def _refusals(capsys: pytest.CaptureFixture) -> list[tuple[str, str, str]]:
    diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
    return [(item["code"], item["subject"], item["unknown_claim"]) for item in diagnostics]


def _prefixed(repo: Path, value: str) -> str:
    """Why a root-prefixed `value` under `--root mobile`, run from `repo`, names nothing."""
    root = repo / "mobile"
    return (
        f"{value} is relative to --root {root}: it names {root / value}, which does not exist, "
        f"not {repo / value}; pass {value.removeprefix('mobile/')}"
    )


def test_baseline_is_read_relative_to_root_like_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """AD-103 (#149): from the repository root, the app's check reads the app's baseline.

    Before, --baseline was read from the working directory, so this run read the backend's
    file and reported one new and one resolved violation that were a wrong file, not a
    regression. An absolute path inside the root is read as it is. The root-prefixed spelling
    that used to be right names nothing now and is baseline.invalid, instead of being read or
    written one directory too deep, until a folder of that name really holds the file.
    """
    repo = _two_code_bases(tmp_path, monkeypatch, capsys)
    app = ["validate", "--root", "mobile", "--json"]

    for baseline in ("architecture-baseline.json", str(repo / "mobile/architecture-baseline.json")):
        assert main([*app, "--baseline", baseline]) == 0
        result = json.loads(capsys.readouterr().out)
        assert (result["baseline_new"], result["baseline_resolved"], result["failures"]) == (
            0,
            0,
            [],
        )

    prefixed = "mobile/architecture-baseline.json"
    for write in ([], ["--write-baseline"]):
        assert main([*app, "--baseline", prefixed, *write]) == 2
        assert _refusals(capsys) == [
            (
                "baseline.invalid",
                str(repo / "mobile" / prefixed),
                _BASELINE_CLAIM + _prefixed(repo, prefixed),
            )
        ]
    assert not (repo / "mobile/mobile").exists()

    (repo / "mobile/mobile").mkdir()
    shutil.copyfile(repo / prefixed, repo / "mobile" / prefixed)
    assert main([*app, "--baseline", prefixed]) == 0
    capsys.readouterr()

    # From a folder inside the root, a first write lands at the root-relative path.
    monkeypatch.chdir(repo / "mobile/lib")
    fresh = ["validate", "--root", "..", "--baseline", "fresh.json", "--write-baseline", "--json"]
    assert main(fresh) == 0
    assert json.loads(capsys.readouterr().out)["artifact"] == str(repo / "mobile/fresh.json")


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
    for amendment in ("widening.json", str(repo / "mobile/widening.json")):
        assert main([*against, "--amendment", amendment]) == 0
        capsys.readouterr()

    prefixed = "mobile/widening.json"
    assert main([*against, "--amendment", prefixed]) == 2
    assert _refusals(capsys) == [
        (
            "amendment.invalid",
            str(repo / "mobile" / prefixed),
            _AMENDMENT_CLAIM + _prefixed(repo, prefixed),
        )
    ]


@pytest.mark.parametrize(
    ("option", "write", "code", "claim"),
    [
        ("--baseline", ["--write-baseline"], "baseline.invalid", _BASELINE_CLAIM),
        (
            "--amendment",
            ["--write-amendment", "--decided-by", "Jordan", "--rationale", "why"],
            "amendment.invalid",
            _AMENDMENT_CLAIM,
        ),
    ],
    ids=["baseline", "amendment"],
)
@pytest.mark.parametrize(
    "value",
    ["{outside}", "../known-violations.json", "outside.json"],
    ids=["absolute", "parent", "symlink"],
)
def test_root_relative_inputs_stay_inside_the_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    option: str,
    write: list[str],
    code: str,
    claim: str,
    value: str,
) -> None:
    """AD-103: a path that resolves outside the root is refused, read or write, whatever exists
    there; containment is what keeps a write inside the root."""
    root = _prepare_repo(tmp_path, {})
    outside = tmp_path / "known-violations.json"
    outside.write_text("{}")
    (root / "outside.json").symlink_to(outside)
    # --against too: an outside baseline used to be silently left out of its comparison.
    against = ["--against", "HEAD"]
    path = value.format(outside=outside)

    for extra in ([], write):
        assert (
            main(["validate", "--root", str(root), *against, option, path, *extra, "--json"]) == 2
        )
        assert _refusals(capsys) == [
            (
                code,
                str(root / path),
                f"{claim}{path} resolves to {outside}, outside the root {root}",
            )
        ]
    assert outside.read_text() == "{}"


def test_unknown_against_ref_keeps_the_against_invalid_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {})

    assert (
        main(
            [
                "validate",
                "--root",
                str(root),
                "--against",
                "archkeel-review-nonexistent-revision",
                "--json",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
    assert (diagnostic["code"], diagnostic["subject"]) == (
        "against.invalid",
        "archkeel-review-nonexistent-revision",
    )
    assert result["widenings"] is None


def test_validate_against_emits_typed_widening_and_preserves_amendment_status(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {})
    args = ["validate", "--root", str(root), "--against", "HEAD", "--json"]
    apply_overlay(
        root,
        {
            "architecture-contract.json": contract_rule_field(
                "DEP-APP-NO-STORE-SQLITE",
                allowed_sources=["shop.app.maintenance", "shop.app.orders"],
            )
        },
    )

    assert main(args) == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["failures"] == [
        "rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.app.orders'"
    ]
    assert rejected["widenings"] == [
        {
            "code": "ir.widening",
            "subject": "rule DEP-APP-NO-STORE-SQLITE",
            "field": "allowed_sources",
        }
    ]
    assert rejected["amendment_status"] is None

    amendment = [
        "--amendment",
        "widening.json",
        "--write-amendment",
        "--decided-by",
        "Jordan (architect)",
        "--rationale",
        "Orders needs the sqlite exemption during the migration.",
    ]
    assert main([*args, *amendment]) == 0
    assert json.loads(capsys.readouterr().out)["widenings"] == []

    apply_overlay(
        root,
        {
            "architecture-contract.json": contract_rule_field(
                "DEP-APP-NO-STORE-SQLITE",
                allowed_sources=[
                    "shop.app.maintenance",
                    "shop.app.orders",
                    "shop.model.entities",
                ],
            )
        },
    )
    assert main([*args, "--amendment", "widening.json"]) == 1
    stale = json.loads(capsys.readouterr().out)
    assert stale["amendment_status"] == "stale"
    assert stale["widenings"] == [
        {
            "code": "ir.widening",
            "subject": "rule DEP-APP-NO-STORE-SQLITE",
            "field": "allowed_sources",
        },
    ]


def test_validate_against_codes_added_requires_permission_and_baseline_growth(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    requires_root = tmp_path / "requires"
    requires_root.mkdir()
    root = _prepare_repo(requires_root, {})
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    app = next(item for item in contract["components"] if item["label"] == "app")
    app["requires"] = [
        {
            "component": "store",
            "rationale": "A test change that adds a dependency permission.",
            "decided_by": "architect",
        }
    ]
    contract_path.write_text(json.dumps(contract))
    args = ["validate", "--root", str(root), "--against", "HEAD", "--json"]

    assert main(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["widenings"] == [
        {
            "code": "ir.widening",
            "subject": "component 'app'",
            "field": "requires",
        }
    ]

    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    root = _prepare_repo(baseline_root, {})
    baseline = root / "known-violations.json"
    baseline.write_bytes(baseline_bytes(()))
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "empty baseline"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    baseline.write_bytes(
        baseline_bytes(
            (
                KnownViolation(
                    ViolationFingerprint(("CONSTRUCT-NO-DYNAMIC",), ("shop.model.probe.read",)), 1
                ),
            )
        )
    )

    assert (
        main(
            [
                "validate",
                "--root",
                str(root),
                "--baseline",
                str(baseline),
                "--against",
                "HEAD",
                "--json",
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["widenings"] == [
        {
            "code": "ir.widening",
            "subject": "CONSTRUCT-NO-DYNAMIC | shop.model.probe.read",
            "field": "count",
        }
    ]


def test_validate_reports_architect_responsibilities_but_keeps_drafts_usable(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {})
    assert main(["validate", "--root", str(root), "--json"]) == 0
    before = json.loads(capsys.readouterr().out)
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    components = contract["components"]
    components[0]["responsibilities"] = []  # architect-decided and missing
    components[2]["responsibilities"] = []
    components[2]["decided_by"] = "agent"  # generated draft remains usable
    components[3]["responsibilities"] = []
    components[3].pop("decided_by")  # undecided is not an architect decision
    contract_path.write_text(json.dumps(contract))

    nested_path = root / "shop/store/architecture-contract.json"
    nested = json.loads(nested_path.read_text())
    nested["components"][0]["responsibilities"] = []
    nested_path.write_text(json.dumps(nested))

    assert main(["validate", "--root", str(root), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    missing = [
        item for item in result["diagnostics"] if item.get("code") == "responsibility.missing"
    ]
    assert sorted(
        (item["subject"], item["pointer"], item["contract_path"]) for item in missing
    ) == [
        (
            "api in shop/store/architecture-contract.json",
            "/components/0/responsibilities",
            "shop/store/architecture-contract.json",
        ),
        ("model", "/components/0/responsibilities", "architecture-contract.json"),
    ]
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == before["declared_rules"]
    assert result["rule_assessments"] == before["rule_assessments"]


def test_validate_includes_recorded_import_location_in_json_and_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {"shop/model/probe.py": "from shop.store import repository\n"})
    args = ["validate", "--root", str(root)]

    assert main([*args, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    finding = next(item for item in result["diagnostics"] if item.get("code") == "rule.violated")
    assert finding["subject"] == "DEP-MODEL-NO-STORE"
    assert finding["locations"] == [{"path": "shop/model/probe.py", "line": 1}]

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert main(args) == 2
    assert "shop/model/probe.py:1" in capsys.readouterr().out


def test_validate_default_and_explicit_json_are_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _prepare_repo(tmp_path, {})
    baseline = str(root / "architecture-baseline.json")
    arguments = ["validate", "--root", str(root), "--baseline", baseline]
    assert main([*arguments, "--write-baseline", "--json"]) == 0
    capsys.readouterr()
    assert main(arguments) == 0
    default = capsys.readouterr().out
    assert main([*arguments, "--json"]) == 0
    explicit = capsys.readouterr().out
    assert explicit == default
    result = json.loads(explicit)
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == "UNKNOWN"


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
    arguments = ["validate", "--root", str(root), "--baseline", str(baseline), "--json"]

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
    assert result["failures"][-1].startswith("--write-baseline refused: ")
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
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
    assert diagnostic["kind"] == "contract_invalid"
    assert diagnostic["pointer"] == ""


@pytest.fixture(scope="module")
def heading_check_repository(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[str]]:
    import shlex

    from fixtures.reproduce_milestone1 import reproduce

    output = tmp_path_factory.mktemp("heading-protocol")
    reproduce(output)
    command = next(
        item["command"]
        for item in json.loads((output / "commands.json").read_text())
        if "C-host-records.json" in item["command"]
    )
    return output / "C", shlex.split(command)[1:]


@pytest.mark.parametrize("command", ["report", "check"])
@pytest.mark.parametrize(
    "metadata,heading",
    [
        ('[project]\nname = "Declared-Project"\nrequires-python = ">=3.11"\n', "Declared-Project"),
        ('[project]\nname = "<unsafe>"\n', "sample"),
        ("[project]\nname = 42\n", "sample"),
        ("[project] broken", "sample"),
        (None, "sample"),
    ],
)
def test_html_heading_uses_valid_project_name_with_namespace_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    command: str,
    metadata: str | None,
    heading: str,
    heading_check_repository: tuple[Path, list[str]],
) -> None:
    root, check_args = heading_check_repository
    metadata_path = root / "pyproject.toml"
    if metadata is not None:
        metadata_path.write_text(metadata)
    else:
        metadata_path.unlink(missing_ok=True)
    output = tmp_path / "result.json"
    args = ["report", "--root", str(root)] if command == "report" else check_args
    exit_code = main([*args, "--output", str(output), "--json"])
    assert exit_code in (0, 2)
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == command
    html = (tmp_path / f"result.{command}.html").read_text()
    assert f"<h1>{heading}</h1>" in html
    assert "<unsafe>" not in html


def test_report_heading_does_not_read_project_metadata_outside_the_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    root = _prepare_repo(tmp_path, {})
    external = tmp_path / "external.toml"
    external.write_text('[project]\nname = "External-Project"\nrequires-python = ">=3.11"\n')
    metadata = root / "pyproject.toml"
    metadata.unlink()
    metadata.symlink_to(external)
    output = tmp_path / "report.json"
    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) in (0, 2)
    capsys.readouterr()
    assert "<h1>shop</h1>" in (tmp_path / "report.report.html").read_text()


@pytest.mark.parametrize("only", [None, "architecture"])
def test_native_report_publishes_one_linked_offline_detail_snapshot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    only: str | None,
) -> None:
    root = _prepare_repo(tmp_path, {})
    output = tmp_path / "published" / "architecture.json"
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("COLUMNS", "400")
    arguments = ["report", "--root", str(root), "--output", str(output)]
    if only is not None:
        arguments.extend(("--only", only))
    assert main(arguments) == 0
    receipt = capsys.readouterr().out
    main_page = output.with_suffix(".report.html")
    assert output.exists() and main_page.exists()
    details = tuple(output.parent.glob("architecture.detail*.html"))
    if only is not None:
        assert not details
        return
    page = main_page.read_text()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    atlas = json.loads(match.group(1))["atlas"]
    assert atlas["components"] and atlas["unassigned_detail_href"] == "?component=unassigned"
    assert {item.name for item in details} == {atlas["detail_page"]}
    detail_path = output.parent / atlas["detail_page"]
    detail = detail_path.read_text()
    navigation = _flow_data(detail)["navigation"]
    assert navigation["main_href"] == main_page.name
    assert (output.parent / navigation["main_href"]).is_file()
    assert navigation["component_id"] is None
    assert f'href="{output.name}"' in detail
    assert "default-src 'none'" in detail and "fetch(" not in detail
    assert detail_path.name in receipt


def test_check_heading_symlink_loop_preserves_saved_and_stdout_verdicts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    heading_check_repository: tuple[Path, list[str]],
) -> None:
    root, check_args = heading_check_repository
    metadata = root / "pyproject.toml"
    original = metadata.read_bytes() if metadata.exists() else None
    metadata.unlink(missing_ok=True)
    metadata.symlink_to("pyproject.toml")
    output = tmp_path / "result.json"
    try:
        exit_code = main([*check_args, "--output", str(output), "--json"])
    finally:
        metadata.unlink()
        if original is not None:
            metadata.write_bytes(original)
    saved = json.loads(output.read_text())
    emitted = json.loads(capsys.readouterr().out)
    assert saved["exit_code"] == emitted["exit_code"] == exit_code == 0
    for key in ("observation_complete", "declared_rules", "expectation_fulfilled"):
        assert saved[key] == emitted[key] == "PASS"
    assert "<h1>sample</h1>" in (tmp_path / "result.check.html").read_text()
