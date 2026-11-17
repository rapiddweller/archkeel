# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-638: `validate` and `report` without `archkeel.toml` draft it, say so, and never overwrite.

Plants: a Python package, three top-level Python packages, a Cargo workspace and a package.json
workspace. The first verdict of a draft is UNKNOWN with the open decisions, never a refusal.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import core_only
from tests.test_cli_init import plant

GIT = ["git", "-c", "user.email=a@b", "-c", "user.name=a"]
CRATE = '[package]\nname = "{}"\nversion = "0.1.0"\nedition = "2021"\n'
IMPORT = 'import {a} from "../../api-core/src/index";\nexport const w = a;\n'
CONFIG = '{"compilerOptions": {"strict": true, "noEmit": true, "moduleResolution": "Node"}, '
OPEN = "a component without a written responsibility"


def commit(root: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "plant"], cwd=root, check=True)
    return root


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def several_packages(root: Path) -> Path:
    write(root, {f"src/{n}/__init__.py": "" for n in ("alpha", "beta", "gamma")})
    write(
        root,
        {
            "src/alpha/a.py": "from beta import x\n",
            "src/beta/x.py": "x = 1\n",
        },
    )
    write(
        root,
        {"pyproject.toml": '[project]\nname = "p"\nversion = "0"\nrequires-python = ">=3.11"\n'},
    )
    return commit(root)


def cargo_workspace(root: Path) -> Path:
    write(
        root,
        {
            "Cargo.toml": '[workspace]\nmembers = ["crates/core-a", "crates/util"]\n',
            "crates/core-a/Cargo.toml": CRATE.format("core-a")
            + '[dependencies]\nutil = { path = "../util" }\n',
            "crates/core-a/src/lib.rs": "pub fn run() -> i32 { util::one() }\n",
            "crates/util/Cargo.toml": CRATE.format("util"),
            "crates/util/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
            ".gitignore": "target\n",
        },
    )
    return commit(root)


def node_workspace(root: Path) -> Path:
    write(
        root,
        {
            "package.json": '{"name": "mono", "private": true, "workspaces": ["packages/*"]}',
            "packages/web/package.json": '{"name": "@m/web", "version": "1.0.0"}',
            "packages/api-core/package.json": '{"name": "@m/api-core", "version": "1.0.0"}',
            "packages/web/src/index.ts": IMPORT,
            "packages/api-core/src/index.ts": "export const a = 1;\n",
            "tsconfig.json": CONFIG + '"include": ["packages/**/*.ts"]}',
            ".gitignore": "node_modules\n",
        },
    )
    return commit(root)


def run(capsys: pytest.CaptureFixture[str], root: Path, *argv: str) -> tuple[int, str]:
    code = core_only.run([*argv, "--root", str(root)])
    return code, capsys.readouterr().out


def drafted(root: Path) -> set[str]:
    names = ("archkeel.toml", "architecture-contract.json", "docs/architecture/architecture.md")
    return {name for name in names if (root / name).exists()}


@pytest.mark.parametrize("command", ["validate", "report"])
def test_a_project_without_configuration_gets_the_draft_the_block_and_a_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    root = plant(tmp_path)
    code, text = run(capsys, root, command, "--text")
    assert code == 2, text
    assert text.startswith("ArchKeel created archkeel.toml and a first contract draft with 4 ")
    assert "Review the open decisions, then run archkeel validate again." in text
    # The words say where the decisions are, not that a list follows (a refusal prints none).
    assert "TODO entries of the contract files above" in text and "listed below" not in text
    assert len(drafted(root)) == 3 and OPEN in text and "REFUSED" not in text
    # The second run is a normal run: no block, the same open decisions.
    code, again = run(capsys, root, command, "--text")
    assert code == 2 and "ArchKeel created" not in again and OPEN in again


def test_the_json_run_carries_the_block_in_the_init_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(capsys, plant(tmp_path), "validate", "--json")
    document = json.loads(out)
    assert code == 2 and document["status"] == "UNKNOWN"
    assert document["init"]["written"][0] == "archkeel.toml"
    assert document["init"]["components"] == ["billing", "catalog", "orders", "root"]


def test_an_existing_file_is_never_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path)
    contract = root / "architecture-contract.json"
    contract.write_text('{"mine": true}', encoding="utf-8")
    run(capsys, root, "validate", "--text")
    assert contract.read_text(encoding="utf-8") == '{"mine": true}'
    assert (root / "archkeel.toml").is_file() and not (root / "docs").exists()
    config = (root / "archkeel.toml").read_bytes()
    code, out = run(capsys, root, "validate", "--text")
    assert (root / "archkeel.toml").read_bytes() == config and "ArchKeel created" not in out
    assert code == 2


@pytest.mark.parametrize("how", ["flag", "variable"])
def test_opting_out_writes_nothing_and_says_what_the_layout_gives(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    how: str,
) -> None:
    root = plant(tmp_path)
    if how == "variable":
        monkeypatch.setenv("ARCHKEEL_NO_INIT", "1")
    code, text = run(capsys, root, "validate", "--text", *(["--no-init"] if how == "flag" else []))
    assert code == 2 and drafted(root) == set()
    assert "nothing was written" in text and "billing, catalog, orders, root" in text
    assert "archkeel init" in text


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a folder that is read-only")
def test_a_folder_that_cannot_be_written_gets_no_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path)
    root.chmod(0o555)
    try:
        code, text = run(capsys, root, "validate", "--text")
    finally:
        root.chmod(0o755)
    assert code == 2 and drafted(root) == set() and "nothing was written (cannot write" in text


def test_a_layout_that_cannot_be_drafted_is_refused_with_the_guide(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = commit(write(tmp_path, {"README.md": "x\n"}))
    code, text = run(capsys, root, "validate", "--text")
    assert code == 2 and drafted(root) == set() and "onboarding.md" in text


@pytest.mark.parametrize(
    ("make", "names"),
    [
        (several_packages, ["alpha", "beta", "gamma"]),
        (cargo_workspace, ["core_a", "util"]),
        (node_workspace, ["api_core", "web"]),
    ],
    ids=["three-python-packages", "cargo-workspace", "node-workspace"],
)
def test_each_layout_gets_one_component_for_each_part_and_no_scope_defect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make: object, names: list[str]
) -> None:
    root = make(tmp_path)  # type: ignore[operator]
    code, out = run(capsys, root, "validate", "--json")
    document = json.loads(out)
    assert document["init"]["components"] == names, out
    assert (code, document["status"]) == (2, "UNKNOWN"), out
    shown = json.dumps(document["frame"].get("rules")) + json.dumps(document["gaps"])
    # Every component owns its modules: no violation, no unscanned package, no foreign namespace.
    assert not document["frame"]["violations"], out
    assert not document["frame"]["unknown_kinds"], out  # both rules are decided by the core
    for defect in ("unscanned", "outside namespace", "no unique owner", "refused"):
        assert defect not in shown, (defect, out)
    _, text = run(capsys, root, "validate", "--text", "--all")
    assert text.count("The architect-decided") == len(names), text


def test_init_prints_text_by_default_and_json_on_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path)
    code, text = run(capsys, root, "init")
    assert code == 0 and text.startswith("Drafted 3 files for python")
    assert "Components (4): billing, catalog, orders, root" in text and "Guide: " in text
    (root / "archkeel.toml").unlink()
    code, out = run(capsys, root, "init", "--json")
    assert code == 0 and json.loads(out)["files"] == ["archkeel.toml"]


def test_a_folder_inside_a_repository_is_not_the_project_of_an_explicit_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--root` names the project: a parent repository is never written into."""
    repository = plant(tmp_path)
    inner = repository / "inner"
    inner.mkdir()
    code, out = run(capsys, inner, "validate", "--json")
    assert code == 2 and "init" not in json.loads(out) and drafted(repository) == set()


CYCLE_NOTE = (
    "This is a real cycle in your code that the drafted rule 'no component cycles' catches; "
    "keep it as a finding, or change the rule in the contract."
)


def test_the_first_run_says_that_a_cycle_is_real_and_a_later_run_does_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Day one: the first validate of an auto-init draft that finds a cycle says plainly that the
    cycle is in the code and that the drafted rule catches it. The cycle stays a FAIL."""
    root = plant(tmp_path)
    write(root, {"src/shop/catalog/back.py": "from shop.billing import pay\n"})
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "cycle"], cwd=root, check=True)
    code, text = run(capsys, root, "validate", "--text")
    assert code == 1 and "dependency cycle" in text, text
    assert text.count(CYCLE_NOTE) == 1, text
    code, again = run(capsys, root, "validate", "--text")
    assert code == 1 and "dependency cycle" in again and CYCLE_NOTE not in again
