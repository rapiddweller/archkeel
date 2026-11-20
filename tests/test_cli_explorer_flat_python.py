# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A repository of root-level Python scripts opens as observed source."""

import hashlib
import json
from pathlib import Path

import pytest
from corpus_support import commit_tree

from archkeel.cli import core_explorer, core_only
from archkeel.cli.core_arguments import Options
from archkeel.cli.core_binding import ProjectRoot
from archkeel.cli.core_frame import CoreCommand
from archkeel.cli.init_draft import NothingToDraft, draft


def test_observed_flat_scripts_use_the_real_native_collector(tmp_path: Path, built: Path) -> None:
    (tmp_path / "main.py").write_text("def run():\n    return 1\n")
    (tmp_path / "test_helper.py").write_text("pass\n")
    commit_tree(tmp_path)
    with pytest.raises(NothingToDraft):
        draft(tmp_path)
    project = ProjectRoot.of(tmp_path, None)
    digests = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.py")}

    def scan(target: ProjectRoot):
        options = Options(
            command=CoreCommand.REPORT, config=target.config, topology=True, explorer=True
        )
        return core_only._exchange_scan(options, target, built / "archkeel-core", [])

    stdout, frame = core_explorer._observed_scan(project, digests, scan)
    document = json.loads(stdout)
    assert frame.topology is not None
    paths = {file["path"] for part in document["explorer"] for file in part["files"]}
    assert "main.py" in paths, document["collection_gaps"]
    assert "test_helper.py" not in paths
    assert not (tmp_path / "archkeel.toml").exists()


def test_multiple_root_scripts_do_not_create_observed_parts(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("pass\n")
    (tmp_path / "helper.py").write_text("pass\n")
    with pytest.raises(NothingToDraft, match="Multiple Python scripts in the repository root"):
        draft(tmp_path, scan_folder=".observed")
