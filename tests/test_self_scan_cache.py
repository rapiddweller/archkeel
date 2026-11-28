# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1420: a saved self-scan result is reused only when every input of the scan has its content.

Each case runs `tools/self_scan_cache.py` on a small Git repository with a result of the shape that
the core writes. A hit needs the same static inputs and the same documents. Any other case is a miss
(exit 1) and the caller scans. A result that does not show its inputs covered is never saved.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

TOOL = Path(__file__).parents[1] / "tools/self_scan_cache.py"
FILES = {
    "native/src/lib.rs": "pub fn a() {}\n",
    "native/archkeel.toml": "[scan]\n",
    "native/architecture-contract.json": json.dumps(
        {"provenance": ["docs/guide.md", "not a path:"]}
    ),
    "src/archkeel/cli.py": "x = 1\n",
    "studio/src/a.ts": "export const a = 1;\n",
    "schema/frame.json": "{}\n",
    "tools/rustc-facts/driver.rs": "fn main() {}\n",
    "docs/architecture/architecture-system.json": "{}\n",
    "docs/architecture/shell.toml": "[scan]\n",
    "docs/architecture/target/shell-contract.json": "{}\n",
    "docs/guide.md": "cited\n",
    "docs/other.md": "not cited\n",
    "pyproject.toml": "[project]\n",
    "uv.lock": "lock\n",
    "Makefile": "all:\n",
    "README.md": "readme\n",
}
RESULT: dict[str, Any] = {
    "rules": {"R": ["forbidden_dependency", "UNKNOWN"]},
    "topology": {
        "total": {"modules": 2},
        "modules": [{"path": "native/src/lib.rs"}, {"path": "src/archkeel/cli.py"}],
    },
    "system": {
        "document": "docs/architecture/architecture-system.json",
        "parts": [{"config": "docs/architecture/shell.toml"}, {"config": "native/archkeel.toml"}],
    },
    "self_test": {"collect": {"contract_files": {"docs/guide.md": "0" * 64}}},
}


def tool(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args, "--root", str(root)], capture_output=True, text=True
    )


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for name, text in FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(tmp_path / "repo", "init", "-q")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    return root


def saved(root: Path, result: dict[str, Any] | None = None) -> Path:
    directory = root.parent / "entry"
    document = root.parent / "result.json"
    document.write_text(json.dumps(RESULT if result is None else result))
    done = tool(root, "save", "--result", str(document), "--dir", str(directory))
    assert done.returncode == 0, done.stderr
    return directory


def reuse(root: Path, directory: Path) -> subprocess.CompletedProcess[str]:
    return tool(root, "hit", "--dir", str(directory), "--out", str(root.parent / "out.json"))


def test_the_same_inputs_reuse_the_saved_result_byte_for_byte(repo: Path) -> None:
    directory = saved(repo)
    done = reuse(repo, directory)
    assert done.returncode == 0, done.stderr
    assert (repo.parent / "out.json").read_text() == json.dumps(RESULT)


@pytest.mark.parametrize("name", ["docs/other.md", "README.md", "docs/img.png"])
def test_a_file_that_the_scan_does_not_read_keeps_the_key(repo: Path, name: str) -> None:
    directory = saved(repo)
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text("changed\n")
    assert reuse(repo, directory).returncode == 0


STATIC = [
    "native/src/lib.rs",
    "src/archkeel/cli.py",
    "studio/src/a.ts",
    "schema/frame.json",
    "tools/rustc-facts/driver.rs",
    "native/archkeel.toml",
    "native/architecture-contract.json",
    "docs/architecture/target/shell-contract.json",
    "docs/architecture/architecture-system.json",
    "docs/architecture/shell.toml",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
]


@pytest.mark.parametrize("name", STATIC)
def test_a_changed_static_input_is_a_miss(repo: Path, name: str) -> None:
    directory = saved(repo)
    with (repo / name).open("a") as out:
        out.write("\n")
    assert reuse(repo, directory).returncode == 1


@pytest.mark.parametrize(
    "name",
    [
        "native/src/new.rs",
        "src/archkeel/new.py",
        "rust-toolchain.toml",
        "native/rust-toolchain.toml",
        "elsewhere/.cargo/config.toml",
        "elsewhere/archkeel.toml",
        "inner/architecture-contract.json",
        "docs/architecture/inner/architecture-contract.json",
        "tools/probe.py",
        "package.json",
        ".env.local.md",
        "docs/.env.png",
        ".npmrc",
        ".env",
        "docs/data.yml",
        "fixtures/f.txt",
        "tools/patch.c",
        "tools/vendor/pyvenv.cfg",
        "tools/vendor/CACHEDIR.TAG",
        "tests/probe.py",
        "fixtures/probe.rs",
    ],
)
def test_a_new_file_that_can_decide_the_scan_is_a_miss_also_when_not_added(
    repo: Path, name: str
) -> None:
    directory = saved(repo)
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text("new\n")
    assert reuse(repo, directory).returncode == 1


def test_a_deleted_static_input_and_a_new_link_are_a_miss(repo: Path) -> None:
    directory = saved(repo)
    (repo / "native/src/lib.rs").unlink()
    assert reuse(repo, directory).returncode == 1
    (repo / "native/src/lib.rs").write_text("pub fn a() {}\n")
    assert reuse(repo, directory).returncode == 0
    (repo / "docs/link.md").symlink_to("other.md")
    assert reuse(repo, directory).returncode == 1


def test_a_changed_cited_document_is_a_miss_and_so_is_a_cited_file_that_appears(repo: Path) -> None:
    directory = saved(repo)
    (repo / "docs/guide.md").write_text("edited\n")
    assert reuse(repo, directory).returncode == 1
    (repo / "docs/guide.md").write_text("cited\n")
    assert reuse(repo, directory).returncode == 0
    (repo / "docs/guide.md").unlink()
    assert reuse(repo, directory).returncode == 1


def test_a_path_that_a_contract_cites_and_the_core_could_not_read_counts_too(repo: Path) -> None:
    # `docs/later.md` is cited and absent when the result is saved; creating it changes the scan.
    contract = repo / "native/architecture-contract.json"
    contract.write_text(json.dumps({"provenance": ["docs/guide.md", "docs/later.md"]}))
    git(repo, "add", "-A")
    directory = saved(repo)
    assert reuse(repo, directory).returncode == 0
    (repo / "docs/later.md").write_text("now present\n")
    assert reuse(repo, directory).returncode == 1


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["topology"]["modules"].append({"path": "lib/outside.py"}),
        lambda r: r["topology"].update(total={"modules": 5}),
        lambda r: r["topology"].update(modules=[]),
        lambda r: r["system"]["parts"].append({"config": "docs/part.md"}),
        lambda r: r["system"].update(document="docs/system.md"),
        lambda r: r["self_test"]["collect"].update(contract_files={}),
        lambda r: r.update(rules={}),
        lambda r: r.update(refusal={"kind": "core_error"}),
        lambda r: r.pop("system"),
    ],
)
def test_a_result_that_does_not_show_its_inputs_covered_is_never_saved(
    repo: Path, change: Any
) -> None:
    result = json.loads(json.dumps(RESULT))
    change(result)
    document = repo.parent / "result.json"
    document.write_text(json.dumps(result))
    directory = repo.parent / "entry"
    done = tool(repo, "save", "--result", str(document), "--dir", str(directory))
    assert done.returncode == 1 and not directory.exists(), done.stdout


def test_every_failure_to_read_the_entry_is_a_miss(repo: Path, tmp_path: Path) -> None:
    directory = saved(repo)
    (directory / "result.json").unlink()
    assert reuse(repo, directory).returncode == 1
    (directory / "entry.json").write_text("{not json")
    assert reuse(repo, directory).returncode == 1
    assert reuse(repo, tmp_path / "absent").returncode == 1
    entry = {"version": 99, "static": "x", "documents": {}}
    (directory / "entry.json").write_text(json.dumps(entry))
    assert reuse(repo, directory).returncode == 1
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    assert reuse(outside, directory).returncode == 1


def test_the_key_prefix_names_the_static_inputs_only(repo: Path) -> None:
    before = tool(repo, "key").stdout
    (repo / "docs/other.md").write_text("changed\n")
    assert tool(repo, "key").stdout == before
    (repo / "uv.lock").write_text("changed\n")
    assert tool(repo, "key").stdout != before


def test_an_ignored_source_file_that_a_collector_reads_is_a_miss(repo: Path) -> None:
    (repo / ".gitignore").write_text("ignored/\nsrc/archkeel/skip.py\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ignore")
    directory = saved(repo)
    (repo / "ignored").mkdir()
    (repo / "ignored/note.md").write_text("not source\n")
    assert reuse(repo, directory).returncode == 0
    (repo / "src/archkeel/skip.py").write_text("import archkeel.cli\n")
    assert reuse(repo, directory).returncode == 1
    (repo / "src/archkeel/skip.py").unlink()
    assert reuse(repo, directory).returncode == 0
    (repo / "ignored/hidden.py").write_text("x = 1\n")
    assert reuse(repo, directory).returncode == 1


def test_a_followed_configuration_link_counts_with_its_target(repo: Path) -> None:
    (repo / "docs/overrides.toml").write_text("[source]\n")
    (repo / "native/.cargo").mkdir()
    (repo / "native/.cargo/config.toml").symlink_to("../../docs/overrides.toml")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "link")
    directory = saved(repo)
    assert reuse(repo, directory).returncode == 0
    (repo / "docs/overrides.toml").write_text("[source.crates-io]\nreplace-with = 'x'\n")
    assert reuse(repo, directory).returncode == 1


def test_build_output_that_the_collectors_skip_keeps_the_key(repo: Path) -> None:
    (repo / ".gitignore").write_text("target/\ntest-artifacts/\n__pycache__/\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ignore")
    before = tool(repo, "key").stdout
    for name in ("native/target/release/core", "test-artifacts/r.json", "src/__pycache__/a.pyc"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("built\n")
    assert tool(repo, "key").stdout == before


def test_a_cargo_configuration_inside_build_output_counts(repo: Path) -> None:
    (repo / ".gitignore").write_text("target/\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ignore")
    directory = saved(repo)
    (repo / "target/release").mkdir(parents=True)
    (repo / "target/release/core").write_text("built\n")
    assert reuse(repo, directory).returncode == 0
    (repo / "target/.cargo").mkdir()
    (repo / "target/.cargo/config.toml").write_text("[source.crates-io]\nreplace-with = 'x'\n")
    assert reuse(repo, directory).returncode == 1
