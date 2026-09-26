# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #165: an ordinary-module re-export needs static export and binding proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component

from archkeel.analyzer import observe


def _observe_facade(
    tmp_path: Path,
    *,
    api: str,
    init: str = "",
    implementation: str | None = None,
    public: str = "sample.app.api:constraints",
):
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=[public])],
                "rules": [
                    {
                        "id": "APP-TYPES-NOT-DICT",
                        "kind": "boundary_types",
                        "source": "sample.app",
                        "rationale": "Keep the declared application boundary typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (package / "__init__.py").write_text(init)
    (package / "api.py").write_text(api)
    (package / "impl.py").write_text(
        implementation
        or "def element_constraints(first: dict, second: dict) -> object:\n    return first\n"
    )
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


@pytest.mark.parametrize(
    "api",
    [
        (
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
            "constraints = object\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "if enabled:\n    __all__ = ['constraints']\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "def configure():\n    __all__ = ['constraints']\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
            "__all__.append('other')\n"
        ),
        (
            "if enabled:\n"
            "    from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
        ),
    ],
    ids=("rebound-export", "conditional-all", "local-all", "mutated-all", "conditional-import"),
)
def test_unproven_non_init_exports_leave_the_rule_unknown(tmp_path: Path, api: str) -> None:
    observation = _observe_facade(tmp_path, api=api)

    assert not observation.records("violations")
    assert any(
        item.kind in {"rule-without-subjects", "boundary_type_limit"}
        for item in observation.records("unknowns") or ()
    )


def test_init_facade_does_not_make_an_unproven_module_export_decidable(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api=(
            "from .impl import element_constraints as constraints\n"
            "if enabled:\n    __all__ = ['constraints']\n"
        ),
        init=('from .api import constraints\n__all__ = ["constraints"]\n'),
    )

    assert not observation.records("violations")
    assert any(
        item.kind == "rule-without-subjects" for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "api",
    [
        (
            "from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            "if enabled:\n    constraints = safe\n"
            '__all__ = ["safe", "constraints"]\n'
        ),
        (
            "if enabled:\n"
            "    from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            '__all__ = ["safe", "constraints"]\n'
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            '__all__ = ["safe", "constraints"]\n'
            "__all__.append('other')\n"
        ),
    ],
    ids=("rebound-import", "conditional-import", "mutated-all"),
)
def test_mixed_ordinary_facade_keeps_unproven_export_unknown(tmp_path: Path, api: str) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=api,
    )

    assert not observation.records("violations")
    limit = next(
        item for item in observation.records("unknowns") or () if item.kind == "boundary_type_limit"
    )
    assert limit.data.get("undecidable_positions")


def test_ordinary_facade_does_not_follow_rebound_origin_definition(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api=('from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n'),
        implementation=(
            "def element_constraints(first: dict, second: dict) -> object:\n"
            "    return first\n"
            "def actual(first: str, second: str) -> str:\n"
            "    return first\n"
            "element_constraints = actual\n"
        ),
    )

    assert not observation.records("violations")
    assert any(item.kind == "boundary_type_limit" for item in observation.records("unknowns") or ())
