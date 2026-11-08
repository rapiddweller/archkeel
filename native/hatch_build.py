# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Put the native TypeScript collector into a platform wheel when a build asks for it (AD-317).

`ARCHKEEL_BUNDLE_NATIVE` selects the binary: an absolute path to a prebuilt binary, or `1` to
build it with cargo from `native/`. Without the variable the hook does nothing, so an sdist, an
editable install and the default wheel never run cargo.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

REQUEST = "ARCHKEEL_BUNDLE_NATIVE"
BINARY = "archkeel-typescript-collector"
PACKAGE_DATA = "archkeel/_native"
# The minimum macOS of a binary is the default deployment target of Rust for its architecture.
MACOS = {"x86_64": "10.12", "arm64": "11.0"}
LINUX = re.compile(r"(manylinux_\d+_\d+_(?:x86_64|aarch64)|musllinux_\d+_\d+_x86_64)")
SUPPORTED = "macOS x86_64 and arm64, manylinux x86_64 and aarch64, musllinux x86_64, win_amd64"


def _wheel_platform(platform: str) -> str | None:
    macos = re.fullmatch(r"macosx_\d+_\d+_(\w+)", platform)
    if macos and macos[1] in MACOS:
        return f"macosx_{MACOS[macos[1]].replace('.', '_')}_{macos[1]}"
    # The glibc or musl version of the build host is the minimum version of the binary.
    if LINUX.fullmatch(platform) or platform == "win_amd64":
        return platform
    return None


def _unsupported(platform: str) -> ValueError:
    return ValueError(f"No native TypeScript collector for {platform}. Supported: {SUPPORTED}.")


def wheel_tag(platform: str) -> str:
    """Give the wheel tag for a supported platform tag of the build host."""
    wheel = _wheel_platform(platform)
    if wheel is None:
        raise _unsupported(repr(platform))
    return f"py3-none-{wheel}"


def host_platform(tags: Iterable[str]) -> str:
    """Give the first supported tag of `packaging.tags.platform_tags()`.

    packaging 26 yields the generic `linux_<arch>` before `manylinux_<glibc>_<arch>`, and it
    yields the newest glibc version first, so the first supported tag is the most specific one.
    """
    listed = tuple(tags)
    supported = [tag for tag in listed if _wheel_platform(tag) is not None]
    if not supported:
        raise _unsupported(repr(listed[0]) if listed else "this host")
    return supported[0]


def _platform_tags() -> Iterator[str]:
    # Hatchling depends on packaging, so the build environment has it.
    from packaging.tags import platform_tags

    return platform_tags()


def bundle(
    root: Path, version: str, request: str, build_data: dict[str, Any], platform: str = ""
) -> None:
    """Change `build_data` of hatchling so that the wheel carries the binary."""
    if not request:
        return
    tag = wheel_tag(platform or host_platform(_platform_tags()))
    name = BINARY + (".exe" if tag.endswith("win_amd64") else "")
    binary = _cargo_build(root, version, tag, name) if request == "1" else _prebuilt(request)
    build_data["pure_python"] = False
    build_data["tag"] = tag
    build_data["force_include"][str(binary)] = f"{PACKAGE_DATA}/{name}"


def _prebuilt(request: str) -> Path:
    binary = Path(request)
    # A relative path is unclear: a wheel built from the sdist runs in a temporary directory.
    if not binary.is_absolute():
        raise ValueError(f"{REQUEST} must be an absolute path or 1, not {request!r}.")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"{REQUEST}={request} is not an executable file.")
    return binary


def _cargo_build(root: Path, version: str, tag: str, name: str) -> Path:
    native = root / "native"
    if not (native / "Cargo.toml").is_file():
        raise ValueError(
            f"{REQUEST}=1 builds from a checkout, and {root} has no native/Cargo.toml. "
            "Give the absolute path of a prebuilt binary."
        )
    cargo = shutil.which("cargo")
    if cargo is None:
        raise ValueError(f"{REQUEST}=1 needs cargo. Install Rust or give a prebuilt binary.")
    environment = {**os.environ, "ARCHKEEL_VERSION": version}
    macos = re.fullmatch(r"py3-none-macosx_(\d+)_(\d+)_\w+", tag)
    if macos:
        environment["MACOSX_DEPLOYMENT_TARGET"] = f"{macos[1]}.{macos[2]}"
    target = native / "target"
    # The working directory selects the toolchain that native/rust-toolchain.toml pins.
    subprocess.run(
        [cargo, "build", "--release", "--locked", "--target-dir", str(target)],
        cwd=native,
        env=environment,
        stdout=sys.stderr,
        check=True,
    )
    return target / "release" / name


def get_build_hook() -> type:
    # Hatchling calls this function, so the tests can import this file without hatchling.
    from hatchling.builders.config import BuilderConfig
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface

    class NativeCollectorHook(BuildHookInterface[BuilderConfig]):
        def initialize(self, version: str, build_data: dict[str, Any]) -> None:
            # An editable install never builds or bundles the binary.
            if version != "editable":
                request = os.environ.get(REQUEST, "")
                bundle(Path(self.root), self.metadata.version, request, build_data)

    return NativeCollectorHook
