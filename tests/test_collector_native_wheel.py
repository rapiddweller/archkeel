# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-317: a platform wheel carries the native TypeScript collector.

Consumer: the release build, which sets `ARCHKEEL_BUNDLE_NATIVE`. The host does not use the
bundled binary yet, so the test finds it with `importlib.resources` itself.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import sysconfig
import zipfile
import zlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from packaging.tags import platform_tags, sys_tags

ROOT = Path(__file__).parents[1]
MEMBER = "archkeel/_native/archkeel-typescript-collector"
VERSION = "0.0.0"


def _hook() -> ModuleType:
    spec = spec_from_file_location("archkeel_hatch_build", ROOT / "native/hatch_build.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _hook()


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
    assert data == {
        "pure_python": False,
        "infer_tag": False,
        "tag": "py3-none-manylinux_2_17_x86_64",
        "force_include": {str(binary): MEMBER},
    }
    hook.bundle(tmp_path, VERSION, str(binary), data, platform="win_amd64")
    assert data["force_include"][str(binary)] == f"{MEMBER}.exe"


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


def test_a_bundled_wheel_installs_and_its_binary_replies(tmp_path: Path) -> None:
    _tool("cargo")
    uv = _tool("uv")
    wheel = _build_wheel(tmp_path / "dist", ARCHKEEL_BUNDLE_NATIVE="1")

    tag = hook.wheel_tag(hook.host_platform(platform_tags()))
    assert wheel.name == f"archkeel-{VERSION}-{tag}.whl"
    # An installer of this host accepts the wheel.
    assert tag.split("-")[2] in {item.platform for item in sys_tags()}
    windows = tag.endswith("win_amd64")
    member = MEMBER + (".exe" if windows else "")
    with zipfile.ZipFile(wheel) as archive:
        assert (
            "Root-Is-Purelib: false" in archive.read(f"archkeel-{VERSION}.dist-info/WHEEL").decode()
        )
        if not windows:
            assert stat.S_IMODE(archive.getinfo(member).external_attr >> 16) == 0o755

    venv = tmp_path / "venv"
    for command in (
        [uv, "venv", "--offline", "--python", sys.executable, str(venv)],
        [uv, "pip", "install", "--offline", "--no-deps", "--python", str(venv), str(wheel)],
    ):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    python = venv / ("Scripts/python.exe" if windows else "bin/python")
    # The wheel is installed without its dependencies; this environment supplies them.
    lookup = subprocess.run(
        [str(python), "-c", LOOKUP],
        env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert lookup.returncode == 0, lookup.stderr
    package, installed, executable = json.loads(lookup.stdout)
    assert Path(package).is_relative_to(venv)
    assert Path(installed) == Path(package) / member.removeprefix("archkeel/")
    assert executable

    reply = subprocess.run(
        [str(installed)], input=json.dumps(_request(tmp_path)).encode(), capture_output=True
    )
    assert reply.returncode == 0, reply.stderr
    decoded = json.loads(zlib.decompress(reply.stdout))
    assert decoded["protocol_version"] == "9.0.0"
    assert decoded["facts"]["adapter"]["version"] == VERSION
    assert decoded["facts"]["coverage"]["selected_files"] == ["src/app.ts"]


# The host does not use the bundled binary yet (PR 4.4 adds this lookup to cli/observe.py).
LOOKUP = """
import json
import os
import sysconfig
from importlib.resources import files

package = files("archkeel")
name = "archkeel-typescript-collector" + (sysconfig.get_config_var("EXE") or "")
binary = package / "_native" / name
print(json.dumps([str(package), str(binary), binary.is_file() and os.access(binary, os.X_OK)]))
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
