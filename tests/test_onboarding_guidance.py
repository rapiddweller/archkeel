# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""First-run guidance must lead to an executable, decided target."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from archkeel.check.onboarding import run_init
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import CompleteRequiresRule, ForbiddenDependencyRule
from archkeel.render.summary import init_summary
from fixtures.reproduce_onboarding import SHOP, _architect_decides, _repository


def repository(root: Path, *, cyclic: bool = False) -> Path:
    files = {
        "src/demo/__init__.py": "",
        "src/demo/domain/__init__.py": "",
        "src/demo/domain/api.py": '__all__ = ["VALUE"]\nVALUE = 1\n',
        "src/demo/storage/__init__.py": "",
        "src/demo/storage/api.py": "from demo.domain import api\nVALUE = api.VALUE\n",
        "pyproject.toml": '[project]\nname = "demo"\nrequires-python = ">=3.11"\n',
    }
    if cyclic:
        files["src/demo/domain/api.py"] += "from demo.storage import api\nOTHER = api.VALUE\n"
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "guidance@example.invalid"),
        ("config", "user.name", "Guidance test"),
        ("add", "."),
        ("-c", "commit.gpgsign=false", "commit", "-qm", "source"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


@pytest.mark.parametrize("command", ["report", "validate"])
def test_missing_default_config_names_setup_and_restore(
    tmp_path: Path, capsys: pytest.CaptureFixture, command: str
) -> None:
    assert main([command, "--root", str(tmp_path), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
    assert "archkeel init" in diagnostic["remedy"]
    assert "restore" in diagnostic["remedy"].lower()
    assert diagnostic["kind"] == ("contract_invalid" if command == "validate" else "parse_error")
    if command == "validate":
        assert diagnostic["code"] == "contract.invalid"


@pytest.mark.parametrize("command", ["report", "validate"])
@pytest.mark.parametrize("config", ["custom.toml", "archkeel.toml"])
def test_bad_config_does_not_suggest_overwriting_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture, command: str, config: str
) -> None:
    if config == "archkeel.toml":
        (tmp_path / config).write_text("[broken")
    assert main([command, "--root", str(tmp_path), "--config", config, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "archkeel init" not in result["diagnostics"][0]["remedy"]
    if config == "custom.toml":
        assert "--config" in result["diagnostics"][0]["remedy"]


@pytest.mark.parametrize("config", ["../archkeel.toml", "archkeel.toml"])
def test_unsafe_config_keeps_corrective_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture, config: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "archkeel.toml"
    outside.write_text("[scan]")
    if config == "archkeel.toml":
        (root / config).symlink_to(outside)
    assert main(["report", "--root", str(root), "--config", config, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "archkeel init" not in result["diagnostics"][0]["remedy"]
    assert (
        "escapes" in result["diagnostics"][0]["unknown_claim"]
        or "safe" in result["diagnostics"][0]["unknown_claim"]
    )


@pytest.mark.parametrize("unborn", [False, True])
def test_init_without_head_names_git_prerequisite(
    tmp_path: Path, capsys: pytest.CaptureFixture, unborn: bool
) -> None:
    root = repository(tmp_path)
    shutil.rmtree(root / ".git")
    if unborn:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    assert main(["init", "--root", str(root), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    remedy = result["diagnostics"][0]["remedy"]
    assert "git init" in remedy and "commit" in remedy
    assert "archkeel init" in remedy
    assert not (root / "archkeel.toml").exists()


@pytest.mark.parametrize("cyclic", [False, True])
def test_successful_init_is_neutral_and_names_observed_cycles(tmp_path: Path, cyclic: bool) -> None:
    root = repository(tmp_path, cyclic=cyclic)
    result, files = run_init(root, source=None, namespace=None, force=False, analyzer=observe)
    summary = init_summary(result)
    assert result.exit_code == 0 and result.observation_complete == "PASS"
    assert result.diagnostics == () and result.open_decision_count == 2
    assert len(result.open_decisions) == (2 if cyclic else 1)
    assert result.open_decisions_complete is cyclic
    assert summary.decision.state == "info" and summary.decision.label == "DRAFT"
    assert summary.verdicts[0].value == "PASS"
    assert result.measurements is not None
    count = result.measurements.scalars.cycle_edges
    assert count is not None and (count > 0) == cyclic
    assert ("no_component_cycles" in summary.sentence) == cyclic
    assert (f"{count} cycle edge" in summary.sentence) == cyclic
    kinds = {item["kind"] for item in json.loads(files["architecture-contract.json"])["rules"]}
    assert ("no_component_cycles" in kinds) != cyclic


@pytest.mark.parametrize("agent, invocation", [("codex", "$archkeel"), ("claude", "/archkeel")])
def test_skill_install_names_invocation_only_in_terminal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
    invocation: str,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert main(["skill", "install", agent, "--root", str(tmp_path)]) == 0
    assert f"Use {invocation} " in capsys.readouterr().out
    assert main(["skill", "install", agent, "--root", str(tmp_path), "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"command", "exit_code", "path"}


@pytest.mark.parametrize("document", ["docs/onboarding.md", "skills/archkeel/SKILL.md"])
def test_dependency_examples_execute_to_pass_and_name_unapproved_edge(
    tmp_path: Path, capsys: pytest.CaptureFixture, document: str
) -> None:
    text = (Path(__file__).parents[1] / document).read_text()
    fragments = [json.loads(item) for item in re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)]
    assert len(fragments) == 2
    root = repository(tmp_path)
    assert main(["init", "--root", str(root), "--json"]) == 0
    capsys.readouterr()
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    storage = next(item for item in contract["components"] if item["label"] == "storage")
    storage.update(fragments[0])
    for component in contract["components"]:
        if "public" in component:
            component["decided_by"] = "architect"
    for rule in contract["rules"]:
        rule["rationale"] = {
            "complete_assignment": "Each source module has one owner.",
            "no_component_cycles": "Domain stays independent of persistence.",
            "interface_boundary": "Storage uses the domain API so domain internals can change.",
        }[rule["kind"]]
        rule["decided_by"] = "architect"
    contract["rules"].append(fragments[1])
    path.write_text(json.dumps(contract))
    assert main(["validate", "--root", str(root), "--json"]) == 0
    valid = json.loads(capsys.readouterr().out)
    assert not valid["diagnostics"] and not valid["open_decisions"]
    assert main(["report", "--root", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["declared_rules"] == "PASS"
    (root / "src/demo/domain/api.py").write_text(
        "from demo.storage import api\nVALUE = api.VALUE\n"
    )
    assert main(["report", "--root", str(root), "--json"]) == 0
    failed = json.loads(capsys.readouterr().out)
    assert failed["declared_rules"] == "FAIL"
    assert any(
        item["id"] == fragments[1]["id"] and item["status"] == "FAIL"
        for item in failed["rule_assessments"]
    )


def test_demo_uses_approved_requires_and_preserves_narrow_exclusions(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    step = _architect_decides(root)
    contract = parse_contract(decode_json((root / "architecture-contract.json").read_bytes()))
    assert step.outcome == "exit 0, declared_rules PASS, 6 requires entries"
    assert {
        (item.label, entry.component)
        for item in contract.components
        for entry in item.requires or ()
    } == {
        ("store", "model"),
        ("app", "model"),
        ("app", "store"),
        ("render", "model"),
        ("cli", "app"),
        ("cli", "render"),
    }
    assert any(isinstance(item, CompleteRequiresRule) for item in contract.rules)
    assert {item.id for item in contract.rules if isinstance(item, ForbiddenDependencyRule)} == {
        "DEP-APP-NO-STORE-SQLITE",
        "DEP-APP-NO-STORE-BACKEND",
        "DEP-STORE-NO-MONEY",
    }
    assert all(
        entry.rationale and entry.decided_by == "architect"
        for item in contract.components
        for entry in item.requires or ()
    )


def test_demo_owns_the_namespace_facade_without_expanding_package_permissions(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    undecided, _ = run_report(root, config=SHOP, analyzer=observe)
    assert undecided.declared_rules == "UNKNOWN"
    assessment = next(
        item for item in undecided.rule_assessments if item.id == "store:STORE-REQUIRES-COMPLETE"
    )
    assert assessment.status == "UNKNOWN" and "shop.store" in assessment.reason
    assert "exact_modules" in assessment.reason
    _architect_decides(root)
    decided, _ = run_report(root, config=SHOP, analyzer=observe)
    assert decided.declared_rules == "PASS"
    inner = parse_contract(
        decode_json((root / "shop/store/architecture-contract.json").read_bytes())
    )
    repository = next(item for item in inner.components if item.label == "repository")
    assert repository.exact_modules == ("shop.store",)
    assert repository.packages == ("shop.store.repository",)
    assert [entry.component for entry in repository.requires or ()] == ["backend", "codec"]


def test_dart_draft_keeps_unmeasured_scalars_unavailable(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "lib").mkdir()
    (root / "lib/api.dart").write_text("const value = 1;\n")
    result, _ = run_init(
        root, source=("lib",), namespace="demo", force=False, analyzer=observe, language="dart"
    )
    assert result.exit_code == 0 and not result.diagnostics
    assert result.measurements is not None
    scalars = result.measurements.scalars
    assert scalars.cycle_edges == 0
    assert scalars.calls_unresolved is None and scalars.typing_positions is None
    assert result.measurements.calls_total is None


def test_init_api_returns_the_same_typed_git_remedy(tmp_path: Path) -> None:
    from archkeel.ir.model import DiagnosticError

    root = repository(tmp_path)
    shutil.rmtree(root / ".git")
    with pytest.raises(DiagnosticError) as failure:
        run_init(root, source=None, namespace=None, force=False, analyzer=observe)
    assert failure.value.diagnostic.kind == "parse_error"
    assert "git init" in failure.value.diagnostic.remedy
    assert "commit" in failure.value.diagnostic.remedy
