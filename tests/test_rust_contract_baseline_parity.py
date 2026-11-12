# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-386: compare baseline content, canonical bytes, digests and errors with Python.

Rust may refuse a named unsupported input. It must never accept a file Python refuses,
drop an entry, or change a supported validation message. No engine or verdict is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from rust_contract_baseline_cases import (
    hostile_cases,
    integer_token_cases,
    repository_cases,
    schema_cases,
    valid_cases,
)

from archkeel.ir.codec_governance import baseline_bytes, parse_validation_baseline
from archkeel.ir.codec_wire import decode_json
from archkeel.ir.measurements import NameBudgetKind

NATIVE = Path(__file__).parents[1] / "native"


def _probe() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for baseline parity.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [
        cargo,
        "build",
        "--locked",
        "--release",
        "-p",
        "archkeel-contract",
        "--example",
        "contract_baseline_dump",
    ]
    with FileLock(str(NATIVE / "target/.pytest-native-build.lock")):
        built = subprocess.run(command, cwd=NATIVE, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return (
        NATIVE
        / "target/release/examples"
        / ("contract_baseline_dump.exe" if os.name == "nt" else "contract_baseline_dump")
    )


def _rust(probe: Path, cases: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    text = "".join(json.dumps(data.hex()) + "\n" for _, data in cases)
    run = subprocess.run([probe], input=text.encode(), capture_output=True, check=True, timeout=120)
    answers = [json.loads(line) for line in run.stdout.decode().split("\n") if line]
    assert len(answers) == len(cases)
    return answers


def _python(data: bytes) -> dict[str, Any]:
    try:
        baseline = parse_validation_baseline(decode_json(data))
    except (ValueError, TypeError, RecursionError) as error:
        return {"kind": "invalid", "error": str(error)}
    value = {
        "violations": [
            {
                "fingerprint": {
                    "rules": list(item.fingerprint.rules),
                    "subjects": list(item.fingerprint.subjects),
                },
                "count": item.count,
                "roles": [{"source": source, "target": target} for source, target in item.roles],
            }
            for item in baseline.violations
        ],
        "budgets": [
            {"Names": {"kind": str(item.name), "key": item.key, "names": list(item.names)}}
            if isinstance(item.name, NameBudgetKind)
            else {"Scalar": {"name": str(item.name), "value": item.value}}
            for item in baseline.budgets
        ],
    }
    try:
        written = baseline_bytes(baseline.violations, baseline.budgets)
    except UnicodeEncodeError:
        return {"kind": "parsed", "value": value, "bytes": None}
    return {
        "kind": "parsed",
        "value": value,
        "bytes": written.hex(),
        "digest": hashlib.sha256(written).hexdigest(),
    }


def _repeats(data: bytes) -> bool:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len(pairs) != len({key for key, _ in pairs}):
            raise KeyError("duplicate")
        return dict(pairs)

    try:
        json.loads(data, object_pairs_hook=hook)
    except KeyError:
        return True
    return False


def _stricter(data: bytes, expected: dict[str, Any], actual: dict[str, Any]) -> str | None:
    if actual["kind"] != "invalid" or expected["kind"] != "parsed":
        return None
    if actual["class"] == "size" and len(data) > 16 * 1024 * 1024:
        return "size limit"
    if actual["class"] == "duplicate_key" and _repeats(data):
        return "duplicate JSON key"
    if actual["class"] == "json" and expected["bytes"] is None:
        return "lone surrogate"
    counts = [item["count"] for item in expected["value"]["violations"]]
    counts += [item["Scalar"]["value"] for item in expected["value"]["budgets"] if "Scalar" in item]
    if any(number > 2**64 - 1 for number in counts) and actual["class"] in (
        "json",
        "field",
        "integer_range",
    ):
        return "integer range"
    return None


@pytest.mark.requires_python(below=12)
@pytest.mark.parametrize("source", ["repository", "valid", "hostile", "integer_tokens", "schemas"])
def test_baseline_codec_parity(source: str) -> None:
    cases = {
        "repository": repository_cases,
        "valid": valid_cases,
        "hostile": hostile_cases,
        "integer_tokens": integer_token_cases,
        "schemas": schema_cases,
    }[source]()
    assert cases
    if source == "hostile":
        assert len(cases) >= 60
    tally: Counter[str] = Counter()
    for (name, data), actual in zip(cases, _rust(_probe(), cases), strict=True):
        expected = _python(data)
        stricter = _stricter(data, expected, actual)
        if stricter is not None:
            tally[f"stricter: {stricter}"] += 1
            continue
        assert actual["kind"] == expected["kind"], (name, expected, actual)
        if expected["kind"] == "parsed":
            assert actual == expected, name
            tally["equal accepted"] += 1
        else:
            if actual["class"] == "field" or (
                actual["class"] == "schema" and "<" not in actual["error"]
            ):
                assert actual["error"] == expected["error"], (name, expected, actual)
                tally["same message"] += 1
            tally["equal refused"] += 1
    print(source, "files", len(cases), dict(tally), "different", 0)
