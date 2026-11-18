# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`--timings FILE` never replaces an input or another output, and it is written only for a run
that the core measured completely (#659, review of PR #1834).

Each test names the bytes of the files before and after the run: a refused run changes no file.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command
from test_cli_native_system_run import PASSING, _system, _validate

SENTINEL = b"keep these bytes\n"
SECOND = tuple({**rule, "id": f"Q-{rule['id']}"} for rule in PASSING)


def _refused(done: Any, *, kept: dict[Path, bytes], code: int = 2) -> None:
    assert done.returncode == code, done.stdout + done.stderr
    assert "no file was written" in done.stdout + done.stderr
    for path, before in kept.items():
        assert path.read_bytes() == before, f"{path} changed"


def test_an_output_and_a_timings_file_cannot_be_the_same_file(built: Path, tmp_path: Path) -> None:
    same = tmp_path / "same.html"
    same.write_bytes(SENTINEL)
    with case_root(HONEST) as root:
        done = command(
            built / f"archkeel-core{SUFFIX}",
            root,
            "--output",
            str(same),
            "--timings",
            str(same),
            verb="report",
        )
    _refused(done, kept={same: SENTINEL})


@pytest.mark.parametrize(
    "target",
    ["archkeel.toml", "architecture-contract.json", "src/a/a.ts", "./src/../archkeel.toml"],
)
def test_a_timings_file_cannot_replace_an_input_of_the_run(built: Path, target: str) -> None:
    with case_root(HONEST) as root:
        before = {name: (root / name).read_bytes() for name in ("archkeel.toml", "src/a/a.ts")}
        before["architecture-contract.json"] = (root / "architecture-contract.json").read_bytes()
        done = command(built / f"archkeel-core{SUFFIX}", root, "--timings", target, cwd=root)
        _refused(done, kept={root / name: data for name, data in before.items()})


def test_a_link_to_an_input_is_the_input(built: Path, tmp_path: Path) -> None:
    with case_root(HONEST) as root:
        alias = tmp_path / "alias.json"
        alias.symlink_to(root / "archkeel.toml")
        before = (root / "archkeel.toml").read_bytes()
        done = command(built / f"archkeel-core{SUFFIX}", root, "--timings", str(alias))
        _refused(done, kept={root / "archkeel.toml": before})
        assert alias.is_symlink()


def test_a_baseline_and_a_timings_file_cannot_be_the_same_file(built: Path) -> None:
    with case_root(HONEST) as root:
        same = root / "baseline.json"
        same.write_bytes(SENTINEL)
        # A file that was not written exits 1 with `--baseline` and 2 without it (AD-731).
        for code, flags in (
            (1, ("--baseline", "baseline.json", "--timings", str(same))),
            (2, ("--write-baseline", "baseline.json", "--timings", str(same))),
        ):
            done = command(built / f"archkeel-core{SUFFIX}", root, *flags, cwd=root)
            _refused(done, kept={same: SENTINEL}, code=code)


def test_a_system_run_does_not_replace_a_part_configuration(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING}, [])
    kept = {root / name: (root / name).read_bytes() for name in ("one.toml", "system.json")}
    for name in ("one.toml", "system.json", "one-contract.json"):
        code, result = _validate(root, core_binary, "--timings", str(root / name))
        assert code == 2, result
        assert "no file was written" in json.dumps(result)
    assert {path: path.read_bytes() for path in kept} == kept


def test_a_system_run_with_a_refused_part_writes_no_timings_and_keeps_the_old_file(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING, "two": SECOND}, [])
    (root / "two.toml").write_text("[scan\n", encoding="utf-8")
    target = tmp_path / "timings.json"
    target.write_bytes(SENTINEL)
    code, result = _validate(root, core_binary, "--timings", str(target))
    assert code == 2 and result["status"] == "UNKNOWN", result
    assert target.read_bytes() == SENTINEL


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
