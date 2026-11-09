# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read each bundled page asset once per process: the installed bytes do not change."""

from __future__ import annotations

import base64
from functools import cache
from importlib.resources import files


@cache
def asset(name: str) -> bytes:
    return files("archkeel.render").joinpath("assets", name).read_bytes()


@cache
def data_uri(name: str, mime_type: str) -> str:
    encoded = base64.b64encode(asset(name)).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
