# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-317, AD-436: the wheel hook puts the core into a platform wheel, and refuses without it.

Consumer: the release build, which sets `ARCHKEEL_BUNDLE_NATIVE`. The test marked `native_wheel`
needs a Rust toolchain: `make native-wheel` runs it on each target of the wheel matrix in Full
verification. `test_cli_installed_wheel.py` installs the wheel and reads its verdicts.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tomllib
import zipfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from packaging.tags import platform_tags, sys_tags

ROOT = Path(__file__).parents[1]
MEMBER = "archkeel/_native/archkeel-core"
VERSION = "0.0.0"


def _hook() -> ModuleType:
    spec = spec_from_file_location("archkeel_hatch_build", ROOT / "native/hatch_build.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _hook()


def test_only_a_manylinux_build_gets_the_bsd_source_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # tree-sitter calls `le16toh`, which glibc before 2.19 declares only for `_BSD_SOURCE`.
    monkeypatch.setenv("CFLAGS", "-O1")
    flags = {
        tag: hook.build_environment(VERSION, tag).get("CFLAGS")
        for tag in (
            "py3-none-manylinux_2_17_aarch64",
            "py3-none-musllinux_1_2_x86_64",
            "py3-none-win_amd64",
        )
    }
    assert flags == {
        "py3-none-manylinux_2_17_aarch64": "-O1 -D_BSD_SOURCE",
        "py3-none-musllinux_1_2_x86_64": "-O1",
        "py3-none-win_amd64": "-O1",
    }


@pytest.mark.parametrize(
    "platform,tag",
    [
        ("macosx_14_0_x86_64", "py3-none-macosx_10_12_x86_64"),
        ("macosx_27_0_arm64", "py3-none-macosx_11_0_arm64"),
        ("manylinux_2_17_x86_64", "py3-none-manylinux_2_17_x86_64"),
        ("manylinux_2_17_aarch64", "py3-none-manylinux_2_17_aarch64"),
        ("musllinux_1_2_x86_64", "py3-none-musllinux_1_2_x86_64"),
        ("win_amd64", "py3-none-win_amd64"),
    ],
)
def test_each_target_platform_has_one_wheel_tag(platform: str, tag: str) -> None:
    assert hook.wheel_tag(platform) == tag


@pytest.mark.parametrize(
    "platform",
    ["linux_x86_64", "musllinux_1_2_aarch64", "win_arm64", "macosx_14_0_universal2", "any"],
)
def test_an_unknown_platform_is_a_clear_error(platform: str) -> None:
    with pytest.raises(ValueError, match=f"No archkeel-core for {platform!r}"):
        hook.wheel_tag(platform)


def _manylinux(arch: str, newest: int) -> list[str]:
    # packaging 26 yields the generic tag first, then each glibc version down to 2.17.
    versions = [f"manylinux_2_{minor}_{arch}" for minor in range(newest, 16, -1)]
    return [f"linux_{arch}", *versions, f"manylinux2014_{arch}"]


@pytest.mark.parametrize(
    "tags,platform",
    [
        (_manylinux("x86_64", 39), "manylinux_2_39_x86_64"),
        (_manylinux("aarch64", 36), "manylinux_2_36_aarch64"),
        (["linux_x86_64", "musllinux_1_2_x86_64", "musllinux_1_1_x86_64"], "musllinux_1_2_x86_64"),
        (["macosx_15_0_arm64", "macosx_15_0_universal2", "macosx_11_0_arm64"], "macosx_15_0_arm64"),
        (["macosx_14_0_x86_64", "macosx_14_0_intel", "macosx_10_9_x86_64"], "macosx_14_0_x86_64"),
        (["win_amd64"], "win_amd64"),
    ],
    ids=["ubuntu-glibc", "aarch64-glibc", "alpine-musl", "macos-arm64", "macos-x86_64", "windows"],
)
def test_the_host_platform_is_its_first_supported_tag(tags: list[str], platform: str) -> None:
    assert hook.host_platform(tags) == platform


@pytest.mark.parametrize(
    "tags",
    [["linux_x86_64"], _manylinux("i686", 39), ["win_arm64"], []],
    ids=["generic-only", "linux-i686", "windows-arm64", "no-tag"],
)
def test_a_host_without_a_supported_tag_is_a_clear_error(tags: list[str]) -> None:
    first = repr(tags[0]) if tags else "this host"
    with pytest.raises(ValueError, match=f"No archkeel-core for {first}"):
        hook.host_platform(tags)


def _data() -> dict[str, Any]:
    return {"pure_python": True, "infer_tag": False, "force_include": {}}


def test_without_a_request_the_hook_refuses_the_wheel(tmp_path: Path) -> None:
    # A wheel without the core gives a package that refuses each run (AD-436).
    data = _data()
    with pytest.raises(ValueError, match="must carry the core binary archkeel-core"):
        hook.bundle(tmp_path, VERSION, "", data)
    assert data == _data()


def _executable(path: Path) -> Path:
    path.write_bytes(b"binary")
    path.chmod(0o755)
    return path


def test_a_prebuilt_binary_goes_into_the_package_data(tmp_path: Path) -> None:
    binary = _executable(tmp_path / "core")
    data = _data()
    hook.bundle(tmp_path, VERSION, str(binary), data, platform="manylinux_2_17_x86_64")
    digest = hashlib.sha256(b"binary").hexdigest()
    record = tmp_path / "native/.digests" / f"{digest}.sha256"
    assert data == {
        "pure_python": False,
        "infer_tag": False,
        "tag": "py3-none-manylinux_2_17_x86_64",
        "force_include": {str(binary): MEMBER, str(record): f"{MEMBER}.sha256"},
    }
    # The shell starts the binary only when its file has the digest that the wheel records (AD-432).
    assert record.read_text() == digest
    hook.bundle(tmp_path, VERSION, str(binary), data, platform="win_amd64")
    assert data["force_include"] == {
        str(binary): f"{MEMBER}.exe",
        str(record): f"{MEMBER}.exe.sha256",
    }


@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit")
def test_a_prebuilt_binary_must_be_an_absolute_executable_file(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.write_bytes(b"binary")
    for request, message in (
        ("core", "must be an absolute path"),
        (str(tmp_path / "missing"), "is not an executable file"),
        (str(plain), "is not an executable file"),
    ):
        with pytest.raises(ValueError, match=message):
            hook.bundle(tmp_path, VERSION, request, _data(), platform="win_amd64")


def test_a_cargo_request_without_native_sources_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="has no native/Cargo.toml"):
        hook.bundle(tmp_path, VERSION, "1", _data(), platform="win_amd64")


REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


def _crate(name: str, version: str, license: str | None, source: str | None) -> dict[str, Any]:
    prefix = f"{REGISTRY}#" if source else "path+file:///checkout/native/x#"
    identity = f"{prefix}{name}@{version}"
    return {"id": identity, "name": name, "version": version, "license": license, "source": source}


def _metadata(*crates: dict[str, Any], edges: dict[str, list[tuple[str, str | None]]]) -> Any:
    ids = {crate["name"]: crate["id"] for crate in crates}
    nodes = [
        {
            "id": crate["id"],
            "deps": [
                {"pkg": ids[name], "dep_kinds": [{"kind": kind, "target": None}]}
                for name, kind in edges.get(crate["name"], [])
            ],
        }
        for crate in crates
    ]
    return {"packages": list(crates), "resolve": {"root": None, "nodes": nodes}}


def test_the_sbom_lists_each_crate_that_the_binary_links() -> None:
    metadata = _metadata(
        _crate(hook.BINARY, "0.0.0", "MIT", None),
        _crate("archkeel-wire", "0.0.0", "MIT", None),
        _crate("flate2", "1.1.9", "MIT OR Apache-2.0", REGISTRY),
        _crate("version_check", "0.9.5", "MIT/Apache-2.0", REGISTRY),
        _crate("only-for-build", "1.0.0", "MIT", REGISTRY),
        _crate("only-for-tests", "1.0.0", "MIT", REGISTRY),
        edges={
            hook.BINARY: [("archkeel-wire", None), ("only-for-build", "build")],
            "archkeel-wire": [("flate2", None), ("only-for-tests", "dev")],
            "flate2": [("version_check", None)],
        },
    )
    lock = {("flate2", "1.1.9"): "a" * 64, ("version_check", "0.9.5"): "b" * 64}

    sbom = hook.cyclonedx(metadata, lock, "5.0.0")

    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"] == {
        "type": "application",
        "bom-ref": hook.BINARY,
        "name": hook.BINARY,
        "version": "5.0.0",
        "licenses": [{"expression": "MIT"}],
    }
    assert sbom["components"] == [
        {
            "type": "library",
            "bom-ref": "archkeel-wire",
            "name": "archkeel-wire",
            "version": "5.0.0",
            "licenses": [{"expression": "MIT"}],
        },
        {
            "type": "library",
            "bom-ref": "pkg:cargo/flate2@1.1.9",
            "name": "flate2",
            "version": "1.1.9",
            "purl": "pkg:cargo/flate2@1.1.9",
            "licenses": [{"expression": "MIT OR Apache-2.0"}],
            "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
        },
        {
            "type": "library",
            "bom-ref": "pkg:cargo/version_check@0.9.5",
            "name": "version_check",
            "version": "0.9.5",
            "purl": "pkg:cargo/version_check@0.9.5",
            "licenses": [{"expression": "MIT OR Apache-2.0"}],
            "hashes": [{"alg": "SHA-256", "content": "b" * 64}],
        },
    ]
    assert sbom["dependencies"] == [
        {"ref": hook.BINARY, "dependsOn": ["archkeel-wire"]},
        {"ref": "archkeel-wire", "dependsOn": ["pkg:cargo/flate2@1.1.9"]},
        {"ref": "pkg:cargo/flate2@1.1.9", "dependsOn": ["pkg:cargo/version_check@0.9.5"]},
        {"ref": "pkg:cargo/version_check@0.9.5", "dependsOn": []},
    ]
    # A local path never goes into the SBOM: the wheel must not depend on the build directory.
    assert "file://" not in json.dumps(sbom)


@pytest.mark.parametrize(
    "change,message",
    [("license", "has no license"), ("checksum", "has no checksum in Cargo.lock")],
)
def test_an_sbom_without_license_or_checksum_is_a_clear_error(change: str, message: str) -> None:
    flate2 = _crate("flate2", "1.1.9", None if change == "license" else "MIT", REGISTRY)
    metadata = _metadata(
        _crate(hook.BINARY, "0.0.0", "MIT", None), flate2, edges={hook.BINARY: [("flate2", None)]}
    )
    lock = {} if change == "checksum" else {("flate2", "1.1.9"): "a" * 64}
    with pytest.raises(ValueError, match=f"flate2 1.1.9 {message}"):
        hook.cyclonedx(metadata, lock, VERSION)


def _tool(name: str) -> str:
    found = shutil.which(name)
    # A Rust toolchain is required only for changes in native/; CI always has one.
    if found is None and os.environ.get("CI"):
        pytest.fail(f"CI must provide {name} for the native wheel tests.")
    if found is None:
        pytest.skip(f"{name} is not installed; install it to test the native wheel.")
    return found


def _build(output: Path, *arguments: str, **environment: str) -> subprocess.CompletedProcess[str]:
    uv = _tool("uv")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ARCHKEEL_BUNDLE_NATIVE", "HATCH_BUILD_NO_HOOKS", "VIRTUAL_ENV"}
    }
    env.update(SETUPTOOLS_SCM_PRETEND_VERSION=VERSION, SOURCE_DATE_EPOCH="315532800")
    env.update(environment)
    return subprocess.run(
        [uv, "build", "--no-sources", "--out-dir", str(output), *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_wheel_build_without_the_core_refuses_from_the_checkout_and_from_the_sdist(
    tmp_path: Path,
) -> None:
    refused = _build(tmp_path / "wheel", "--wheel", str(ROOT))
    assert refused.returncode != 0 and hook.NO_CORE in refused.stderr, refused.stderr
    # The sdist has no native sources: it builds without the core, and its wheel needs the core.
    built = _build(tmp_path / "sdist", "--sdist", str(ROOT))
    assert built.returncode == 0, built.stderr
    (sdist,) = (tmp_path / "sdist").glob("archkeel-*.tar.gz")
    refused = _build(tmp_path / "wheel", "--wheel", str(sdist))
    assert refused.returncode != 0 and hook.NO_CORE in refused.stderr, refused.stderr
    cargo = _build(tmp_path / "wheel", "--wheel", str(sdist), ARCHKEEL_BUNDLE_NATIVE="1")
    assert cargo.returncode != 0 and "has no native/Cargo.toml" in cargo.stderr, cargo.stderr
    assert not list((tmp_path / "wheel").glob("*.whl"))


def _bundled_wheel(output: Path) -> Path:
    # `make native-wheel` gives the wheel that CI uploads; without it, the test builds one.
    given = os.environ.get("ARCHKEEL_NATIVE_WHEEL")
    if given:
        return Path(given).resolve()
    _tool("cargo")
    _tool("cargo-auditable")
    built = _build(output, "--wheel", str(ROOT), ARCHKEEL_BUNDLE_NATIVE="1")
    assert built.returncode == 0, built.stderr
    (wheel,) = output.glob("*.whl")
    return wheel


def _checksums() -> dict[tuple[str, str], str]:
    lock = tomllib.loads((ROOT / "native/Cargo.lock").read_text())
    return {
        (crate["name"], crate["version"]): crate["checksum"]
        for crate in lock["package"]
        if "checksum" in crate
    }


@pytest.mark.native_wheel
def test_a_bundled_wheel_carries_the_core_its_digest_and_its_sbom(tmp_path: Path) -> None:
    wheel = _bundled_wheel(tmp_path / "dist")
    version = wheel.name.split("-")[1]

    tag = hook.wheel_tag(hook.host_platform(platform_tags()))
    assert wheel.name == f"archkeel-{version}-{tag}.whl"
    # An installer of this host accepts the wheel.
    assert tag.split("-")[2] in {item.platform for item in sys_tags()}
    windows = tag.endswith("win_amd64")
    member = MEMBER + (".exe" if windows else "")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        dist_info = f"archkeel-{version}.dist-info"
        assert "Root-Is-Purelib: false" in archive.read(f"{dist_info}/WHEEL").decode()
        # The core links each collector, so it is the only binary of the wheel (AD-436).
        native = sorted(name for name in names if name.startswith("archkeel/_native/"))
        assert native == [member, member + ".sha256"]
        if not windows:
            assert stat.S_IMODE(archive.getinfo(member).external_attr >> 16) == 0o755
        binary = archive.read(member)
        assert archive.read(member + ".sha256").decode() == hashlib.sha256(binary).hexdigest()
        sboms = [name for name in names if name.startswith(f"{dist_info}/sboms/")]
        assert sboms == [f"{dist_info}/sboms/{hook.BINARY}.cdx.json"]
        sbom = json.loads(archive.read(sboms[0]))
        assert f"{sboms[0]}," in archive.read(f"{dist_info}/RECORD").decode()
    # cargo auditable puts the dependency list into a section of the binary.
    assert b".dep-v0" in binary
    # AD-323: the test-only `dump` feature is not in the binary that the wheel ships.
    assert b"dump request is not JSON" not in binary
    assert sbom["metadata"]["component"]["name"] == hook.BINARY
    assert sbom["metadata"]["component"]["version"] == version
    linked = {item["name"]: item for item in sbom["components"]}
    collectors = {"archkeel-typescript-collector", "archkeel-rust-collector", "archkeel-collect"}
    assert collectors | {"archkeel-eval", "tree-sitter", "syn", "serde_json", "sha2"} <= set(linked)
    assert linked["flate2"]["hashes"] == [
        {"alg": "SHA-256", "content": _checksums()["flate2", linked["flate2"]["version"]]}
    ]


def test_the_build_hook_reads_cargo_output_as_utf8_on_any_locale() -> None:
    # Windows decodes a pipe with cp1252, which has no byte 0x8f; cargo prints UTF-8.
    probe = (
        "import sys\n"
        "from importlib.util import module_from_spec, spec_from_file_location\n"
        "from pathlib import Path\n"
        "spec = spec_from_file_location('hook', sys.argv[1])\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "child = 'import sys; sys.stdout.buffer.write(bytes([0xc3, 0xa9, 0xe2, 0x80, 0x8f]))'\n"
        "print(ascii(module._run([sys.executable, '-c', child], Path('.'))))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe, str(ROOT / "native/hatch_build.py")],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == ascii("é‏")
