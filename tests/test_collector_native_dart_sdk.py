# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-385: the SDK support flag and gaps equal the Python collection boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dart_sdk_parity as parity  # noqa: E402


@pytest.fixture(scope="module")
def binary() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo for native collector tests.")
        pytest.skip("cargo is not installed; install Rust to test native changes.")
    install_rust_toolchain(cargo)
    return parity.build(release=False)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "3.0",
        "any",
        "^3",
        "^2.12",
        "^2.11",
        "^3.12.999",
        "^3.13",
        "^4",
        ">=2.12 <4",
        ">2.11 <4",
        ">3.12 <4",
        ">3.13",
        "<4",
        "<=3.12",
        "=3.12",
        ">=3.12 <=3.12",
        ">=3.12 >3.12 <=3.12",
        ">3.12 >=3.12 <=3.12",
        ">=3.12 <=3.12 <3.12",
        ">=3.12 <3.12 <=3.12",
        ">3.12 <=3.12",
        ">=3.12 <3.12",
        ">=3 <2",
        ">=2 >=3 <4",
        ">=3 >=2 <4",
        ">=3,<=3",
        ">=3<=3",
        "^0.0.1",
        "^0.2",
        "^0",
        "^03.012.00",
        "^3.12-dev.1+build",
        "^3.12--",
        "^3.12+...",
        "^3.12-",
        "^3.12+",
        "^3.12.0.1",
        ">=3 || <4",
        ">=3,",
        ",>=3",
        "^3 <4",
        ">=3 ^4",
        ">=٣.١٢",
        "=３.１２",
        "\u001c>=\u20033.12\u0085<4\u2028",
        "\ufeff>=3",
        ">=².12",
        ">=3.12-beta<4",
        ">=3.12+meta>=3.12",
        ">=3.12, <9999999999999999999999999999999999999",
        ">=3.12.9999999999999999999999999999999999999 <3.13",
        ">=3.12.9999999999999999999999999999999999999 <3.12.9999999999999999999999999999999999998",
        "^3.12\x00",
        "=3.12\n",
        "=3.12\n=3.12",
        "=3.12,\n=3.12",
        "^3.12.0.",
        "^3.12.0.-a",
    ],
)
def test_sdk_boundary_equals_python(binary: Path, value: str | None) -> None:
    item = {"state": "declared", "constraint": value}
    actual = parity.native(binary, [item])[0]
    assert parity.canonical(parity.payload(actual)) == parity.canonical(parity.python(item))


@pytest.mark.parametrize("state", ["declared", "requirement_missing", "requirement_invalid"])
def test_sdk_state_precedes_constraint(binary: Path, state: str) -> None:
    item = {"state": state, "constraint": ">=4"}
    assert parity.payload(parity.native(binary, [item])[0]) == parity.python(item)


def test_long_constraints_stop_with_named_gaps_within_ten_seconds(binary: Path) -> None:
    started = time.monotonic()
    rows = parity.native(
        binary,
        [
            {"state": "declared", "constraint": ">=3 " * 200_000},
            {"state": "declared", "constraint": "^" + "0" * 4301 + "3.12"},
        ],
    )
    assert time.monotonic() - started < 10
    for row, name in zip(rows, ["SdkConstraintWorkLimit", "SdkConstraintDigitLimit"], strict=True):
        assert not row["sdk_supported"]
        assert len(row["gaps"]) == 1
        assert name in row["gaps"][0]["data"]["message"]


def test_exact_work_and_integer_digit_boundary(binary: Path) -> None:
    items = [
        {"state": "declared", "constraint": text}
        for text in [
            ">=3.12.0 <4",
            "^" + "0" * 4299 + "3.12",
            "^3.12" + "0" * 4298,
        ]
    ]
    rows = parity.native(binary, items)
    assert rows[0]["work"] == 86
    for item, row in zip(items, rows, strict=True):
        assert parity.payload(row) == parity.python(item)


def test_invalid_dump_input_never_disappears(binary: Path) -> None:
    run = subprocess.run(
        [str(binary), "--dump-sdk"],
        input='{"state":"other"}\n',
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run.returncode == 1
    assert not run.stdout
    assert run.stderr


def test_sdk_gap_reaches_the_existing_section_builder(binary: Path, tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: shop\nenvironment:\n  sdk: '>=4'\n")
    (tmp_path / "a.dart").write_text("class A {}\n")
    run = subprocess.run(
        [str(binary), "--dump", str(tmp_path), "shop", "."],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    value = json.loads(run.stdout)
    assert len(value["files"]) == 1
    assert value["files"][0]["rel_path"] == "a.dart"
    gaps = value["gaps"]
    assert [gap["kind"] for gap in gaps] == ["SdkConstraintError"]
    assert gaps[0] == parity.python({"state": "declared", "constraint": ">=4"})["gaps"][0]


def test_parity_tool_covers_fixtures_demos_and_hostile_snapshots(
    binary: Path, tmp_path: Path
) -> None:
    results = parity.run(binary, demos=True, items=[], scratch=tmp_path)
    assert all(row.different == 0 for row in results)
    assert sum(row.files for row in results) >= 50
    assert any(row.name == "hostile filesystem snapshots" and row.files >= 40 for row in results)
