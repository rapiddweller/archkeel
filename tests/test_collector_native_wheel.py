# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-317, AD-335: a platform wheel carries the native TypeScript and Rust collectors.

Consumer: the release build, which sets `ARCHKEEL_BUNDLE_NATIVE`. The wheel does not carry the
core yet (AD-432), so the installed shell refuses each run. The test finds the two collector
binaries with `importlib.resources` itself and runs them directly. The test marked
`native_wheel` needs a Rust toolchain: `make native-wheel` runs it on each target of the wheel
matrix in Full verification.
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
import zlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from native_wheel_rust import check_rust_binary
from packaging.tags import platform_tags, sys_tags

ROOT = Path(__file__).parents[1]
MEMBER = "archkeel/_native/archkeel-typescript-collector"
RUST_MEMBER = "archkeel/_native/archkeel-rust-collector"
RUST_BINARY = "archkeel-rust-collector"
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
    with pytest.raises(ValueError, match=f"No native TypeScript collector for {platform!r}"):
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
    with pytest.raises(ValueError, match=f"No native TypeScript collector for {first}"):
        hook.host_platform(tags)


def _data() -> dict[str, Any]:
    return {"pure_python": True, "infer_tag": False, "force_include": {}}


def test_without_a_request_the_wheel_stays_pure(tmp_path: Path) -> None:
    data = _data()
    hook.bundle(tmp_path, VERSION, "", data)
    assert data == _data()


def _executable(path: Path) -> Path:
    path.write_bytes(b"binary")
    path.chmod(0o755)
    return path


def test_a_prebuilt_binary_goes_into_the_package_data(tmp_path: Path) -> None:
    binary = _executable(tmp_path / "collector")
    data = _data()
    hook.bundle(tmp_path, VERSION, str(binary), data, platform="manylinux_2_17_x86_64")
    digests = tmp_path / "native/.digests"
    record = digests / f"{hook.BINARY}.sha256"
    assert data == {
        "pure_python": False,
        "infer_tag": False,
        "tag": "py3-none-manylinux_2_17_x86_64",
        "force_include": {str(binary): MEMBER, str(record): f"{MEMBER}.sha256"},
    }
    # The host starts the binary only when its file has the digest that the wheel records (AD-352).
    assert record.read_text() == hashlib.sha256(b"binary").hexdigest()
    hook.bundle(tmp_path, VERSION, str(binary), data, platform="win_amd64")
    assert data["force_include"][str(binary)] == f"{MEMBER}.exe"
    exe_record = digests / f"{hook.BINARY}.exe.sha256"
    assert data["force_include"][str(exe_record)] == f"{MEMBER}.exe.sha256"


@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit")
def test_a_prebuilt_binary_must_be_an_absolute_executable_file(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.write_bytes(b"binary")
    for request, message in (
        ("collector", "must be an absolute path"),
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


def _build_wheel(output: Path, **environment: str) -> Path:
    uv = _tool("uv")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ARCHKEEL_BUNDLE_NATIVE", "HATCH_BUILD_NO_HOOKS", "VIRTUAL_ENV"}
    }
    env.update(SETUPTOOLS_SCM_PRETEND_VERSION=VERSION, SOURCE_DATE_EPOCH="315532800")
    env.update(environment)
    built = subprocess.run(
        [uv, "build", "--wheel", "--no-sources", "--out-dir", str(output), str(ROOT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    (wheel,) = output.glob("*.whl")
    return wheel


def _listing(wheel: Path) -> list[tuple[str, int]]:
    with zipfile.ZipFile(wheel) as archive:
        return [(item.filename, item.external_attr >> 16) for item in archive.infolist()]


def test_the_default_wheel_is_the_pure_wheel_without_the_hook(tmp_path: Path) -> None:
    default = _build_wheel(tmp_path / "default")
    without_hook = _build_wheel(tmp_path / "without-hook", HATCH_BUILD_NO_HOOKS="true")

    assert default.name == f"archkeel-{VERSION}-py3-none-any.whl"
    assert default.name == without_hook.name
    assert _listing(default) == _listing(without_hook)
    assert default.read_bytes() == without_hook.read_bytes()


def _bundled_wheel(output: Path) -> Path:
    # `make native-wheel` gives the wheel that CI uploads; without it, the test builds one.
    given = os.environ.get("ARCHKEEL_NATIVE_WHEEL")
    if given:
        return Path(given).resolve()
    _tool("cargo")
    _tool("cargo-auditable")
    return _build_wheel(output, ARCHKEEL_BUNDLE_NATIVE="1")


def _checksums() -> dict[tuple[str, str], str]:
    lock = tomllib.loads((ROOT / "native/Cargo.lock").read_text())
    return {
        (crate["name"], crate["version"]): crate["checksum"]
        for crate in lock["package"]
        if "checksum" in crate
    }


@pytest.mark.native_wheel
def test_a_bundled_wheel_installs_and_its_binary_replies(tmp_path: Path) -> None:
    uv = _tool("uv")
    wheel = _bundled_wheel(tmp_path / "dist")
    version = wheel.name.split("-")[1]

    tag = hook.wheel_tag(hook.host_platform(platform_tags()))
    assert wheel.name == f"archkeel-{version}-{tag}.whl"
    # An installer of this host accepts the wheel.
    assert tag.split("-")[2] in {item.platform for item in sys_tags()}
    windows = tag.endswith("win_amd64")
    member = MEMBER + (".exe" if windows else "")
    with zipfile.ZipFile(wheel) as archive:
        dist_info = f"archkeel-{version}.dist-info"
        assert "Root-Is-Purelib: false" in archive.read(f"{dist_info}/WHEEL").decode()
        if not windows:
            assert stat.S_IMODE(archive.getinfo(member).external_attr >> 16) == 0o755
        # cargo auditable puts the dependency list into a section of the binary.
        assert b".dep-v0" in archive.read(member)
        recorded = archive.read(member + ".sha256").decode()
        assert recorded == hashlib.sha256(archive.read(member)).hexdigest()
        sbom_member = f"{dist_info}/sboms/{hook.BINARY}.cdx.json"
        sbom = json.loads(archive.read(sbom_member))
        assert f"{sbom_member}," in archive.read(f"{dist_info}/RECORD").decode()
        # AD-335: the Rust collector is the third binary of the wheel, with its own SBOM.
        rust_member = RUST_MEMBER + (".exe" if windows else "")
        if not windows:
            assert stat.S_IMODE(archive.getinfo(rust_member).external_attr >> 16) == 0o755
        assert b".dep-v0" in archive.read(rust_member)
        rust_sbom_member = f"{dist_info}/sboms/{RUST_BINARY}.cdx.json"
        rust_sbom = json.loads(archive.read(rust_sbom_member))
        assert f"{rust_sbom_member}," in archive.read(f"{dist_info}/RECORD").decode()
    rust_linked = {item["name"] for item in rust_sbom["components"]}
    assert rust_sbom["metadata"]["component"]["name"] == RUST_BINARY
    assert {"archkeel-wire", "syn", "proc-macro2", "serde_json"} <= rust_linked
    assert "tree-sitter" not in rust_linked
    assert sbom["metadata"]["component"]["version"] == version
    linked = {item["name"]: item for item in sbom["components"]}
    assert {"archkeel-wire", "flate2", "serde_json", "sha2"} <= linked.keys()
    assert linked["flate2"]["hashes"] == [
        {"alg": "SHA-256", "content": _checksums()["flate2", linked["flate2"]["version"]]}
    ]

    venv = tmp_path / "venv"
    for command in (
        [uv, "venv", "--offline", "--python", sys.executable, str(venv)],
        [uv, "pip", "install", "--offline", "--no-deps", "--python", str(venv), str(wheel)],
    ):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    python = venv / ("Scripts/python.exe" if windows else "bin/python")
    # The package has no dependencies, so the new environment needs only the wheel.
    lookup = subprocess.run(
        [str(python), "-c", LOOKUP], capture_output=True, text=True, check=False
    )
    assert lookup.returncode == 0, lookup.stderr
    package, installed, executable, rust, rust_executable = json.loads(lookup.stdout)
    assert Path(package).is_relative_to(venv)
    assert Path(installed) == Path(package) / member.removeprefix("archkeel/")
    assert executable and rust_executable
    # The Rust binary replies, and the installed shell refuses without the core.
    check_rust_binary(tmp_path, python, rust, version)

    reply = subprocess.run(
        [str(installed)], input=json.dumps(_request(tmp_path)).encode(), capture_output=True
    )
    assert reply.returncode == 0, reply.stderr
    decoded = json.loads(zlib.decompress(reply.stdout))
    assert decoded["protocol_version"] == "9.0.0"
    assert decoded["facts"]["adapter"]["version"] == version
    assert decoded["facts"]["coverage"]["selected_files"] == ["src/app.ts"]
    # AD-323: the test-only `dump` feature is not in the binary that the wheel ships. With the
    # feature, `--dump` would read file names on stdin and print JSON. Here it is an ignored
    # argument: the binary reads a collection request, finds none, and fails without output.
    dumped = subprocess.run([str(installed), "--dump"], input=b"", capture_output=True)
    assert dumped.returncode != 0
    assert dumped.stdout == b""
    assert b"dump request is not JSON" not in Path(installed).read_bytes()


# The two collector binaries of the installed package (AD-317, AD-335).
LOOKUP = """
import json
import os
import sysconfig
from importlib.resources import files

package = files("archkeel")
suffix = sysconfig.get_config_var("EXE") or ""
binary = package / "_native" / ("archkeel-typescript-collector" + suffix)
rust = package / "_native" / ("archkeel-rust-collector" + suffix)
executable = [item.is_file() and os.access(item, os.X_OK) for item in (binary, rust)]
print(json.dumps([str(package), str(binary), executable[0], str(rust), executable[1]]))
"""


def _request(root: Path) -> dict[str, Any]:
    (root / "src").mkdir()
    (root / "src/app.ts").write_text("export const value = 1;\n")
    (root / "tsconfig.json").write_text("{}")
    return {
        "protocol_version": "9.0.0",
        "snapshot": {"root": str(root), "git_head": "a" * 40, "dirty": False},
        "scope": {"roots": ["src"], "namespace": "shop", "exclude_test_sources": False},
        "resolver": {"language": "typescript", "tsconfig": "tsconfig.json"},
    }


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
