# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-70 states the invariant: "the external promise declares every type it hands out." A
reviewer found it unenforced -- `test_violations.py::test_api_all_matches_the_names_reference_md_
documents` pins today's three names and one `is` check, but nothing stops a future
`load_violations` from returning an undeclared type, or a declared class from carrying an
undeclared attribute type, without the test noticing.

`public_api_diagnostics` (archkeel.check.validation) is `declarations.public_api`'s only
guard today, and it checks existence alone (AD-66/AD-71): a declared entry's module must have
been scanned, and, when the module states `__all__`, the name must be in it. It never reads a
declared function's parameters or return, or a declared class's public attributes -- exactly the
gap `boundary_types` (AD-58/AD-63) already closes for a component's *internal* facade, asked here
of the package's *external* one.

These tests build a synthetic package the way `test_analyzer.py`'s own `boundary_types` tests do
and pin the effect a generic guard must have -- an undeclared type reported -- rather than which
function or rule kind ends up computing it, so they hold regardless of whether the guard turns
out to be a new check or `boundary_types`'s own resolution machinery pointed at `public_api`.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_analyzer import _observe

from archkeel.check.validation import public_api_diagnostics
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import Diagnostic


def _prepare(tmp_path: Path, public_api: list[str], facade_source: str) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": {"public_api": public_api},
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "facade.py").write_text(facade_source)
    return tmp_path


def _public_api_diagnostics(tmp_path: Path) -> tuple[Diagnostic, ...]:
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(decode_json((tmp_path / "contract.json").read_bytes()))
    return public_api_diagnostics(contract, result.observation)


def test_public_api_reports_a_declared_function_returning_an_undeclared_type(
    tmp_path: Path,
) -> None:
    """Only `make_config` is declared; `Config`, the type it hands out, is not."""
    _prepare(
        tmp_path,
        ["sample.facade:make_config"],
        "class Config:\n    pass\n\n\ndef make_config() -> Config:\n    return Config()\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared function returning an undeclared type must be reported"
    assert any("Config" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_declared_function_taking_an_undeclared_type(tmp_path: Path) -> None:
    """The same leak on the side a consumer must supply rather than the side it receives."""
    _prepare(
        tmp_path,
        ["sample.facade:use_config"],
        "class Config:\n    pass\n\n\ndef use_config(config: Config) -> None:\n    return None\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared function taking an undeclared type must be reported"
    assert any("Config" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_declared_classs_undeclared_attribute_type(tmp_path: Path) -> None:
    """AD-70's own example: `ViolationRow.fingerprint` is why `ViolationFingerprint` is declared
    at all. `Row` is declared here; `Fingerprint`, the type its own attribute hands out, is not
    -- a consumer holding a `Row` can reach `Fingerprint` with no promise covering it."""
    _prepare(
        tmp_path,
        ["sample.facade:Row"],
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Fingerprint:\n"
        "    value: str\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Row:\n"
        "    fingerprint: Fingerprint\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared class's undeclared attribute type must be reported"
    assert any("Fingerprint" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_is_silent_for_a_builtin_and_a_declared_collection_element(
    tmp_path: Path,
) -> None:
    """Green regression guard: `archkeel.api.load_violations` takes a bare `Path` and returns
    `tuple[ViolationRow, ...]` today (AD-70's own current, correct surface). The guard must clear
    a stdlib parameter and a declared type sitting inside a generic, not just a bare declared
    name, or it would fire on the facade it exists to protect.
    """
    _prepare(
        tmp_path,
        ["sample.facade:Row", "sample.facade:load"],
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Row:\n"
        "    value: str\n\n\n"
        "def load(path: Path) -> tuple[Row, ...]:\n"
        "    return ()\n",
    )

    assert _public_api_diagnostics(tmp_path) == ()
