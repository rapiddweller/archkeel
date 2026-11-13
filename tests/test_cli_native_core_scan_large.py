# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-420: large ordinary source is not deep source, and repeated reads retain one input."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_cli_native_core_scan import built
from test_cli_native_core_scan_work import ROOT, input_measurement, project, release_core

from archkeel.cli import native_scan

__all__ = ["built", "release_core"]


def complete_contract(root: Path) -> None:
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract.pop("declarations", None)
    owner = contract["components"][0]
    owner.update(packages=["shop"], public=["shop"], requires=[])
    contract["components"] = [owner]
    contract["rules"] = [
        {
            "id": "LARGE-COMPLETE",
            "kind": "complete_assignment",
            "source": "shop",
            "rationale": "All generated source is observed.",
            "provenance": ["test"],
            "decided_by": "architect",
        }
    ]
    path.write_text(json.dumps(contract))


def honest_source(language: str, shape: str, size: int) -> str:
    rows = []
    length = 0
    prefix, suffix = "", ""
    if shape == "table":
        prefix, suffix = (
            ("export const table = [\n", "];\n")
            if language == "typescript"
            else ("pub static TABLE: &[(u32, &str)] = &[\n", "];\n")
        )
    for index in range(size):
        if shape == "functions":
            row = (
                f"export function f{index}(x: number) {{ return x + 1; }}\n"
                if language == "typescript"
                else f"pub fn f{index}(x: u32) -> u32 {{ x + 1 }}\n"
            )
        else:
            row = (
                f'[{index}, "item{index}"],\n'
                if language == "typescript"
                else f'({index}, "item{index}"),\n'
            )
        if len(prefix) + length + len(row) + len(suffix) > size:
            break
        rows.append(row)
        length += len(row)
    text = prefix + "".join(rows) + suffix
    return text + " " * (size - len(text))


def unguarded_frame(built: Path, core: Path, frame: dict) -> dict:
    request = frame["self_test"]["collect"]["request"]
    language = request["resolver"]["language"]
    reply = subprocess.run(
        [str(built / f"archkeel-{language}-collector")],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=True,
        timeout=600,
    ).stdout
    root = Path(request["snapshot"]["root"])
    payload = {
        "protocol": "archkeel-core-check-2",
        "contract": {
            "path": "architecture-contract.json",
            "hex": (root / "architecture-contract.json").read_bytes().hex(),
        },
        "insides": [],
        "reply": {"hex": reply.hex()},
        "roots": request["scope"]["roots"],
        "namespace": request["scope"]["namespace"],
        "base": None,
    }
    stdout, _ = native_scan.exchange(str(core), "check", json.dumps(payload).encode())
    return json.loads(stdout)


@pytest.mark.parametrize("size", [100_000, 1_000_000, (4 << 20) - 1])
@pytest.mark.parametrize("shape", ["functions", "table"])
@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_large_honest_source_has_the_unguarded_frame(
    built: Path, release_core: Path, tmp_path: Path, language: str, shape: str, size: int
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0, language)
    complete_contract(root)
    path = root / ("src/large.ts" if language == "typescript" else "src/lib.rs")
    path.write_text(honest_source(language, shape, size))
    assert path.stat().st_size == size
    stdout, code = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    frame = json.loads(stdout)
    assert code == 0, frame["unsupported"]
    assert frame["rules"]["LARGE-COMPLETE"][1] == "PASS"
    assert "request" in frame["self_test"]["collect"], frame
    plain = unguarded_frame(built, release_core, frame)
    frame["self_test"].pop("collect")
    assert frame == plain


def test_repeated_package_reads_do_not_refuse_a_small_distinct_project(
    built: Path, release_core: Path, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0)
    complete_contract(root)
    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"module": "NodeNext", "moduleResolution": "NodeNext"},
                "include": ["src/**/*.ts"],
            }
        )
    )
    (root / "package.json").write_text(
        json.dumps({"type": "module", "description": "x" * (1 << 20)})
    )
    for index in range(80):
        (root / f"src/m{index}.ts").write_text(f"export const value{index} = {index};\n")
    measured = input_measurement(root, tmp_path / "inputs.json")
    print("Repeated manifest:", json.dumps(measured))
    assert measured["reads"] > 64 << 20
    assert measured["charged"] == measured["distinct"] < 64 << 20
    stdout, code = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    frame = json.loads(stdout)
    assert code == 0, frame["unsupported"]
    assert "request" in frame["self_test"]["collect"], frame
    plain = unguarded_frame(built, release_core, frame)
    frame["self_test"].pop("collect")
    assert frame == plain


def test_ad420_states_linear_units_distinct_input_and_the_way_back() -> None:
    text = (
        ROOT
        / "docs/architecture/decisions"
        / "ad-420-bound-parse-work-before-an-in-process-collector-reads-bytes.md"
    ).read_text()
    for required in ["bytes + tokens", "64 MiB", "once", "**Way back.**"]:
        assert required in text
