# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880 PR 8 slice 1: the native Dart discovery equals the discovery of the Python collector.

Consumer: the host, which reads the inputs, the file facts and the gaps of a Dart reply. The
native collector must select, read and report the same sources and problems as the Python
collector. The gate compares the reply sections of both on a tree with each problem kind, on
the Dart fixtures and on the demo variants.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "dart_discovery_parity", ROOT / "tools/dart_discovery_parity.py"
)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
sys.modules["dart_discovery_parity"] = parity
spec.loader.exec_module(parity)

PUBSPEC = "name: shop\nenvironment:\n  sdk: ^3.0.0\n"


@pytest.fixture(scope="module")
def binary() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo for the native collector tests.")
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    install_rust_toolchain(cargo)
    built: Path = parity.build(release=False)
    return built


def _tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
    return root


def _compare(binary: Path, root: Path, roots: tuple[str, ...]) -> object:
    result = parity.Result("tree")
    parity.compare(parity.Corpus("tree", root, roots, "shop"), binary, result)
    return result


def test_each_problem_kind_gives_the_python_gap(binary: Path, tmp_path: Path) -> None:
    files: dict[str, str | bytes] = {
        "pubspec.yaml": PUBSPEC,
        "lib/a.dart": "class A {}\n",
        "lib/blank.dart": " \n",
        "lib/first_line_blank.dart": "\nclass B {}\n",
        "lib/latin1.dart": b"// caf\xe9\nclass C {}\n",
        "lib/9bad.dart": "class D {}\n",
        "lib/x-y.dart": "class E {}\n",
        "lib/x_y.dart": "class F {}\n",
        "lib/.dart_tool/gen.dart": "class G {}\n",
        "lib/owner.dart": "part 'piece.dart';\n",
        "lib/piece.dart": "part of 'owner.dart';\nclass H {}\n",
        "lib/broken.dart": "class {\n",
        "other/target.dart": "class I {}\n",
    }
    root = _tree(tmp_path / "snapshot", files)
    if os.name != "nt":
        (root / "lib/link.dart").symlink_to(root / "lib/a.dart")
        (root / "lib/linked").symlink_to(root / "other")
    result = _compare(binary, root, ("lib", "missing"))
    assert result.problems == []
    assert result.equal_gaps == result.gaps >= 4
    # The parse and the parts remove 5 file facts: the syntax error, the source that is not
    # UTF-8, the `part of` file and both colliding sources, which have no unique owner.
    assert result.deferred == 5
    assert result.equal_files + result.deferred == result.files


@pytest.mark.parametrize(
    ("files", "label"),
    [
        ({"lib/a.dart": ""}, "no pubspec"),
        ({"pubspec.yaml": "name: 9x\n"}, "invalid name"),
        ({"pubspec.yaml": "name: shop\nenvironment:\n  sdk: '*'\n"}, "invalid sdk"),
        ({"pubspec.yaml": "name: shop\nenvironment:\n  sdk: ^3.1.0 # c\n"}, "declared sdk"),
    ],
)
def test_a_missing_or_invalid_pubspec_gives_the_python_result(
    binary: Path, tmp_path: Path, files: dict[str, str | bytes], label: str
) -> None:
    root = _tree(tmp_path / "snapshot", {"lib/a.dart": "class A {}\n", **files})
    assert _compare(binary, root, ("lib",)).problems == [], label


def test_a_snapshot_root_that_is_a_link_or_missing_stops_both_collectors(
    binary: Path, tmp_path: Path
) -> None:
    real = _tree(tmp_path / "real", {"pubspec.yaml": PUBSPEC, "lib/a.dart": ""})
    roots: list[Path] = [tmp_path / "absent"]
    if os.name != "nt":
        (tmp_path / "link").symlink_to(real)
        roots.append(tmp_path / "link")
    for root in roots:
        result = _compare(binary, root, ("lib",))
        assert result.problems == [], root.name


def test_a_repeated_root_and_a_root_after_pubspec_give_the_python_sections(
    binary: Path, tmp_path: Path
) -> None:
    files: dict[str, str | bytes] = {
        "pubspec.yaml": PUBSPEC,
        "lib/a.dart": "",
        "test/a_test.dart": "",
    }
    root = _tree(tmp_path / "snapshot", files)
    result = _compare(binary, root, ("lib", "test", "lib"))
    assert result.problems == []
    assert result.equal_files == result.files == 2


def test_the_fixtures_and_demos_give_the_python_sections(binary: Path) -> None:
    for result in parity.run(binary, True, []):
        assert result.problems == [], result.name
        assert result.equal_files + result.deferred == result.files > 0, result.name


def test_the_binary_refuses_a_request_and_the_wheel_does_not_carry_it(binary: Path) -> None:
    """No host path runs the native Dart collector, so its reply can never give PASS."""
    run = subprocess.run([binary], input=b"{}", capture_output=True, check=False)
    assert run.returncode == 2
    assert b"no Dart request" in run.stderr
    assert '"archkeel-dart-collector"' not in (ROOT / "native/hatch_build.py").read_text()
