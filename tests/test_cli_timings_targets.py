# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`--timings FILE` creates a new file and never replaces one (#659, review of PR #1834).

A path that exists, also as a link or a second name of a file, is refused before the scan and
before any other output. Two new targets that name one file are refused too. A file that appears
while the run writes is not replaced. Each test compares the bytes of every file before and after.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, SUFFIX, case_root, run
from test_cli_core_only_scan import command
from test_cli_native_system_run import PASSING, _system, _validate

from archkeel.cli import core_only

SENTINEL = b"keep these bytes\n"
SECOND = tuple({**rule, "id": f"Q-{rule['id']}"} for rule in PASSING)


def _bytes(*folders: Path) -> dict[Path, bytes]:
    """Every file below the folders, except the Git directory, with its bytes."""
    return {
        path: path.read_bytes()
        for folder in folders
        for path in sorted(folder.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }


def _refused(done: Any, cause: str) -> None:
    assert done.returncode == 2, done.stdout + done.stderr
    text = done.stdout + done.stderr
    assert cause in text and "--timings" in text, text
    assert '"frame"' not in text and "PASS" not in text, "no output of the run"


@pytest.mark.parametrize(
    "target",
    [
        "archkeel.toml",
        "architecture-contract.json",
        "tsconfig.json",
        "src/a/a.ts",
        "outside.js",
        "./src/../archkeel.toml",
    ],
)
def test_a_file_that_exists_is_refused_before_the_scan(built: Path, target: str) -> None:
    with case_root(HONEST) as root:
        (root / "outside.js").write_text("const value = 42;\n", encoding="utf-8")
        before = _bytes(root)
        done = command(built / f"archkeel-core{SUFFIX}", root, "--timings", target, cwd=root)
        _refused(done, "never replaces one")
        assert _bytes(root) == before


def test_a_link_or_a_second_name_of_an_input_is_a_file_that_exists(
    built: Path, tmp_path: Path
) -> None:
    with case_root(HONEST) as root:
        names = {
            "symlink": tmp_path / "symlink.json",
            "dangling": tmp_path / "dangling.json",
            "hardlink": tmp_path / "hardlink.json",
        }
        names["symlink"].symlink_to(root / "tsconfig.json")
        names["dangling"].symlink_to(tmp_path / "missing.json")
        os.link(root / "tsconfig.json", names["hardlink"])
        before = _bytes(root)
        for target in names.values():
            done = command(built / f"archkeel-core{SUFFIX}", root, "--timings", str(target))
            _refused(done, "never replaces one")
        assert _bytes(root) == before
        assert names["symlink"].is_symlink() and not (tmp_path / "missing.json").exists()


def test_an_output_and_a_timings_file_cannot_be_one_new_file(built: Path, tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    with case_root(HONEST) as root:
        for spelling in (str(tmp_path / "same.html"), str(tmp_path / "sub" / ".." / "same.html")):
            done = command(
                built / f"archkeel-core{SUFFIX}",
                root,
                "--output",
                str(tmp_path / "same.html"),
                "--timings",
                spelling,
                verb="report",
            )
            _refused(done, "name the same file")
    assert not (tmp_path / "same.html").exists()


def test_a_baseline_and_a_timings_file_cannot_be_one_new_file(built: Path) -> None:
    with case_root(HONEST) as root:
        before = _bytes(root)
        done = command(
            built / f"archkeel-core{SUFFIX}",
            root,
            "--write-baseline",
            "new.json",
            "--timings",
            str(root / "new.json"),
            cwd=root,
        )
        _refused(done, "name the same file")
        assert _bytes(root) == before


def test_a_new_file_is_created_once_and_a_second_run_does_not_replace_it(
    built: Path, tmp_path: Path
) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    target = tmp_path / "timings.json"
    with case_root(HONEST) as root:
        first = command(binary, root, "--timings", str(target))
        assert first.returncode == 0, first.stdout + first.stderr
        written = target.read_bytes()
        assert json.loads(written)["protocol"] == "archkeel-core-timings-1"
        second = command(binary, root, "--timings", str(target))
        _refused(second, "never replaces one")
    assert target.read_bytes() == written
    assert [path.name for path in tmp_path.iterdir()] == ["timings.json"], "no temporary file"


@pytest.mark.parametrize("racer", ["file", "link"])
def test_a_file_that_appears_during_the_run_is_not_replaced(
    tmp_path: Path, core_binary: Path, monkeypatch: pytest.MonkeyPatch, racer: str
) -> None:
    real = core_only.exchange
    target = tmp_path / "timings.json"

    def late(binary: str, kind: str, request: bytes, stderr_sink: list[bytes]) -> Any:
        answer = real(binary, kind, request, stderr_sink)
        if racer == "file":
            target.write_bytes(SENTINEL)
        else:
            target.symlink_to(tmp_path / "victim.txt")
        return answer

    victim = tmp_path / "victim.txt"
    victim.write_bytes(SENTINEL)
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    monkeypatch.setattr(core_only, "exchange", late)
    with case_root(HONEST) as root:
        before = _bytes(root)
        code, result = run("validate", "--root", str(root), "--timings", str(target))
        assert _bytes(root) == before
    assert code == 2 and "cannot write timings file" in json.dumps(result), result
    assert victim.read_bytes() == SENTINEL
    assert (target.read_bytes() == SENTINEL) if racer == "file" else target.is_symlink()
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        ["timings.json", "victim.txt"]
    ), "no temporary file"


def test_a_system_run_with_a_refused_part_writes_no_timings_file(
    tmp_path: Path, core_binary: Path
) -> None:
    for refused in ("two", "one"):
        root = _system(tmp_path / refused, core_binary, {"one": PASSING, "two": SECOND}, [])
        (root / f"{refused}.toml").write_text("[scan\n", encoding="utf-8")
        target = tmp_path / f"timings-{refused}.json"
        code, result = _validate(root, core_binary, "--timings", str(target))
        assert code == 2 and result["status"] == "UNKNOWN", result
        assert not target.exists(), f"a system with a refused part {refused!r} has no timings"


def test_a_refused_scan_writes_no_timings_file_and_is_no_error(built: Path, tmp_path: Path) -> None:
    target = tmp_path / "timings.json"
    with case_root(HONEST) as root:
        (root / "archkeel.toml").write_text("[scan\n", encoding="utf-8")
        done = command(built / f"archkeel-core{SUFFIX}", root, "--timings", str(target))
    assert done.returncode == 2 and "UNKNOWN" in done.stdout, done.stdout + done.stderr
    assert not target.exists()


def test_a_complete_system_run_names_the_join_apart_from_the_render(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING, "two": SECOND}, [])
    target = tmp_path / "timings.json"
    code, result = _validate(root, core_binary, "--timings", str(target))
    assert code == 0, result
    document = json.loads(target.read_text(encoding="utf-8"))
    phases = document["phases"]
    assert phases["join"] > 0 and phases["collect"] > 0
    assert sum(phases.values()) <= document["core_seconds"] + 1e-5
