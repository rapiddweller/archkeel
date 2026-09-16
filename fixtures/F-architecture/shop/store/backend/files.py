# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The file format behind the repository: one JSON document per order id."""

from __future__ import annotations

import json
from pathlib import Path

from shop.model.entities import OrderPayload


def write_payload(path: Path, payload: OrderPayload) -> None:
    path.write_text(json.dumps(payload))


def read_payload(path: Path) -> OrderPayload:
    return json.loads(path.read_text())
