# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The root and the configuration that a run scans (AD-776, #1608).

A relative `--config` is read from the current folder. Without `--root`, the root is the folder of
the configuration, or the folder that its `[scan] root` states; a system document names its work
tree. Without flags, the nearest `archkeel.toml` inside the work tree names the project. Each
header and each JSON result names the root and the configuration.
"""

import json
import subprocess
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command

from archkeel.cli import core_only
from archkeel.cli.core_json import CoreError

SCAN = '[scan]\nroots = ["."]\nnamespace = "app"\ncontract = "c.json"\n'


def _repository(root: Path) -> Path:
    """A work tree with its own `archkeel.toml` at the top and a project in `sub`."""
    (root / "sub").mkdir(parents=True)
    (root / "archkeel.toml").write_text(SCAN, encoding="utf-8")
    (root / "sub" / "archkeel.toml").write_text(SCAN, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root.resolve()


def _sent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd: Path,
    *argv: str,
) -> dict[str, object]:
    """The scan request of a command line, or the JSON refusal when the shell sends none."""
    requests: list[dict[str, object]] = []

    def exchange(_binary: str, _kind: str, request: bytes) -> tuple[bytes, int]:
        requests.append(json.loads(request))
        raise CoreError("stop after the request")

    monkeypatch.setattr(core_only, "locate_core", lambda: cwd / "archkeel-core")
    monkeypatch.setattr(core_only, "exchange", exchange)
    monkeypatch.chdir(cwd)
    core_only.run(["validate", "--json", *argv])
    out = capsys.readouterr().out
    return requests[0] if requests else json.loads(out)


def test_a_relative_config_in_a_subfolder_scans_the_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#1608: `cd sub && archkeel validate --config archkeel.toml` scanned the top project."""
    top = _repository(tmp_path)
    sent = _sent(monkeypatch, capsys, top / "sub", "--config", "archkeel.toml")
    assert (sent["root"], sent["config"]) == (str(top / "sub"), "archkeel.toml")
    assert sent["discover_root"] is False


def test_a_config_that_is_not_in_the_current_folder_is_refused_with_the_path_tried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    (top / "selected.toml").write_text(SCAN, encoding="utf-8")
    sent = _sent(monkeypatch, capsys, top / "sub", "--config", "selected.toml")
    assert sent["refusal"]["kind"] == "invalid_input"  # type: ignore[index]
    assert str(top / "sub" / "selected.toml") in sent["refusal"]["message"]  # type: ignore[index]


def test_without_flags_the_nearest_config_of_the_work_tree_names_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    sent = _sent(monkeypatch, capsys, top / "sub")
    assert (sent["root"], sent["config"]) == (str(top / "sub"), "archkeel.toml")
    (top / "sub" / "deeper").mkdir()
    (top / "sub" / "archkeel.toml").unlink()
    sent = _sent(monkeypatch, capsys, top / "sub" / "deeper")
    assert (sent["root"], sent["config"], sent["discover_root"]) == (
        str(top),
        "archkeel.toml",
        True,
    )


def test_without_flags_at_the_top_the_work_tree_is_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    sent = _sent(monkeypatch, capsys, top)
    assert (sent["root"], sent["config"], sent["discover_root"]) == (
        str(top),
        "archkeel.toml",
        True,
    )


def test_an_explicit_root_reads_the_config_below_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    (top / "sub" / "other.toml").write_text(SCAN, encoding="utf-8")
    sent = _sent(monkeypatch, capsys, tmp_path.parent, "--root", str(top / "sub"))
    assert (sent["root"], sent["config"], sent["discover_root"]) == (
        str(top / "sub"),
        "archkeel.toml",
        False,
    )
    both = ("--root", str(top / "sub"), "--config", "other.toml")
    sent = _sent(monkeypatch, capsys, top, *both)
    assert (sent["root"], sent["config"]) == (str(top / "sub"), "other.toml")


def test_a_config_below_the_repository_can_state_its_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    (top / "cfg").mkdir()
    (top / "cfg" / "x.toml").write_text(SCAN.replace("[scan]\n", '[scan]\nroot = ".."\n'))
    sent = _sent(monkeypatch, capsys, top, "--config", "cfg/x.toml")
    assert (sent["root"], sent["config"]) == (str(top), "cfg/x.toml")
    (top / "cfg" / "x.toml").write_text(SCAN.replace("[scan]\n", '[scan]\nroot = "sub"\n'))
    sent = _sent(monkeypatch, capsys, top, "--config", "cfg/x.toml")
    assert sent["refusal"]["kind"] == "invalid_input"  # type: ignore[index]
    assert "scan.root" in sent["refusal"]["message"]  # type: ignore[index]


def test_a_system_document_names_the_top_of_its_work_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    top = _repository(tmp_path)
    (top / "docs").mkdir()
    (top / "docs" / "system.json").write_text("{}", encoding="utf-8")
    sent = _sent(monkeypatch, capsys, top, "--config", "docs/system.json")
    assert (sent["root"], sent["config"]) == (str(top), "docs/system.json")


def test_the_header_and_the_json_name_the_root_and_the_config(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with case_root(HONEST) as root:
        binary = built / f"archkeel-core{SUFFIX}"
        text = command(binary, None, "--text", cwd=root)
        done = command(binary, None, "--json", cwd=root)
    assert text.returncode == 0, text.stdout + text.stderr
    assert text.stdout.splitlines()[0].endswith(" · root . · config archkeel.toml")
    result = json.loads(done.stdout)
    assert (result["root"], result["config"]) == (str(root), str(root / "archkeel.toml"))
