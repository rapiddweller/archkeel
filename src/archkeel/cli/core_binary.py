# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the core of this install, never a binary selected by the scanned repository.

The lookup reads only the directory of this package: the bundled binary with its digest, else the
build output of the checkout that holds this package below `src/`. An installed package has no
checkout. The lookup never reads the scanned project, the current directory or `PATH` (AD-432).
A platform wheel bundles the binary and its digest (AD-436). The digest finds a damaged or wrong
file. It does not stop a party that can write both files, or a change after the check.
"""

import hashlib
import sysconfig
from pathlib import Path

from .core_frame import CoreError


class CoreBinaryNotFound(CoreError):
    """This install has no core binary, so no command can decide."""


def locate_core(package: Path | None = None) -> Path:
    package = package or Path(__file__).resolve().parents[1]
    name = "archkeel-core" + (sysconfig.get_config_var("EXE") or "")
    bundled = package / "_native" / name
    if bundled.exists() or bundled.with_name(name + ".sha256").exists():
        try:
            recorded = bundled.with_name(name + ".sha256").read_text(encoding="ascii")
            with bundled.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except (OSError, UnicodeError) as error:
            raise CoreBinaryNotFound(
                f"the installed core binary or digest is missing: {bundled}"
            ) from error
        if recorded != actual:
            raise CoreError(f"the installed core binary digest does not match: {bundled}")
        return bundled
    checkout = package.parent.parent
    in_checkout = package.parent.name == "src" and (checkout / "pyproject.toml").is_file()
    if in_checkout and (checkout / "native" / "core" / "Cargo.toml").is_file():
        for profile in ("release", "debug"):
            binary = checkout / "native" / "target" / profile / name
            if binary.is_file():
                return binary
        raise CoreBinaryNotFound(
            "the core binary is missing; build native/ with cargo build --release -p archkeel-core"
        )
    raise CoreBinaryNotFound(
        "this package holds no core binary; install a platform wheel of archkeel, or run from a "
        "checkout after cargo build --release -p archkeel-core"
    )
