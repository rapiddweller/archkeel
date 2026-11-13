# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Acceptance checks for exact repository module targets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from archkeel.check.observation import _declared_module_name
from archkeel.check.ports import ScanConfig
from archkeel.ir.codec import (
    contract_bytes,
    parse_contract,
)

ROOT = Path(__file__).parents[1]
_PROVENANCE = ["docs/architecture/sample.md"]
_CONFIG = ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)


def _contract() -> dict[str, Any]:
    return {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-APP",
                "label": "app",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own the sample package."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
                "inside": "contracts/inside.json",
            }
        ],
        "rules": [],
    }


def _module(path: str, responsibility: str = "Own this module.") -> dict[str, str]:
    return {"path": path, "responsibility": responsibility}


def test_module_declarations_round_trip_and_remain_optional() -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module("sample/core/api.py", "Own the public API.")]}
    parsed = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed

    omitted = parse_contract(_contract())
    assert parse_contract(json.loads(contract_bytes(omitted))) == omitted
    assert "declarations" not in json.loads(contract_bytes(omitted))


@pytest.mark.parametrize(
    "path",
    [
        "",
        "sample/core/api",
        "sample//core/api.py",
        "sample/../outside.py",
        "../sample/api.py",
        "/sample/api.py",
        "sample/core/api.txt",
        r"sample\\api.py",
    ],
)
def test_module_declaration_rejects_unsafe_or_non_python_paths(path: str) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module(path)]}
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    "suffix", [".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
)
def test_module_declaration_accepts_supported_language_source_suffixes(suffix: str) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module(f"sample/core/api{suffix}")]}

    assert parse_contract(raw).declarations.modules[0].path == f"sample/core/api{suffix}"


def test_module_declaration_paths_are_unique_and_responsibility_is_required() -> None:
    raw = _contract()
    raw["declarations"] = {
        "modules": [_module("sample/core/api.py"), _module("sample/core/api.py", "Another.")]
    }
    with pytest.raises(ValueError):
        parse_contract(raw)

    raw["declarations"] = {"modules": [{"path": "sample/core/api.py", "responsibility": " "}]}
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_exact_module_declaration_does_not_choose_an_overlapping_semantic_owner() -> None:
    raw = _contract()
    raw["components"].append(
        {
            "id": "COMP-CORE",
            "label": "core",
            "role": "component",
            "packages": ["sample.core"],
            "responsibilities": ["Own core behavior."],
            "forbidden_responsibilities": [],
            "provenance": _PROVENANCE,
        }
    )
    raw["declarations"] = {"modules": [_module("sample/core/api.py")]}
    contract = parse_contract(raw)
    assert contract.component_for("sample.core.api") is None


@pytest.mark.parametrize(
    ("path", "root"),
    [("sample.py", ("sample",)), ("src/sample.py", ("src/sample",))],
)
def test_module_file_cannot_masquerade_as_a_configured_root(
    path: str, root: tuple[str, ...]
) -> None:
    assert _declared_module_name(path, root, "sample") is None


@pytest.mark.parametrize(
    ("suffix", "encoded_suffix"),
    [
        (".ts", "_x2e_ts"),
        (".tsx", "_x2e_tsx"),
        (".mts", "_x2e_mts"),
        (".cts", "_x2e_cts"),
        (".js", "_x2e_js"),
        (".jsx", "_x2e_jsx"),
        (".mjs", "_x2e_mjs"),
        (".cjs", "_x2e_cjs"),
        (".d.ts", "_x2e_d_x2e_ts"),
    ],
)
def test_typescript_declared_module_name_maps_native_sources_under_dot_root(
    suffix: str, encoded_suffix: str
) -> None:
    path = f"src/nested/module{suffix}"

    assert _declared_module_name(path, (".",), "app", "typescript") == (
        f"app.src.nested.module{encoded_suffix}"
    )


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        ("lib/planned.dart", ("lib",), "sample.planned"),
        ("custom/nested/a-b.dart", ("custom",), "sample.nested.a_b"),
        ("lib/planned.dart", (".",), "sample.lib.planned"),
        ("lib/planned.dart", ("lib/nested",), None),
        ("lib/planned.py", ("lib",), None),
        ("lib/planned.dart", (".", "lib"), None),
    ],
)
def test_dart_target_uses_the_collectors_active_root(
    path: str, roots: tuple[str, ...], expected: str | None
) -> None:
    assert _declared_module_name(path, roots, "sample", "dart") == expected
