# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The catalog generator owns one native output after the Python collector deletion."""

import pytest

from tools import typescript_libs


def test_the_catalog_output_is_the_native_embed():
    assert typescript_libs.OUTPUT == typescript_libs.ROOT / "native/typescript/standard_libs.json"


@pytest.mark.parametrize("content", [None, "stale", "catalog\n"])
def test_catalog_check_does_not_write_or_require_a_python_copy(tmp_path, monkeypatch, content):
    path = tmp_path / "catalog.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(typescript_libs, "ROOT", tmp_path)
    monkeypatch.setattr(typescript_libs, "OUTPUT", path)
    monkeypatch.setattr(typescript_libs, "build_catalog", lambda: "catalog\n")
    assert typescript_libs.main(["--check"]) == (0 if content == "catalog\n" else 1)
    assert (path.read_text() if path.exists() else None) == content
    assert typescript_libs.main(["--write"]) == 0
    assert path.read_bytes() == b"catalog\n"
