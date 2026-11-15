# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Variants of the M-review-workflow fixture for the interface lifecycle of a mounted contract
(AD-514, #880). Each variant changes one contract file; `four` is the `interface.*` finding of an
installed 4.0.1 (`validate --json`) with its pointer."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "M-review-workflow"
ROOT = "architecture-contract.json"
CHECKOUT = "contracts/checkout.json"


@dataclass(frozen=True)
class Variant:
    name: str
    file: str
    change: Callable[[dict[str, Any]], None]
    # The finding of 4.0.1 (code, pointer) and the code that the core gives at that pointer.
    four: tuple[str, str] | None
    core: str | None


def _component(contract: dict[str, Any], label: str) -> dict[str, Any]:
    return next(c for c in contract["components"] if label in (c["label"], c["id"]))


def _drop_parent_entry(contract: dict[str, Any]) -> None:
    _component(contract, "checkout")["public"] = ["orders.checkout"]


def _unread_entry(contract: dict[str, Any]) -> None:
    entries = _component(contract, "checkout-operation")["public"]
    _component(contract, "checkout-operation")["public"] = [
        *entries,
        "orders.checkout.service:other",
    ]


def _undeclare(contract: dict[str, Any]) -> None:
    _component(contract, "checkout-receipts").pop("public")


def variants() -> list[Variant]:
    base = "/components/1/inside/components"
    return [
        Variant("as it is", ROOT, lambda _: None, None, None),
        Variant(
            "the parent does not publish the entry of its mount",
            ROOT,
            _drop_parent_entry,
            ("interface.unused", f"{base}/0/public/1"),
            "interface.usage_unknown",
        ),
        Variant(
            "an entry of the mount that no import reaches",
            CHECKOUT,
            _unread_entry,
            ("interface.unused", f"{base}/0/public/2"),
            "interface.usage_unknown",
        ),
        Variant(
            "a component of the mount without public entry that receives imports",
            CHECKOUT,
            _undeclare,
            ("interface.undeclared", f"{base}/1"),
            "interface.undeclared",
        ),
    ]


def build(root: Path, variant: Variant) -> Path:
    """Copy the fixture below `root` with the change of one variant; the caller commits it."""
    shutil.copytree(FIXTURE, root)
    path = root / variant.file
    contract = json.loads(path.read_text())
    variant.change(contract)
    path.write_text(json.dumps(contract, indent=1))
    return root
