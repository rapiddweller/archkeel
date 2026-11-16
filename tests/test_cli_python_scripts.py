# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""K3 (AD-648): a file that no import can name is a script, not a module of the layout."""

import json
import subprocess
import sys
from pathlib import Path

from test_cli_core_only_scan import command
from test_cli_python_target import target_project


def test_truth_python_cannot_import_these_files_by_any_name(tmp_path: Path) -> None:
    """The plant's truth, by the interpreter itself: neither spelling reaches the file."""
    package = tmp_path / "app"
    (package / "demo-x").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "demo-x" / "run.scr.py").write_text("raise SystemExit('imported')\n")
    (package / "tool.v2.py").write_text("raise SystemExit('imported')\n")
    code = (
        "import importlib, sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "for name in ('app.demo-x.run.scr', 'app.demo-x.run', 'app.tool.v2', 'app.tool'):\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except ModuleNotFoundError:\n"
        "        continue\n"
        "    raise SystemExit('imported ' + name)\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr + done.stdout


def _project(root: Path) -> Path:
    target_project(root)
    (root / "src/app/util.py").write_text("VALUE = 1\n")
    (root / "src/app/demo-x").mkdir()
    (root / "src/app/demo-x/run.scr.py").write_text("from app import util\n")
    return root


def test_a_script_file_holds_no_rule_and_is_not_a_gap(release_core: Path, tmp_path: Path) -> None:
    root = _project(tmp_path)
    done = command(release_core, root, "--text")
    assert done.returncode == 0, done.stdout
    assert "module_outside_layout" not in command(release_core, root, "--json").stdout


def test_a_module_above_its_root_still_holds_the_run(release_core: Path, tmp_path: Path) -> None:
    root = _project(tmp_path)
    inner = root / "src/app/inner/app"
    inner.mkdir(parents=True)
    (inner / "deep.py").write_text("")
    config = root / "archkeel.toml"
    config.write_text(config.read_text().replace('"src"', '"src/app/inner"'))
    done = command(release_core, root, "--json")
    assert "module_outside_layout" in done.stdout and json.loads(done.stdout)["status"] != "PASS"
