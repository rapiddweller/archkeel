# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #165: ordinary literal-__all__ facades produce one violation per position."""

import json
from pathlib import Path
from unittest.mock import patch

from test_analyzer import _component

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Record, RunResult
from archkeel.ir.trace import trace_valid_violations


def _write_app(
    root: Path,
    *,
    public: list[str],
    init: str,
    api: str,
) -> None:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=public)],
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
    package = root / "sample/app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(init)
    (package / "api.py").write_text(api)
    (package / "impl.py").write_text(
        "def element_constraints(first: dict, second: dict) -> object:\n    return first\n"
    )


def _reported_violations(root: Path) -> tuple[RunResult, tuple[Record, ...]]:
    with (
        patch("archkeel.check.report.resolve_commit", return_value="a" * 40),
        patch("archkeel.check.report.git_bytes", return_value=b""),
    ):
        result, architecture = run_report(
            root,
            config=ScanConfig(("sample",), "sample", "contract.json", "d" * 64),
            analyzer=observe,
        )
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    violations = tuple(observation.records("violations") or ())
    assert trace_valid_violations(observation) == violations
    return result, violations


def _assert_one_per_position(result: RunResult, violations: tuple[Record, ...]) -> None:
    assert result.exit_code == 0, result.diagnostics
    assert {item.data.get("position") for item in violations} == {
        "first",
        "second",
        "return",
    }
    assert len(violations) == 3
    assert len({item.id for item in violations}) == len(violations)


def test_non_init_api_all_reexport_chain_reports_each_position_once(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:constraints", "sample.app:element_constraints"],
        init=(
            "from .api import constraints as element_constraints\n"
            '__all__ = ["element_constraints"]\n'
        ),
        api=('from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n'),
    )

    _assert_one_per_position(*_reported_violations(tmp_path))


def test_init_py_reexport_control_reports_each_position_once(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app:element_constraints"],
        init=('from .impl import element_constraints\n__all__ = ["element_constraints"]\n'),
        api="",
    )

    _assert_one_per_position(*_reported_violations(tmp_path))
