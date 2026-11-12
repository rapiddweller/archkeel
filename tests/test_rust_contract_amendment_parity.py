# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-375: the Rust contract crate reads, writes and binds an amendment as `validate --against`
does.

Three parts, each against the unmodified Python code:

- Read: for each case of `rust_contract_amendment_cases`, `parse_amendment` and Rust accept or
  refuse together, Rust writes the bytes of `amendment_bytes`, and an error has the Python message
  where Rust names the same error. Rust is stricter only in the named cases (`STRICTER`).
- Gate: for pairs of contract trees and amendments, `_widening_failures` and `Binding::check`
  give the same status (unchanged, covered, unamended, stale) and the same failure messages.
- Write: `_artifact_files` and `Binding::amend` write the same bytes.

An amendment that Rust accepts and Python refuses is a silent false PASS of a CI gate, so each
such case fails the test. The messages hold the Python `repr` of values, so the tests run on
Python 3.11 only (L-28).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from rust_contract_against_cases import hand_pairs, mutated_pairs, recorded_pairs
from rust_contract_amendment_cases import OTHER, TEXT_VALUES, all_cases
from test_rust_contract_against_parity import _load, _sources

from archkeel.check.validation import (
    _AgainstContext,
    _artifact_files,
    _Introduced,
    _widening_failures,
)
from archkeel.ir.amendment import AmendmentStatus, AmendmentVersion
from archkeel.ir.amendment_codec import amendment_bytes, parse_amendment
from archkeel.ir.codec import InsideContractTree
from archkeel.ir.codec_wire import decode_json

NATIVE = Path(__file__).parents[1] / "native"
PATHS = ("architecture-contract.json", "other.json", "é/c.json", "a b/c.json")
AGAINST = ("HEAD~1", "origin/main")
POSITIONS = ("before_digest", "after_digest", "before_baseline_digest", "after_baseline_digest")
Side = tuple[InsideContractTree | None, Any]
# The code points of Python `str.isspace`, written out so that a change of either side shows.
PYTHON_SPACE = (
    *(0x9, 0xA, 0xB, 0xC, 0xD, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680),
    *range(0x2000, 0x200B),
    *(0x2028, 0x2029, 0x202F, 0x205F, 0x3000),
)


def _probe() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native amendment parity test.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    name = "contract_amendment_dump"
    command = [cargo, "build", "--locked", "--release", "-p", "archkeel-contract"]
    command += ["--example", name]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        built = subprocess.run(command, cwd=NATIVE, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return NATIVE / "target/release/examples" / (name + (".exe" if os.name == "nt" else ""))


def _rust(probe: Path, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = "".join(json.dumps(line) + "\n" for line in lines)
    run = subprocess.run([probe], input=text.encode(), capture_output=True, check=True)
    # Split on line feeds only: a message may hold U+2028, which `splitlines` also splits on.
    return [json.loads(line) for line in run.stdout.decode().split("\n") if line]


def _python_parse(data: bytes) -> dict[str, Any]:
    try:
        amendment = parse_amendment(decode_json(data))
    except ValueError as error:
        return {"kind": "invalid", "error": str(error)}
    except RecursionError:
        return {"kind": "crash"}
    try:
        written: str | None = amendment_bytes(amendment).hex()
    except UnicodeEncodeError:
        written = None
    return {
        "kind": "parsed",
        "v1": amendment.schema_version == AmendmentVersion.V1,
        "bytes": written,
    }


def _repeats(data: bytes) -> bool:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise KeyError("repeated")
        return dict(pairs)

    try:
        json.loads(data, object_pairs_hook=hook)
    except KeyError:
        return True
    return False


def _stricter(data: bytes, python: dict[str, Any], rust: dict[str, Any]) -> str | None:
    """The named case of AD-375 where Python reads an amendment that Rust refuses."""
    if python["kind"] != "parsed" or rust["kind"] != "invalid":
        return None
    if python["v1"] and rust["class"] == "version1":
        return "schema 1.0.0"
    if rust["class"] == "duplicate_key" and _repeats(data):
        return "repeated key"
    if python["bytes"] is None and rust["class"] == "json":
        return "lone surrogate"
    return None


@pytest.mark.requires_python(below=12)
def test_the_rust_amendment_reader_is_the_python_reader() -> None:
    cases = all_cases()
    rust = _rust(_probe(), [{"op": "parse", "bytes": data.hex()} for _, data in cases])
    tally: Counter[str] = Counter()
    for (name, data), actual in zip(cases, rust, strict=True):
        expected = _python_parse(data)
        stricter = _stricter(data, expected, actual)
        if stricter is not None:
            tally[f"stricter {stricter}"] += 1
            continue
        if expected["kind"] != "parsed":
            assert actual["kind"] == "invalid", (name, expected, actual)
            tally["refused"] += 1
            if actual["class"] == "field" or (
                actual["class"] == "schema" and "<" not in actual["error"]
            ):
                assert actual["error"] == expected.get("error"), name
                tally["same message"] += 1
            continue
        assert actual["kind"] == "parsed", (name, expected, actual)
        assert actual["bytes"] == expected["bytes"], name
        again = parse_amendment(decode_json(bytes.fromhex(actual["bytes"])))
        assert again == parse_amendment(decode_json(data)), name
        tally["accepted"] += 1
    print(dict(tally))
    assert tally["accepted"] >= 40, tally
    assert tally["refused"] >= 200, tally
    assert tally["same message"] >= 150, tally
    for case in ("schema 1.0.0", "repeated key", "lone surrogate"):
        assert tally[f"stricter {case}"] >= 1, tally


def _context(
    old: InsideContractTree | None, path: str, against: str, parsed: Any
) -> _AgainstContext:
    contract = old.comparison_contract if old is not None else _Introduced(path)
    digest = old.comparison_digest if old is not None else None
    return _AgainstContext(
        against, contract, None, (), None, False, parsed, None, None, None, digest, None, old
    )


def _python_gate(
    old: InsideContractTree | None,
    path: str,
    against: str,
    new: InsideContractTree,
    data: bytes | None,
) -> dict[str, Any]:
    parsed = None
    if data is not None:
        try:
            parsed = parse_amendment(decode_json(data))
        except ValueError as error:
            return {"kind": "invalid", "class": "field", "error": str(error)}
    ctx = _context(old, path, against, parsed)
    messages, coded, status = _widening_failures(
        ctx,
        new.comparison_contract,
        None,
        None,
        (),
        (),
        frozenset(),
        new.comparison_digest,
        None,
        amendment_written=False,
        inside_tree=new,
    )
    if status == AmendmentStatus.VALID:
        name = "covered"
    elif status == AmendmentStatus.STALE:
        name = "stale"
    else:
        name = "unamended" if messages else "unchanged"
    widenings = [[item.subject, item.field] for item in coded]
    return {"kind": "gate", "status": name, "failures": list(messages), "widenings": widenings}


def _python_amend(
    old: InsideContractTree | None,
    path: str,
    against: str,
    new: InsideContractTree,
    who: str,
    why: str,
) -> bytes:
    ctx = replace(
        _context(old, path, against, None),
        amendment=Path("amendment.json"),
        write_amendment=True,
        decided_by=who,
        rationale=why,
    )
    files, _, _ = _artifact_files(
        root=Path("."),
        write_baseline=False,
        baseline=None,
        violations=(),
        budgets=(),
        against=ctx,
        edits=(),
        exit_code=1,
        current_digest=new.comparison_digest,
        after_baseline_digest=None,
        refused=False,
    )
    return files["amendment.json"]


def _changed(data: bytes, key: str) -> bytes:
    value = json.loads(data)
    value[key] = OTHER if value[key] != OTHER else "e" * 64
    return json.dumps(value).encode()


def _sides() -> list[tuple[str, Side, Side]]:
    pairs = [*recorded_pairs(), *hand_pairs(), *mutated_pairs()[:300]]
    sides = [(name, _load(before), _load(after)) for name, before, after in pairs]
    return [item for item in sides if item[1][0] is not None and item[2][0] is not None]


def _line(
    op: str, old: Side | None, path: str, against: str, new: Side, **extra: Any
) -> dict[str, Any]:
    return {
        "op": op,
        "before": None if old is None else _sources(old[1]),
        "path": path,
        "against": against,
        "after": _sources(new[1]),
        **extra,
    }


def _gate_cases(
    sides: list[tuple[str, Side, Side]],
) -> list[tuple[str, Side | None, str, str, Side, bytes | None]]:
    cases: list[tuple[str, Side | None, str, str, Side, bytes | None]] = []
    path, against = PATHS[0], AGAINST[0]
    valid = [
        _python_amend(old[0], path, against, new[0], "Jordan", "Accepted.") for _, old, new in sides
    ]
    for index, (name, old, new) in enumerate(sides):
        other = (index + 1) % len(sides)
        cases.append((f"{name} none", old, path, against, new, None))
        cases.append((f"{name} valid", old, path, against, new, valid[index]))
        for key in POSITIONS:
            cases.append(
                (f"{name} stale {key}", old, path, against, new, _changed(valid[index], key))
            )
        cases.append((f"{name} another pair", old, path, against, new, valid[other]))
        cases.append((f"{name} replay", old, path, against, sides[other][2], valid[index]))
        cases.append((f"{name} reversed", new, path, against, old, valid[index]))
        cases.append(
            (f"{name} invalid", old, path, against, new, valid[index].replace(b"Jordan", b"  "))
        )
    for index, (name, _old, new) in enumerate(sides[:40]):
        for path in PATHS:
            for against in AGAINST:
                introduced = _python_amend(None, path, against, new[0], "J", "R")
                cases.append((f"{name} introduced none", None, path, against, new, None))
                cases.append((f"{name} introduced valid", None, path, against, new, introduced))
                cases.append(
                    (f"{name} introduced tree amendment", None, path, against, new, valid[index])
                )
                moved = _python_amend(
                    None, PATHS[(PATHS.index(path) + 1) % len(PATHS)], against, new[0], "J", "R"
                )
                cases.append((f"{name} introduced moved", None, path, against, new, moved))
    return cases


@pytest.mark.requires_python(below=12)
def test_the_rust_amendment_gate_is_the_python_gate() -> None:
    probe = _probe()
    cases = _gate_cases(_sides())
    lines = [
        _line("gate", old, path, against, new, amendment=None if data is None else data.hex())
        for _, old, path, against, new, data in cases
    ]
    tally: Counter[str] = Counter()
    for (name, old, path, against, new, data), actual in zip(
        cases, _rust(probe, lines), strict=True
    ):
        expected = _python_gate(None if old is None else old[0], path, against, new[0], data)
        # Python names the coded widenings only for a failing gate.
        if actual.get("status") not in ("stale", "unamended"):
            actual["widenings"] = [] if "widenings" in actual else None
            expected.setdefault("widenings", None)
        assert actual == expected, name
        tally[expected.get("status", expected["kind"])] += 1
        if old is None:
            tally["introduced"] += 1
    print(dict(tally))
    assert tally["covered"] >= 300, tally
    assert tally["stale"] >= 1500, tally
    assert tally["unamended"] >= 200, tally
    assert tally["unchanged"] >= 1, tally
    assert tally["invalid"] >= 300, tally
    assert tally["introduced"] >= 1000, tally


@pytest.mark.requires_python(below=12)
def test_the_rust_amendment_writer_is_the_python_writer() -> None:
    probe = _probe()
    sides = _sides()[:60]
    texts = [("Jordan", "Accepted."), *((text, text) for text in TEXT_VALUES)]
    blanks = [(" ", "r"), ("J", "\x1c　"), ("", "r")]
    cases = [
        (old if introduced is None else None, introduced or PATHS[0], new, who, why)
        for _, old, new in sides
        for introduced in (None, PATHS[2])
        for who, why in [*texts, *blanks]
    ]
    lines = [
        _line("amend", old, path, AGAINST[0], new, decided_by=who, rationale=why)
        for old, path, new, who, why in cases
    ]
    tally: Counter[str] = Counter()
    for (old, path, new, who, why), actual in zip(cases, _rust(probe, lines), strict=True):
        written = _python_amend(None if old is None else old[0], path, AGAINST[0], new[0], who, why)
        if (who, why) in blanks:
            # Stricter: Python writes a file that its own reader refuses.
            assert actual["kind"] == "invalid", actual
            with pytest.raises(ValueError):
                parse_amendment(decode_json(written))
            tally["stricter blank"] += 1
            continue
        assert actual == {"kind": "written", "bytes": written.hex()}
        gate = _python_gate(None if old is None else old[0], path, AGAINST[0], new[0], written)
        assert gate["status"] == "covered"
        tally["written"] += 1
    print(dict(tally))
    assert tally["written"] >= 900, tally
    assert tally["stricter blank"] >= 300, tally


@pytest.mark.requires_python(below=12)
def test_the_blank_texts_of_rust_are_the_blank_texts_of_python() -> None:
    assert len(PYTHON_SPACE) == 29
    assert PYTHON_SPACE == tuple(code for code in range(0x110000) if chr(code).isspace())
    (answer,) = _rust(_probe(), [{"op": "blank_table"}])
    assert tuple(answer["blank"]) == PYTHON_SPACE


@pytest.mark.requires_python(below=12)
def test_a_run_with_a_baseline_gets_no_rust_decision() -> None:
    """L-34a: Python binds the baseline digests of a `--baseline` run, which this crate cannot
    compute, so Rust refuses the run. Python gives a decision; Rust gives none, never a PASS."""
    probe = _probe()
    sides = _sides()[:40]
    path, against = PATHS[0], AGAINST[0]
    cases = []
    for _, old, new in sides:
        valid = _python_amend(old[0], path, against, new[0], "J", "R")
        cases += [(old, new, valid), (old, new, None), (old, old, None), (None, new, None)]
        cases.append((None, new, _python_amend(None, path, against, new[0], "J", "R")))
    lines = [
        _line(
            "gate",
            old,
            path,
            against,
            new,
            amendment=None if data is None else data.hex(),
            baseline=True,
        )
        for old, new, data in cases
    ]
    lines += [
        _line("amend", old, path, against, new, decided_by="J", rationale="R", baseline=True)
        for old, new, _ in cases
    ]
    answers = _rust(probe, lines)
    assert answers == [{"kind": "refused", "reason": "baseline"}] * len(lines)
    assert len(lines) >= 400
