# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Put the core into a platform wheel, and refuse a wheel without it (AD-317, AD-436).

`ARCHKEEL_BUNDLE_NATIVE` selects the binary. `1` builds `archkeel-core` with `cargo auditable`
from `native/` and adds a CycloneDX SBOM of its crates. An absolute path bundles that prebuilt
core. Without the variable the hook refuses the build: a package without the core refuses each
run. An editable install bundles nothing, because the shell finds the build output of the checkout.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

Checksums = dict[tuple[str, str], str]

REQUEST = "ARCHKEEL_BUNDLE_NATIVE"
# The core links each collector, so it is the only binary of the package (AD-406, AD-436).
BINARY = "archkeel-core"
PACKAGE_DATA = "archkeel/_native"
# The minimum macOS of a binary is the default deployment target of Rust for its architecture.
MACOS = {"x86_64": "10.12", "arm64": "11.0"}
LINUX = re.compile(r"(manylinux_\d+_\d+_(?:x86_64|aarch64)|musllinux_\d+_\d+_x86_64)")
SUPPORTED = "macOS x86_64 and arm64, manylinux x86_64 and aarch64, musllinux x86_64, win_amd64"
NO_CORE = (
    f"A wheel of archkeel must carry the core binary {BINARY}, and this build has none. "
    f"Install a platform wheel ({SUPPORTED}). Or build the core from the Git tag "
    f"(cargo build --release -p {BINARY} in native/) and set {REQUEST} to its absolute path."
)


def _wheel_platform(platform: str) -> str | None:
    macos = re.fullmatch(r"macosx_\d+_\d+_(\w+)", platform)
    if macos and macos[1] in MACOS:
        return f"macosx_{MACOS[macos[1]].replace('.', '_')}_{macos[1]}"
    # The glibc or musl version of the build host is the minimum version of the binary.
    if LINUX.fullmatch(platform) or platform == "win_amd64":
        return platform
    return None


def _unsupported(platform: str) -> ValueError:
    return ValueError(f"No {BINARY} for {platform}. Supported: {SUPPORTED}.")


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
    """Change `build_data` of hatchling so that the wheel carries the core and its digest."""
    if not request:
        raise ValueError(NO_CORE)
    tag = wheel_tag(platform or host_platform(_platform_tags()))
    name = BINARY + (".exe" if tag.endswith("win_amd64") else "")
    if request == "1":
        binary = _cargo_build(root, version, tag) / name
        build_data["sbom_files"].append(str(_write_sbom(root / "native", binary, version)))
    else:
        binary = _prebuilt(request)
    build_data["pure_python"] = False
    build_data["tag"] = tag
    build_data["force_include"][str(binary)] = f"{PACKAGE_DATA}/{name}"
    # The shell starts the binary only when its file has this digest (AD-432).
    digest = _write_digest(root, binary)
    build_data["force_include"][str(digest)] = f"{PACKAGE_DATA}/{name}.sha256"


def _write_digest(root: Path, binary: Path) -> Path:
    """Write the SHA-256 of a binary, in hexadecimal, to a file that the wheel carries."""
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    directory = root / "native" / ".digests"
    directory.mkdir(parents=True, exist_ok=True)
    # The digest names the file, so two builds at the same time cannot change the record of each
    # other.
    record = directory / f"{digest}.sha256"
    record.write_text(digest, encoding="ascii")
    return record


def _prebuilt(request: str) -> Path:
    binary = Path(request)
    # A relative path is unclear: a wheel built from the sdist runs in a temporary directory.
    if not binary.is_absolute():
        raise ValueError(f"{REQUEST} must be an absolute path or 1, not {request!r}.")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"{REQUEST}={request} is not an executable file.")
    return binary


def build_environment(version: str, tag: str) -> dict[str, str]:
    environment = {**os.environ, "ARCHKEEL_VERSION": version}
    macos = re.fullmatch(r"py3-none-macosx_(\d+)_(\d+)_\w+", tag)
    if macos:
        environment["MACOSX_DEPLOYMENT_TARGET"] = f"{macos[1]}.{macos[2]}"
    if tag.startswith("py3-none-manylinux"):
        # The C grammar parser needs `le16toh`. The headers of glibc before 2.19 declare it only
        # for `_BSD_SOURCE`, which the strict `_POSIX_C_SOURCE` of its build script turns off.
        flags = environment.get("CFLAGS", "")
        environment["CFLAGS"] = f"{flags} -D_BSD_SOURCE".strip()
    return environment


def _cargo_build(root: Path, version: str, tag: str) -> Path:
    native = root / "native"
    if not (native / "Cargo.toml").is_file():
        raise ValueError(
            f"{REQUEST}=1 builds from a checkout, and {root} has no native/Cargo.toml. "
            "Give the absolute path of a prebuilt core."
        )
    cargo = shutil.which("cargo")
    if cargo is None:
        raise ValueError(f"{REQUEST}=1 needs cargo. Install Rust or give a prebuilt core.")
    if shutil.which("cargo-auditable") is None:
        raise ValueError(f"{REQUEST}=1 needs cargo-auditable. Run make native-tools.")
    environment = build_environment(version, tag)
    target = native / "target"
    # The working directory selects the toolchain that native/rust-toolchain.toml pins.
    # cargo auditable records the crates in the `.dep-v0` section for `cargo audit bin`.
    subprocess.run(
        [cargo, "auditable", "build", "--release", "--locked", "--target-dir", str(target)]
        + ["-p", BINARY],
        cwd=native,
        env=environment,
        stdout=sys.stderr,
        check=True,
    )
    return target / "release"


def _write_sbom(native: Path, binary: Path, version: str) -> Path:
    cargo = shutil.which("cargo") or "cargo"
    host = _run([cargo, "-vV"], native).split("host: ", 1)[1].split()[0]
    # The crates of the build host only: a crate for another platform is not in the binary.
    metadata = json.loads(
        _run(
            [cargo, "metadata", "--locked", "--format-version", "1", "--filter-platform", host],
            native,
        )
    )
    lock = tomllib.loads((native / "Cargo.lock").read_text(encoding="utf-8"))
    checksums = {
        (crate["name"], crate["version"]): crate["checksum"]
        for crate in lock["package"]
        if "checksum" in crate
    }
    sbom = binary.with_name(f"{BINARY}.cdx.json")
    text = json.dumps(cyclonedx(metadata, checksums, version), indent=2, sort_keys=True)
    sbom.write_text(text + "\n", encoding="utf-8")
    return sbom


def _run(command: list[str], cwd: Path) -> str:
    # Cargo prints UTF-8; the Windows locale code page (cp1252) cannot decode every byte of it.
    return subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def cyclonedx(metadata: dict[str, Any], checksums: Checksums, version: str) -> dict[str, Any]:
    """Give a CycloneDX 1.6 SBOM of the crates that the binary links (PEP 770).

    The SBOM follows the normal dependencies from the binary: build and test crates are not in it.
    A workspace crate has the version of the wheel, as the binary reports. A crates.io crate has
    its package URL and the SHA-256 from Cargo.lock. The SBOM has no time and no local path, so the
    same sources give the same bytes.
    """
    packages = {package["id"]: package for package in metadata["packages"]}
    edges = {
        node["id"]: sorted(
            {dep["pkg"] for dep in node["deps"] if any(k["kind"] is None for k in dep["dep_kinds"])}
        )
        for node in metadata["resolve"]["nodes"]
    }
    (root,) = (key for key, package in packages.items() if package["name"] == BINARY)
    linked, pending = {root}, [root]
    while pending:
        for dependency in edges[pending.pop()]:
            if dependency not in linked:
                linked.add(dependency)
                pending.append(dependency)
    refs = {key: _component(packages[key], checksums, version)["bom-ref"] for key in linked}
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": _component(packages[root], checksums, version, "application")},
        "components": sorted(
            (_component(packages[key], checksums, version) for key in linked - {root}),
            key=lambda component: component["bom-ref"],
        ),
        "dependencies": sorted(
            (
                {"ref": refs[key], "dependsOn": sorted(refs[item] for item in edges[key])}
                for key in linked
            ),
            key=lambda dependency: dependency["ref"],
        ),
    }


def _component(
    package: dict[str, Any], checksums: Checksums, version: str, kind: str = "library"
) -> dict[str, Any]:
    name, crate_version, license = package["name"], package["version"], package["license"]
    if not license:
        raise ValueError(f"The crate {name} {crate_version} has no license.")
    # cargo still accepts the old form `MIT/Apache-2.0`; SPDX writes it with OR.
    licenses = [{"expression": re.sub(r"\s*/\s*", " OR ", license)}]
    if package["source"] is None:
        return {
            "type": kind,
            "bom-ref": name,
            "name": name,
            "version": version,
            "licenses": licenses,
        }
    checksum = checksums.get((name, crate_version))
    if checksum is None:
        raise ValueError(f"The crate {name} {crate_version} has no checksum in Cargo.lock.")
    purl = f"pkg:cargo/{name}@{crate_version}"
    return {
        "type": kind,
        "bom-ref": purl,
        "name": name,
        "version": crate_version,
        "purl": purl,
        "licenses": licenses,
        "hashes": [{"alg": "SHA-256", "content": checksum}],
    }


def get_build_hook() -> type:
    # Hatchling calls this function, so the tests can import this file without hatchling.
    from hatchling.builders.config import BuilderConfig
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface

    class CoreHook(BuildHookInterface[BuilderConfig]):
        def initialize(self, version: str, build_data: dict[str, Any]) -> None:
            # An editable install never builds or bundles the binary.
            if version != "editable":
                request = os.environ.get(REQUEST, "")
                bundle(Path(self.root), self.metadata.version, request, build_data)

    return CoreHook
