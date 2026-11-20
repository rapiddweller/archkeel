# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the core of this install, never a binary selected by the scanned repository.

The lookup reads only the directory of this package: the bundled binary with its digest, else the
build output of the checkout that holds this package below `src/`. An installed package has no
checkout. The lookup never reads the scanned project, the current directory or `PATH` (AD-432).
A platform wheel bundles the binary and its digest (AD-436). The digest finds a damaged or wrong
file. It does not stop a party that can write both files. `confirm` checks the digest again
immediately before the start, so the window for a change after the first check is one start, not a
whole run. A change between that check and the start of the process stays open.
"""

import hashlib
import sysconfig
from pathlib import Path

from .core_json import CoreError


class CoreBinaryNotFound(CoreError):
    """This install has no core binary, so no command can decide."""


def _verify(bundled: Path) -> None:
    """Refuse a bundled core binary that is missing or whose digest file does not match it."""
    try:
        recorded = bundled.with_name(bundled.name + ".sha256").read_text(encoding="ascii")
        with bundled.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, UnicodeError) as error:
        raise CoreBinaryNotFound(
            f"the installed core binary or digest is missing: {bundled}"
        ) from error
    if recorded != actual:
        raise CoreError(f"the installed core binary digest does not match: {bundled}")


def collector_workers(binary: Path) -> tuple[Path, ...]:
    """The separately installed collectors that the core can start."""
    return tuple(
        binary.with_name(name + binary.suffix)
        for name in ("archkeel-rust-collector", "archkeel-typescript-collector")
    )


def confirm(binary: Path) -> None:
    """Check a bundled core binary and both workers beside it again, immediately before the
    core starts. A checkout binary has no digest file and is not checked."""
    if binary.parent.name == "_native":
        _verify(binary)
        for worker in collector_workers(binary):
            _verify(worker)


def locate_core(package: Path | None = None) -> Path:
    """The core binary of this install, verified; never one that the scanned repository selects."""

    package = package or Path(__file__).resolve().parents[1]
    name = "archkeel-core" + (sysconfig.get_config_var("EXE") or "")
    bundled = package / "_native" / name
    if bundled.exists() or bundled.with_name(name + ".sha256").exists():
        _verify(bundled)
        return bundled
    checkout = package.parent.parent
    in_checkout = package.parent.name == "src" and (checkout / "pyproject.toml").is_file()
    if in_checkout and (checkout / "native" / "core" / "Cargo.toml").is_file():
        for profile in ("release", "debug"):
            binary = checkout / "native" / "target" / profile / name
            if binary.is_file():
                return binary
        raise CoreBinaryNotFound("the core binary is missing; run make core")
    raise CoreBinaryNotFound(
        "this package holds no core binary; install a platform wheel of archkeel, or run from a "
        "checkout after make core"
    )
