# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name a report sidecar without loading an engine or renderer."""

from pathlib import Path


def html_path(output: Path, command: str) -> Path:
    return output.parent / f"{output.stem}.{command}.html"
