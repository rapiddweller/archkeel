# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The protocol reader admits only live class inventory and proven type bindings."""

from pathlib import Path

import pytest
from core_support import ROOT
from test_cli_native_python_imports import verdict

from tools.fixture_tree import fixture_tree

SHOP = ROOT / "fixtures/F-architecture"
RULE = "STORE-READER-DECLARATION"


@pytest.mark.parametrize(
    ("replacement", "status"),
    [
        ("    reader: RepositoryReader", "PASS"),
        ("    reader: object", "FAIL"),
        ("    reader = None", "FAIL"),
        ("    if True:\n        reader: RepositoryReader", "UNKNOWN"),
        ("    RepositoryReader = object\n    reader: RepositoryReader", "UNKNOWN"),
        ("    reader: Missing", "UNKNOWN"),
        ("    reader: RepositoryReader\n    __annotations__ = {}", "UNKNOWN"),
        ("    __slots__ = ('RepositoryReader',)\n    reader: RepositoryReader", "UNKNOWN"),
    ],
)
def test_live_protocol_member_declaration(
    release_core: Path, replacement: str, status: str
) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/repository.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace("    reader: RepositoryReader", replacement),
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["protocol_declarations", status]
    if status == "PASS":
        assert frame["premises"][RULE][0]["kind"] == "standard_library_unchanged"
    if status == "FAIL":
        assert frame["details"][RULE][0]["source"] == "shop.store.repository.OrderRepository:reader"


def test_protocol_class_can_disable_canonical_identity(release_core: Path) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/repository.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace(
                "class RepositoryReader(Protocol):",
                "class RepositoryReader(Protocol):\n    _is_protocol = False",
            ),
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["protocol_declarations", "UNKNOWN"]


def test_known_member_violation_survives_an_unread_class(release_core: Path) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/repository.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace("    reader: RepositoryReader", "    reader: object")
            + "\n\nclass Unread:\n    if True:\n        reader: RepositoryReader\n",
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["protocol_declarations", "FAIL"]
    assert frame["details"][RULE][0]["source"] == "shop.store.repository.OrderRepository:reader"


def test_protocol_member_holds_when_any_binding_can_change(release_core: Path) -> None:
    with fixture_tree(SHOP) as root:
        source = root / "shop/store/repository.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text.replace(
                "from typing import Protocol", "import typing\nfrom typing import Protocol"
            ).replace(
                "    reader: RepositoryReader",
                "    reader: typing.Any",
            )
            + "\n\ntyping.Any = RepositoryReader\n",
            encoding="utf-8",
        )
        frame = verdict(release_core, root, "report")["frame"]
    assert frame["rules"][RULE] == ["protocol_declarations", "UNKNOWN"]
