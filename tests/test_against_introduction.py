# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-104 (#150): a contract the `--against` revision lacks is introduced, not unreadable."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.git import MissingBlobError, read_blob
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR


def _base(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _mobile_scope(tmp_path: Path, base_files: dict[str, str | None] | None = None) -> Path:
    """The merge request #150 describes: the shop sample is committed, and a Flutter-style
    package with its own archkeel.toml and contract is added under mobile/."""
    root = _prepare_repo(tmp_path, base_files or {})
    shutil.rmtree(root / "mobile", ignore_errors=True)
    shutil.copytree(DART_FIXTURE_DIR, root / "mobile")
    return root / "mobile"


def test_a_missing_blob_names_its_repository_path_below_the_root(tmp_path: Path) -> None:
    mobile = _mobile_scope(tmp_path)

    with pytest.raises(MissingBlobError) as raised:
        read_blob(mobile, _base(mobile), "architecture-contract.json")

    assert raised.value.path == "mobile/architecture-contract.json"
    assert str(raised.value) == "missing regular Git blob: mobile/architecture-contract.json"
