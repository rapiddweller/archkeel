# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: `archkeel explore` shows the as-is code of a repository that has no contract."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from test_result_schema import _validator

from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.report_graph import architecture_report
from fixtures.architecture_demo import CATALOG, replay

_SOURCES = {
    "shop/__init__.py": "",
    "shop/app/__init__.py": "",
    "shop/app/orders.py": (
        "from shop.store.repository import save\n\n\ndef place() -> int:\n    return save(1)\n"
    ),
    "shop/store/__init__.py": "",
    "shop/store/repository.py": "def save(value: int) -> int:\n    return value\n",
    "shop/cli/__init__.py": "",
    "shop/cli/__main__.py": "from shop.app.orders import place\n\nplace()\n",
    "pyproject.toml": '[project]\nname = "shop"\nrequires-python = ">=3.11"\n',
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _repository(root: Path, files: dict[str, str] = _SOURCES, *, commit: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "explore@example.invalid")
    _git(root, "config", "user.name", "Archkeel explore")
    if commit:
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "snapshot", "--allow-empty")
    return root


def _explore(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict]:
    code = main(["explore", *args, "--json"])
    return code, json.loads(capsys.readouterr().out)


def _snapshot(path: Path):
    return parse_observation(decode_canonical_model(decode_json(path.read_bytes())))


def _tree_digest(root: Path) -> dict[str, str]:
    """Every file below the root, ignored ones too; Git's own folder is not repository content."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_explore_shows_a_repository_without_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    code, payload = _explore(capsys, "--root", str(root))

    assert code == 0, payload
    assert payload["target"] == "unavailable"
    assert payload["declared_rules"] == "UNKNOWN"
    assert payload["rule_assessments"] == []
    assert payload["open_decisions"] == []
    assert payload["scan_roots"] == ["shop"]
    validator = _validator("command-result-11.0.schema.json")
    assert validator.is_valid(payload)
    assert not validator.is_valid({**payload, "declared_rules": "PASS"})
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    artifact = tmp_path / "cache" / "archkeel" / "explore" / key / "architecture.json"
    assert payload["artifact"] == str(artifact)
    model = _snapshot(artifact)
    assert model.contract.path == "archkeel-explore-layout.json"
    memberships = {item.component_id for item in architecture_report(model).memberships}
    assert memberships == {"COMP-APP", "COMP-CLI", "COMP-STORE"}
    page = artifact.with_name("architecture.report.html").read_text()
    assert page.index('id="inventory-heading"') < page.index('id="findings-heading"')
    assert "Target unavailable: no rule is declared, so no rule passes or fails" in page
    assert "3 layout components" in page
    assert "shop.cli.__main__" in page
    assert "PASS · Rules" not in page


def test_explore_never_writes_into_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    (root / ".gitignore").write_text("ignored.txt\n")
    (root / "ignored.txt").write_text("kept\n")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    tree, status = _tree_digest(root), _git(root, "status", "--porcelain", "--ignored")

    assert _explore(capsys, "--root", str(root))[0] == 0
    code, payload = _explore(capsys, "--root", str(root), "--output", str(root / "out"))

    assert code == 2
    assert "inside the analyzed repository" in payload["diagnostics"][0]["unknown_claim"]
    assert _tree_digest(root) == tree
    assert _git(root, "status", "--porcelain", "--ignored") == status


def test_a_saved_explore_snapshot_gives_no_rule_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    snapshot = str(tmp_path / "out" / "architecture.json")

    assert main(["report", "--input", snapshot, "--json"]) == 0
    saved = json.loads(capsys.readouterr().out)
    query = ["report", "--input", snapshot, "--only", "architecture", "--component", "COMP-STORE"]
    assert main([*query, "--json"]) == 0
    component = json.loads(capsys.readouterr().out)

    assert (saved["target"], saved["declared_rules"]) == ("unavailable", "UNKNOWN")
    assert component["declared_rules"] == "UNKNOWN"
    assert [item["id"] for item in component["architecture_projection"]["components"]] == [
        "COMP-STORE"
    ]
    query[-1] = "COMP-NOPE"
    assert main([*query, "--json"]) == 2
    fabricated = json.loads(capsys.readouterr().out)
    assert [item["kind"] for item in fabricated["diagnostics"]] == ["filter_unknown"]


def test_explore_records_the_worktree_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    output = tmp_path / "out"
    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0
    clean = _snapshot(output / "architecture.json").source
    (root / "shop/store/repository.py").write_text("def save(value: int) -> int:\n    return 2\n")

    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0
    dirty = _snapshot(output / "architecture.json").source

    assert (clean.dirty, dirty.dirty) == (False, True)
    assert clean.git_head == dirty.git_head
    assert clean.source_digest != dirty.source_digest


@pytest.mark.parametrize(
    ("marker", "named"),
    [(None, "none"), ("tsconfig.json", "tsconfig.json"), ("pubspec.yaml", "pubspec.yaml")],
)
def test_explore_without_a_python_package_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], marker: str | None, named: str
) -> None:
    root = _repository(tmp_path / "repo", {marker: "{}\n"} if marker else {})
    output = tmp_path / "out"
    output.mkdir()
    (output / "architecture.json").write_text("{}")

    code, payload = _explore(capsys, "--root", str(root), "--output", str(output))

    assert code == 2
    [diagnostic] = payload["diagnostics"]
    assert diagnostic["kind"] == "scope_empty"
    assert named in diagnostic["unknown_claim"]
    assert not (output / "architecture.json").exists()


def test_explore_without_a_commit_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo", commit=False)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    assert code == 2
    assert "Git commit" in payload["diagnostics"][0]["remedy"]


def test_explore_collects_the_source_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    collect = PythonProviderCollector.collect
    calls: list[object] = []

    def counted(self: PythonProviderCollector, request: object):  # type: ignore[no-untyped-def]
        calls.append(request)
        return collect(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(PythonProviderCollector, "collect", counted)

    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    assert len(calls) == 1


def test_report_on_a_contract_without_a_rule_gives_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-SHOP",
                "label": "shop",
                "role": "component",
                "packages": ["shop"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture.md"],
            }
        ],
        "rules": [],
    }
    files = {
        **_SOURCES,
        "docs/architecture.md": "# Architecture\n",
        "architecture-contract.json": json.dumps(contract),
        "archkeel.toml": '[scan]\nroots = ["shop"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n',
    }
    root = _repository(tmp_path / "repo", files)

    code = main(["report", "--root", str(root), "--output", str(tmp_path / "a.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert (payload["target"], payload["declared_rules"]) == ("unavailable", "UNKNOWN")


def test_the_explore_demo_row_replays_without_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(item for item in CATALOG if item.id == "explore-contract-free")
    artifact = tmp_path / "explore" / "architecture.json"

    assert replay(variant.id, artifact) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["declared_rules"] == variant.expected_declared_rules
    assert payload["target"] == "unavailable"
    assert 'id="inventory-heading"' in artifact.with_name("architecture.report.html").read_text()
    assert not (variant.fixture / "archkeel.toml").exists()
