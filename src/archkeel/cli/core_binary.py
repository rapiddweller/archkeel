# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the core of this install, never a binary selected by the scanned repository."""

import hashlib
import os
from pathlib import Path

from .core_frame import CoreError


def locate_core(package: Path | None = None) -> Path:
    package = package or Path(__file__).resolve().parents[1]
    name = "archkeel-core.exe" if os.name == "nt" else "archkeel-core"
    bundled = package / "_native" / name
    if bundled.parent.exists():
        try:
            recorded = bundled.with_name(name + ".sha256").read_text(encoding="ascii")
            actual = hashlib.sha256(bundled.read_bytes()).hexdigest()
        except (OSError, UnicodeError) as error:
            raise CoreError(f"the installed core binary or digest is missing: {bundled}") from error
        if recorded != actual:
            raise CoreError(f"the installed core binary digest does not match: {bundled}")
        return bundled
    checkout = package.parent.parent
    if (checkout / "native" / "core" / "Cargo.toml").is_file():
        for profile in ("release", "debug"):
            binary = checkout / "native" / "target" / profile / name
            if binary.is_file():
                return binary
    raise CoreError("the core binary is missing; build native/ with cargo build --release -p archkeel-core")
