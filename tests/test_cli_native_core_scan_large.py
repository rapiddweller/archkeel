# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-420: large ordinary source is not deep source, and repeated reads retain one input."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from core_support import EMPTY_GRAPH, ROOT, SUFFIX
from test_cli_native_core_scan_work import input_measurement, measured_scan, project

from archkeel.cli import native_scan
from archkeel.cli.core_json import CoreError


@pytest.mark.parametrize("shape", ["addition", "casts"])
def test_a_flat_rust_expression_refuses_without_aborting(
    release_core: Path, tmp_path: Path, shape: str
) -> None:
    root = tmp_path / "project"
    request = project(root, 1, 0, "rust")
    expression = "1+" * 2_000_000 + "1" if shape == "addition" else "1" + " as u8" * 600_000
    (root / "src/deep0.rs").write_text(f"pub fn value() -> u8 {{ {expression} }}")
    done, peak = measured_scan(release_core, request)
    assert done.returncode == 2, done.stderr
    assert done.stdout == b""
    assert b"parse_work_limit" in done.stderr and b"Rust operator-work units" in done.stderr
    assert peak is None or peak < 1 << 30


def test_a_rust_expression_below_the_work_limit_keeps_a_frame(
    release_core: Path, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    request = project(root, 1, 0, "rust")
    (root / "src/deep0.rs").write_text("pub fn value() -> u32 { " + "1+" * 8_000 + "1 }")
    done, peak = measured_scan(release_core, request)
    assert done.returncode in (0, 3), done.stderr
    assert json.loads(done.stdout)["self_test"]["collect"]["request"]
    assert peak is None or peak < 1 << 30


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_oversized_source_names_the_gap(release_core: Path, tmp_path: Path, language: str) -> None:
    root = tmp_path / "project"
    request = project(root, 1, 0, language)
    suffix = "rs" if language == "rust" else "ts"
    (root / f"src/deep0.{suffix}").write_text("x" * 50_000_000)
    contract = root / "architecture-contract.json"
    data = json.loads(contract.read_text())
    data["rules"] = [rule for rule in data["rules"] if rule["id"] == "MODULE-CYCLES"]
    contract.write_text(json.dumps(data))
    done, peak = measured_scan(release_core, request)
    frame = json.loads(done.stdout)
    assert frame["status"] == "UNKNOWN"
    assert "over the size limit" in json.dumps(frame["collection_gaps"])
    assert peak is None or peak < 1 << 30


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_two_hundred_thousand_tiny_files_hit_the_survey_budget(
    release_core: Path, tmp_path: Path, language: str
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0, language)
    for group in range(200):
        directory = root / "src" / f"group{group:03}"
        directory.mkdir()
        for number in range(1000):
            (directory / f"file{number:04}.ts").touch()
    done, peak = measured_scan(release_core, request)
    frame = json.loads(done.stdout)
    assert frame["status"] == "UNKNOWN"
    assert "more than 100000 entries" in json.dumps(frame["gaps"])
    assert peak is None or peak < 1 << 30


# #1570: the core refuses a flat Rust expression over 8192 active operator-work units by name.
# A Rust file of a million bytes of `x + 1` bodies, or ten thousand flat concatenations, holds more
# operator work than that, so the scan has no frame: the expected result is the named refusal.
# The refusal is by design; a test that wanted a frame here would test the old limit.
OPERATOR_WORK_REFUSED = {
    ("rust", "functions", 1_000_000),
    ("rust", "functions", (4 << 20) - 1),
    ("rust", "concat", 10_000),
}


def assert_refused_by_operator_work(core: Path, request: dict) -> None:
    with pytest.raises(CoreError) as refused:
        native_scan.exchange(str(core), "scan", json.dumps(request).encode())
    text = str(refused.value)
    assert "parse_work_limit" in text and "8192 active Rust operator-work units" in text, text


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
            "provenance": ["docs/architecture/shop.md"],
            "decided_by": "architect",
        }
    ]
    path.write_text(json.dumps(contract))
    (root / "docs/architecture/shop.md").write_text(EMPTY_GRAPH)


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


def drop_premise(frame: dict) -> None:
    """AD-540: the linked TypeScript collector states one assumption as text; the wire reply of
    the harness carries none. Check that it is a non-empty string before it is left out."""
    language = frame["self_test"]["collect"]["request"]["resolver"]["language"]
    if language == "typescript":
        assert isinstance(frame["premise"], str) and frame["premise"], frame.get("premise")
    else:
        assert "premise" not in frame
    frame.pop("premise", None)


def unguarded_frame(built: Path, core: Path, frame: dict) -> dict:
    """The frame of the same reply through the `check` request of the harness build (#1095)."""
    request = frame["self_test"]["collect"]["request"]
    language = request["resolver"]["language"]
    reply = subprocess.run(
        [str(built / f"archkeel-{language}-collector{SUFFIX}")],
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
    plain = json.loads(stdout)
    # The harness core says so in its engine; the code digest is the one of the release core.
    assert plain["engine"] == frame["engine"] + "+harness"
    plain["engine"] = frame["engine"]
    # AD-466: a check request reads no provenance document. It names that gap and never passes.
    hygiene = plain["unsupported"]["rules"].pop("hygiene:request")
    assert hygiene.startswith("unsupported: the contract hygiene of the request"), hygiene
    # AD-546: the list of gaps with their kinds names the same row once more.
    row = plain["gaps"].pop()
    assert (row["kind"], row["subject"]) == ("contract_hygiene_not_read", "hygiene:request")
    assert row["reason"] == hygiene and plain["gaps"] == []
    # AD-484: the part `explain` names the same cause once more, without a gap.
    assert plain["explain"]["holds"]["rules"].pop("hygiene:request")["kind"] == "other"
    assert plain.pop("status") != "PASS"
    return plain


@pytest.mark.parametrize("size", [100_000, 1_000_000, (4 << 20) - 1])
@pytest.mark.parametrize("shape", ["functions", "table"])
@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_large_honest_source_has_the_unguarded_frame(
    built: Path,
    release_core: Path,
    harness_core: Path,
    tmp_path: Path,
    language: str,
    shape: str,
    size: int,
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0, language)
    complete_contract(root)
    path = root / ("src/large.ts" if language == "typescript" else "src/lib.rs")
    path.write_text(honest_source(language, shape, size))
    assert path.stat().st_size == size
    if (language, shape, size) in OPERATOR_WORK_REFUSED:
        return assert_refused_by_operator_work(release_core, request)
    stdout, code = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    frame = json.loads(stdout)
    assert code == 0, frame["unsupported"]
    assert frame["rules"]["LARGE-COMPLETE"][1] == "PASS"
    assert "request" in frame["self_test"]["collect"], frame
    plain = unguarded_frame(built, harness_core, frame)
    drop_premise(frame)
    frame["self_test"].pop("collect")
    frame.pop("status")
    assert frame == plain


def test_repeated_package_reads_do_not_refuse_a_small_distinct_project(
    built: Path, release_core: Path, harness_core: Path, tmp_path: Path
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
    # #1556: the measurement no longer carries `reads`. The premise is arithmetic: 80 modules read
    # the one-megabyte manifest, 80 MiB of reads in all, over the cap of 64 MiB; the charge counts
    # each input once and stays below it.
    assert 80 * (1 << 20) > 64 << 20
    assert measured["charged"] == measured["distinct"] < 64 << 20
    stdout, code = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    frame = json.loads(stdout)
    assert code == 0, frame["unsupported"]
    assert "request" in frame["self_test"]["collect"], frame
    plain = unguarded_frame(built, harness_core, frame)
    drop_premise(frame)
    frame["self_test"].pop("collect")
    frame.pop("status")
    assert frame == plain


def test_ad420_states_linear_units_distinct_input_and_the_way_back() -> None:
    text = (
        ROOT
        / "docs/architecture/decisions"
        / "ad-420-bound-parse-work-before-an-in-process-collector-reads-bytes.md"
    ).read_text()
    for required in ["bytes + tokens", "64 MiB", "once", "**Way back.**"]:
        assert required in text


def chain_source(language: str, shape: str, count: int) -> str:
    if shape == "branches":
        clauses = " else ".join(
            f"if (x == {index}) {{ return {index}; }}" for index in range(count)
        )
        return (
            f"export function chain(x: number) {{ {clauses} else {{ return -1; }} }}\n"
            if language == "typescript"
            else f"pub fn chain(x: i32) -> i32 {{ {clauses} else {{ return -1; }} }}\n"
        )
    if shape == "concat":
        expression = " + ".join(['"a"'] * count)
        return (
            f"export const chain = {expression};\n"
            if language == "typescript"
            else f"pub fn chain() -> String {{ String::new() + {expression} }}\n"
        )
    expression = "a" + "".join(".b()" if index % 2 == 0 else ".c()" for index in range(count))
    return (
        "class A { b() { return this; } c() { return this; } }\n"
        f"export function chain(a: A) {{ return {expression}; }}\n"
        if language == "typescript"
        else "pub struct A;\n"
        "impl A { pub fn b(self) -> Self { self } pub fn c(self) -> Self { self } }\n"
        f"pub fn chain(a: A) -> A {{ {expression} }}\n"
    )


@pytest.mark.parametrize("language", ["typescript", "rust"])
@pytest.mark.parametrize(
    ("shape", "count"),
    [
        ("branches", 300),
        ("branches", 1000),
        ("branches", 5000),
        ("concat", 1000),
        ("concat", 10_000),
        ("methods", 2000),
    ],
)
def test_flat_chains_keep_the_unguarded_frame(
    built: Path,
    release_core: Path,
    harness_core: Path,
    tmp_path: Path,
    language: str,
    shape: str,
    count: int,
) -> None:
    root = tmp_path / "project"
    request = project(root, 0, 0, language)
    complete_contract(root)
    path = root / ("src/chain.ts" if language == "typescript" else "src/lib.rs")
    path.write_text(chain_source(language, shape, count))
    if (language, shape, count) in OPERATOR_WORK_REFUSED:
        return assert_refused_by_operator_work(release_core, request)
    stdout, code = native_scan.exchange(str(release_core), "scan", json.dumps(request).encode())
    frame = json.loads(stdout)
    assert code == 0, frame["unsupported"]
    plain = unguarded_frame(built, harness_core, frame)
    drop_premise(frame)
    frame["self_test"].pop("collect")
    frame.pop("status")
    assert frame == plain


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_six_hundred_brackets_still_refuse_without_a_frame(
    release_core: Path, tmp_path: Path, language: str
) -> None:
    request = project(tmp_path / "project", 1, 600, language)
    done = subprocess.run(
        [str(release_core), "scan"],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 2 and done.stdout == b"", done.stderr
    assert b"parse_work_limit" in done.stderr
