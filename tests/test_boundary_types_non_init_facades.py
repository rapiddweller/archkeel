# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #165: ordinary literal-__all__ facades produce one violation per position."""

import json
from pathlib import Path
from unittest.mock import patch

from test_analyzer import _component, _observe

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
    implementation: str = """def element_constraints(first: dict, second: dict) -> object:
    return first
""",
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
    (package / "impl.py").write_text(implementation)


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
    assert architecture is not None, result.diagnostics
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


def test_init_py_union_findings_at_one_position_have_stable_ids(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app:element_constraints"],
        init=('from .impl import element_constraints\n__all__ = ["element_constraints"]\n'),
        api="",
        implementation="""def element_constraints(value: dict | object) -> str:
    return str(value)
""",
    )

    result, violations = _reported_violations(tmp_path)
    assert result.exit_code == 0, result.diagnostics
    assert violations
    assert {item.data.get("position") for item in violations} == {"value"}
    assert len({item.id for item in violations}) == len(violations)


def test_reexported_class_exposes_public_methods_but_not_self_or_cls(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:ExportSession"],
        init="",
        api=("from .impl import ExportSession\n__all__ = ['ExportSession']\n"),
        implementation=(
            "from builtins import classmethod as class_method\n"
            "class ExportSession:\n"
            "    def __init__(self, config: dict) -> None:\n"
            "        pass\n\n"
            "    @class_method\n"
            "    def prepare_page(owner, page: dict) -> None:\n"
            "        pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert {item.subjects[1] for item in violations} == {
        "sample.app.api.ExportSession.__init__",
        "sample.app.api.ExportSession.prepare_page",
    }
    assert {item.data.get("position") for item in violations} == {"config", "page"}


def test_unpublished_class_methods_are_not_boundary_subjects(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:run"],
        init="",
        api="from .impl import run\n__all__ = ['run']\n",
        implementation=(
            "class InternalSession:\n"
            "    def prepare_page(self, page: dict) -> object:\n"
            "        return page\n\n"
            "def run() -> None:\n"
            "    pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert not violations


def test_multiple_class_aliases_report_method_once(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:ExportSession", "sample.app.api:Session"],
        init="",
        api=(
            "from .impl import ExportSession\n"
            "Session = ExportSession\n"
            "__all__ = ['ExportSession', 'Session']\n"
        ),
        implementation=(
            "class ExportSession:\n    def prepare_page(self, page: dict) -> None:\n        pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert len(violations) == 1
    assert violations[0].data.get("position") == "page"


def test_alias_only_class_export_uses_alias_in_finding(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:Session"],
        init="",
        api=("from .impl import ExportSession as Session\n__all__ = ['Session']\n"),
        implementation=(
            "class ExportSession:\n    def prepare_page(self, page: dict) -> None:\n        pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects[1] == "sample.app.api.Session.prepare_page"


def test_exported_subclass_reports_inherited_surface_as_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:ExportSession"],
        init="",
        api=(
            "__all__ = ['ExportSession']\n"
            "class BaseSession:\n"
            "    def prepare_page(self, page: dict) -> None:\n"
            "        pass\n"
            "class ExportSession(BaseSession):\n"
            "    pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    unknowns = result.observation.records("unknowns") or ()
    assert any(
        item.kind == "boundary_type_position"
        and item.data.get("position") == "inherited methods"
        and item.data.get("reason") == "inherited_surface"
        for item in unknowns
    )
    result, _ = _reported_violations(tmp_path)
    assert any(item.status == "UNKNOWN" for item in result.rule_assessments or ())


def test_parameterized_generic_root_is_not_an_inherited_surface(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:Public"],
        init="",
        api=(
            "from typing import Generic, TypeVar\n"
            "T = TypeVar('T')\n"
            "__all__ = ['Public']\n"
            "class Public(Generic[T]):\n"
            "    pass\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    [public] = [
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Public"
    ]
    assert public.data.get("bases") == ("Generic[T]",)
    assert public.data.get("base_roots") == ("typing.Generic",)
    assert not any(
        item.kind == "boundary_type_position" and item.data.get("reason") == "inherited_surface"
        for item in result.observation.records("unknowns") or ()
    )


def test_parameterized_custom_base_still_reports_inherited_surface(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:Public"],
        init="",
        api=(
            "from typing import Generic, TypeVar\n"
            "T = TypeVar('T')\n"
            "__all__ = ['Public']\n"
            "class Base(Generic[T]):\n"
            "    def convert(self, value: dict) -> None:\n"
            "        pass\n"
            "class Public(Base[T]):\n"
            "    pass\n"
        ),
    )

    result, _ = _reported_violations(tmp_path)

    assert any(item.status == "UNKNOWN" for item in result.rule_assessments or ())


def test_overload_signatures_define_the_public_method_surface(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:Exporter"],
        init="",
        api=(
            "from typing import overload\n"
            "__all__ = ['Exporter']\n"
            "class Exporter:\n"
            "    @overload\n"
            "    def encode(self, value: int) -> int: ...\n"
            "    @overload\n"
            "    def encode(self, value: str) -> str: ...\n"
            "    def encode(self, value: object) -> object:\n"
            "        return value\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert not trace_valid_violations(result.observation)


def test_exported_callable_class_checks_call_protocol(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:CallableExporter"],
        init="",
        api=(
            "__all__ = ['CallableExporter']\n"
            "class CallableExporter:\n"
            "    def __call__(self, payload: dict) -> object:\n"
            "        return payload\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert {item.subjects[1] for item in violations} == {"sample.app.api.CallableExporter.__call__"}
    assert {item.data.get("position") for item in violations} == {"payload", "return"}


def test_direct_class_export_checks_static_self_parameter(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:ExportSession"],
        init="",
        api=(
            "import builtins as builtin_types\n"
            "__all__ = ['ExportSession']\n"
            "class ExportSession:\n"
            "    @builtin_types.staticmethod\n"
            "    def convert(self: dict) -> str:\n"
            "        return str(self)\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert len(violations) == 1
    assert violations[0].data.get("position") == "self"


def test_private_and_typed_methods_of_exported_class_are_not_findings(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api:ExportSession"],
        init="",
        api=(
            "__all__ = ['ExportSession']\n"
            "class ExportSession:\n"
            "    def _internal(self, value: dict) -> None:\n"
            "        pass\n"
            "    def prepare_page(self, page: str) -> str:\n"
            "        return page\n"
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert not trace_valid_violations(result.observation)
