# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TSConfig selection and error behavior against a frozen TypeScript 5.9.3 reference."""

import hashlib
import json
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.config import Snapshot, load_config

REFERENCE = Path(__file__).resolve().parents[1] / "fixtures/typescript-config-reference.json"
_CORPUS = json.loads(REFERENCE.read_text(encoding="utf-8"))
_VALID = tuple(name for name, case in _CORPUS["cases"].items() if not case["diagnostics"])
_INVALID = tuple(name for name, case in _CORPUS["cases"].items() if case["diagnostics"])


def _digest(case: dict[str, object]) -> str:
    payload = {
        "files": case["files"],
        "roots": case["roots"],
        "tsconfig": case["tsconfig"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _materialize(root: Path, case: dict[str, object]) -> Snapshot:
    for relative, content in case["files"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return Snapshot(str(root))


def test_reference_is_pinned_and_each_case_is_bound_to_its_inputs() -> None:
    assert _CORPUS["reference"] == {
        "producer": "TypeScript Compiler API",
        "version": "5.9.3",
        "method": "parseJsonConfigFileContent",
        "diagnostics": "parsed.errors",
    }
    assert len(_CORPUS["cases"]) == 25
    assert len(_VALID) == 13
    assert len(_INVALID) == 12
    for name, case in _CORPUS["cases"].items():
        assert case["input_digest"] == _digest(case), name


@pytest.mark.parametrize("name", _VALID)
def test_valid_extended_configs_select_exact_compiler_files(tmp_path: Path, name: str) -> None:
    case = _CORPUS["cases"][name]
    snapshot = _materialize(tmp_path / name, case)
    config = load_config(snapshot, case["tsconfig"], tuple(case["roots"]))

    assert config.partial is False, snapshot.problems
    assert snapshot.problems == set()
    assert list(config.files) == case["selected"]


@pytest.mark.parametrize("name", _INVALID)
def test_compiler_config_diagnostics_make_collection_partial(tmp_path: Path, name: str) -> None:
    case = _CORPUS["cases"][name]
    assert case["diagnostics"], name
    snapshot = _materialize(tmp_path / name, case)
    config = load_config(snapshot, case["tsconfig"], tuple(case["roots"]))

    assert config.partial is True, (name, case["diagnostics"], snapshot.problems)
    assert snapshot.problems, (name, case["diagnostics"])
