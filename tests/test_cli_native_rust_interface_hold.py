# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1089: the hold of an `interface_boundary` rule counts each import once."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from rust_repository import component
from test_cli_native_rust_interface import BASE, PUBLIC, _run

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")


def test_a_glob_that_is_a_crossing_and_a_publication_is_one_import_in_the_hold(
    core_binary: Path, tmp_path: Path
) -> None:
    base = {**component("base", "base_crate"), "public": PUBLIC}
    app = {**component("app", "app", ("base",)), "public": ["native.app:run"]}
    files = {**BASE, "crates/app/src/lib.rs": "pub use base_crate::*;\npub fn run() {}\n"}
    _, found = _run(tmp_path, core_binary, files, (base, app))
    [text] = found
    assert text.startswith(
        "BOUNDARY: incomplete scope: interface_boundary: unread import binding: 1 import: "
    ), found
