# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #266: a proven local method surface has actual positions, not a placeholder."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_boundary_types_non_init_facades import _write_app

from archkeel.analyzer import observe
from archkeel.analyzer.embedded.report import analyze_snapshot
from archkeel.check.ports import ScanConfig
from archkeel.check.ratchets import unknown_positions, unknown_positions_by_rule
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation, RunResult
from archkeel.ir.trace import trace_valid_violations


def _report(
    root: Path,
    api: str,
    *,
    public: list[str] | None = None,
    implementation: str = "",
    init: str = "",
    extra_files: dict[str, str] | None = None,
) -> tuple[RunResult, Observation]:
    _write_app(
        root,
        public=public or ["sample.app.api:Child"],
        init=init,
        api=api,
        implementation=implementation,
    )
    for name, source in (extra_files or {}).items():
        (root / name).write_text(source)
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
    assert observation.coverage is not None and observation.coverage.status == "PASS"
    assert result.exit_code == 0
    return result, observation


def _assert_decided(result: RunResult, observation: Observation, *, status: str = "PASS") -> None:
    assert unknown_positions(observation) == 0
    assert unknown_positions_by_rule(observation).get("APP-TYPES-NOT-DICT", 0) == 0
    [assessment] = result.rule_assessments or ()
    assert assessment.status == status
    assert assessment.undecided == 0
    assert assessment.evaluation_proven
    assert not any(
        item.kind in {"boundary_type_position", "boundary_type_limit"}
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "child",
    [
        "class Child(Base):\n    pass\n",
        "class Child(Base):\n    def convert(self, value: str) -> str: ...\n",
    ],
    ids=["inherited", "override"],
)
def test_fully_local_inheritance_is_decided(tmp_path: Path, child: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def convert(self, value: str) -> str: ...\n" + child,
        public=["sample.app.api:Base", "sample.app.api:Child"],
    )
    _assert_decided(result, observation)
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("annotation", ["dict", "Hidden"], ids=["broad", "private"])
def test_inherited_return_violation_is_not_accepted(tmp_path: Path, annotation: str) -> None:
    result, observation = _report(
        tmp_path,
        f"class Hidden: pass\nclass Base:\n    def convert(self) -> {annotation}: ...\n"
        "class Child(Base):\n    pass\n",
    )
    _assert_decided(result, observation, status="FAIL")
    [violation] = trace_valid_violations(observation)
    assert violation.subjects[1] == "sample.app.api.Child.convert"
    assert violation.data.get("annotation") == annotation
    assert violation.data.get("position") == "return"


def test_override_and_private_helpers_do_not_leak_base_types(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n"
        "    def convert(self) -> dict: ...\n"
        "    def _helper(self) -> object: ...\n"
        "class Child(Base):\n"
        "    def convert(self) -> str: ...\n",
    )
    _assert_decided(result, observation)
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "method,position",
    [
        ("def __init__(self, payload: dict) -> None: ...", "payload"),
        ("def __call__(self) -> dict: ...", "return"),
    ],
)
def test_inherited_constructor_and_dunder_use_direct_method_policy(
    tmp_path: Path, method: str, position: str
) -> None:
    result, observation = _report(
        tmp_path, f"class Base:\n    {method}\nclass Child(Base):\n    pass\n"
    )
    _assert_decided(result, observation, status="FAIL")
    [violation] = trace_valid_violations(observation)
    assert violation.data.get("position") == position


def test_local_chain_and_alias_preserve_defining_annotation_bindings(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import Middle\nAlias = Middle\nclass Child(Alias):\n    pass\n",
        implementation=(
            "class Hidden: pass\nclass Base:\n    def get(self) -> Hidden: ...\n"
            "class Middle(Base):\n    pass\n"
        ),
    )
    _assert_decided(result, observation, status="FAIL")
    [violation] = trace_valid_violations(observation)
    assert violation.subjects[1] == "sample.app.api.Child.get"
    assert violation.data.get("resolved_types") == ("sample.app.impl:Hidden",)


@pytest.mark.parametrize(
    "source",
    [
        "class Child(Missing): pass\n",
        "from external import Base\nclass Child(Base): pass\n",
        "class Base: pass\nBase = factory()\nclass Child(Base): pass\n",
        "class Base:\n    def get(self) -> dict: ...\n    get = None\nclass Child(Base): pass\n",
        "class Base: pass\nclass Child(Base):\n    if True:\n        get = None\n",
        "class Left:\n    def get(self) -> dict: ...\nclass Right:\n"
        "    def get(self) -> str: ...\nclass Child(Left, Right): pass\n",
        "class Base(Child): pass\nclass Child(Base): pass\n",
    ],
    ids=[
        "missing",
        "external",
        "rebound-base",
        "rebound-method",
        "dynamic-child",
        "multiple",
        "cycle",
    ],
)
def test_unproven_inherited_surface_remains_unknown(tmp_path: Path, source: str) -> None:
    result, observation = _report(tmp_path, source)
    assert unknown_positions(observation) >= 1
    assert unknown_positions_by_rule(observation)["APP-TYPES-NOT-DICT"] >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert assessment.undecided >= 1
    assert any(
        item.kind == "boundary_type_position" and item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )
    assert trace_valid_violations(observation) == ()


def test_reexported_child_keeps_facade_identity_and_defining_scope(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import Child as Alias\n__all__ = ['Alias']\n",
        public=["sample.app.api:Alias"],
        implementation=(
            "class Hidden: pass\nclass Base:\n    def get(self) -> Hidden: ...\n"
            "class Child(Base): pass\n"
        ),
    )
    _assert_decided(result, observation, status="FAIL")
    [violation] = trace_valid_violations(observation)
    assert violation.subjects[1] == "sample.app.api.Alias.get"
    assert violation.data.get("resolved_types") == ("sample.app.impl:Hidden",)


def test_generic_chain_substitutes_inherited_signature(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from typing import Generic, TypeVar\nT = TypeVar('T')\nU = TypeVar('U')\n"
        "class Hidden: pass\nclass Base(Generic[T]):\n    def get(self) -> list[T]: ...\n"
        "class Middle(Base[U], Generic[U]): pass\nclass Child(Middle[Hidden]): pass\n",
    )
    _assert_decided(result, observation, status="FAIL")
    [violation] = trace_valid_violations(observation)
    assert violation.data.get("annotation") == "list[T]"
    assert violation.data.get("resolved_types") == ("sample.app.api:Hidden",)


def test_unannotated_inherited_position_is_counted_without_phantom_surface(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path, "class Base:\n    def get(self): ...\nclass Child(Base): pass\n"
    )
    assert unknown_positions(observation) == 1
    [position] = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert position.data.get("qualified_name") == "sample.app.api.Child.get"
    assert position.data.get("reason") == "missing_annotation"
    [limit] = [
        item for item in observation.records("unknowns") or () if item.kind == "boundary_type_limit"
    ]
    assert (
        limit.data.get("positions"),
        limit.data.get("decided"),
        limit.data.get("undecided"),
    ) == (1, 0, 1)
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1


@pytest.mark.parametrize(
    "source",
    [
        "def wrap(cls): return cls\n@wrap\nclass Base:\n"
        "    def get(self) -> str: ...\nclass Child(Base): pass\n",
        "class Base:\n    def get(self) -> str: ...\nBase.get = lambda self: {}\n"
        "class Child(Base): pass\n",
        "class Base:\n    def get(self) -> str: ...\nclass Child(Base):\n"
        "    __slots__ = ('get',)\n",
        "class Base:\n    def get(self) -> str: ...\n"
        "setattr(Base, 'get', lambda self: {})\nclass Child(Base): pass\n",
        "class Base:\n    def get(self) -> str: ...\n"
        "delattr(Base, 'get')\nclass Child(Base): pass\n",
        "class Base:\n    def get(self) -> str: ...\n"
        "    locals()['get'] = lambda self: {}\nclass Child(Base): pass\n",
        "def replacement(self) -> object: return {}\nclass Base:\n"
        "    def get(self) -> str: ...\nclass Child(Base):\n    get = replacement\n",
        "class Base:\n    def get(self) -> str: ...\nclass Child(Base):\n"
        "    get = lambda self: {}\n",
        "def replacement(self) -> object: return {}\nclass Base:\n"
        "    get = replacement\nclass Child(Base): pass\n",
        "class Base:\n    def __init_subclass__(cls) -> None:\n"
        "        cls.get = lambda self: {}\n    def get(self) -> str: ...\n"
        "class Child(Base): pass\n",
    ],
    ids=[
        "decorated-base",
        "attribute-rebound-method",
        "generated-slot-override",
        "setattr",
        "delattr",
        "class-namespace-write",
        "assigned-override",
        "lambda-override",
        "assigned-base-method",
        "init-subclass-hook",
    ],
)
def test_dynamic_class_transformation_retains_unknown(tmp_path: Path, source: str) -> None:
    result, observation = _report(tmp_path, source)
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


@pytest.mark.parametrize(
    "mutation",
    ["Base.get = lambda self: {}", "Alias.get = lambda self: {}", "del Alias.get"],
)
def test_alias_member_mutation_prevents_surface_proof(tmp_path: Path, mutation: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nAlias = Base\n"
        f"{mutation}\nclass Child(Alias): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


def test_imported_base_member_mutation_prevents_surface_proof(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import Base\nAlias = Base\nBase.get = lambda self: {}\n"
        "class Child(Alias): pass\n",
        implementation="class Base:\n    def get(self) -> str: ...\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


def test_inherited_violation_cites_both_facade_class_and_defining_method(tmp_path: Path) -> None:
    _, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> dict: ...\nclass Child(Base): pass\n",
    )
    [finding] = trace_valid_violations(observation)
    symbols = observation.records("symbols") or ()
    child = next(
        item for item in symbols if item.data.get("qualified_name") == "sample.app.api.Child"
    )
    method = next(
        item for item in symbols if item.data.get("qualified_name") == "sample.app.api.Base.get"
    )
    assert set(finding.fact_ids) == {child.id, method.id}
    assert set(finding.evidence_ids) == set(child.evidence_ids) | set(method.evidence_ids)


def test_inherited_unknown_cites_the_defining_method(tmp_path: Path) -> None:
    _, observation = _report(
        tmp_path, "class Base:\n    def get(self): ...\nclass Child(Base): pass\n"
    )
    [position] = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    method = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base.get"
    )
    assert method.id in position.fact_ids
    assert set(method.evidence_ids) <= set(position.evidence_ids)


@pytest.mark.parametrize(
    "alias",
    ["Annotated[Base, 'meta']", "Base | str", "list[Base]", "Alias"],
)
def test_unproven_alias_base_does_not_select_a_reachable_class(tmp_path: Path, alias: str) -> None:
    result, observation = _report(
        tmp_path,
        "from typing import Annotated\nclass Base:\n    def get(self) -> str: ...\n"
        f"Alias = {alias}\nclass Child(Alias): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


def test_mutated_imported_module_base_remains_unknown(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from . import impl\nimpl.Base.get = lambda self: {}\nclass Child(impl.Base): pass\n",
        implementation="class Base:\n    def get(self) -> str: ...\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


@pytest.mark.parametrize(
    "mutation",
    [
        "from builtins import setattr as change\nchange(Base, 'get', lambda self: {})",
        "import builtins as native\nnative.delattr(Alias, 'get')",
    ],
)
def test_reflective_mutation_invalidates_class_aliases(tmp_path: Path, mutation: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nAlias = Base\n"
        f"{mutation}\nclass Child(Alias): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


def test_reflective_mutation_invalidates_a_dotted_import_route(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "import sample.app.impl as impl\nfrom builtins import setattr as change\n"
        "change(impl.Base, 'get', lambda self: {})\nclass Child(impl.Base): pass\n",
        implementation="class Base:\n    def get(self) -> str: ...\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


@pytest.mark.parametrize(
    "member",
    ["marker: str = 'ok'", "_helper = lambda self: {}", "def _helper(self): return locals()"],
)
def test_non_method_bindings_and_private_helpers_preserve_a_safe_surface(
    tmp_path: Path, member: str
) -> None:
    result, observation = _report(
        tmp_path,
        f"class Base:\n    {member}\n    def get(self) -> str: ...\nclass Child(Base): pass\n",
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize(
    "mutation",
    [
        "globals()['Base'] = Replacement",
        "locals()['Base'] = Replacement",
        "vars()['Base'] = Replacement",
        "exec('Base.get = lambda self: {}')",
        "eval(\"setattr(Base, 'get', lambda self: {})\")",
        "from builtins import exec as run\nrun('Base.get = lambda self: {}')",
        "import builtins as native\nnative.globals()['Base'] = Replacement",
        "write = setattr\nwrite(Base, 'get', lambda self: {})",
        "ns = globals\nns()['Base'] = Replacement",
    ],
)
def test_module_namespace_exposure_prevents_inherited_closure(
    tmp_path: Path, mutation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nclass Replacement:\n"
        f"    def get(self) -> object: ...\n{mutation}\nclass Child(Base): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("argument", ["Base", "Alias", "cls=Base", "[Base]"])
def test_class_object_escape_keeps_the_method_surface_unknown(
    tmp_path: Path, argument: str
) -> None:
    result, observation = _report(
        tmp_path,
        "def mutate(cls):\n    target = cls[0] if isinstance(cls, list) else cls\n"
        "    target.get = lambda self: {}\nclass Base:\n"
        f"    def get(self) -> str: ...\nAlias = Base\nmutate({argument})\n"
        "class Child(Alias): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


def test_dotted_class_object_escape_keeps_the_import_route_unknown(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "import sample.app.impl as impl\ndef mutate(cls): cls.get = lambda self: {}\n"
        "mutate(impl.Base)\nclass Child(impl.Base): pass\n",
        implementation="class Base:\n    def get(self) -> str: ...\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    imported = next(
        item for item in observation.records("imports") or () if item.data.get("binding") == "impl"
    )
    assert imported.data.get("source_binding_unique") is True
    assert imported.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("escape", [False, True])
def test_imported_class_objects_are_decided_only_without_escape(
    tmp_path: Path, escape: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import Base\ndef mutate(cls): cls.get = lambda self: {}\n"
        + ("mutate(Base)\n" if escape else "")
        + "class Child(Base): pass\n",
        implementation="class Base:\n    def get(self) -> str: ...\n",
    )
    if escape:
        assert unknown_positions(observation) >= 1
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN"
    else:
        _assert_decided(result, observation)


def test_constructing_a_base_preserves_identity_but_not_member_stability(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "def consume(value): return None\nclass Base:\n    def get(self) -> str: ...\n"
        "consume(Base())\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "decorator,signature",
    [
        ("staticmethod", "def get(value: str) -> str: ..."),
        ("classmethod", "def get(cls, value: str) -> str: ..."),
        ("property", "def get(self) -> str: ..."),
    ],
)
def test_proven_builtin_inherited_decorators_keep_the_signature(
    tmp_path: Path, decorator: str, signature: str
) -> None:
    result, observation = _report(
        tmp_path, f"class Base:\n    @{decorator}\n    {signature}\nclass Child(Base): pass\n"
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize(
    "setup,decorators",
    [
        ("def wrap(fn): return fn\n", "    @wrap\n"),
        ("def wrap(fn): return fn\n", "    @wrap\n    @staticmethod\n"),
        ("def staticmethod(fn): return fn\n", "    @staticmethod\n"),
        ("", "    @staticmethod\n    @classmethod\n"),
        ("", "    @classmethod\n    @staticmethod\n"),
        ("", "    @property\n    @staticmethod\n"),
        ("", "    @staticmethod\n    @staticmethod\n"),
    ],
    ids=[
        "arbitrary",
        "extra-wrapper",
        "shadowed-builtin",
        "static-class",
        "class-static",
        "property-static",
        "repeated-static",
    ],
)
def test_unproven_inherited_method_decorator_retains_unknown(
    tmp_path: Path, setup: str, decorators: str
) -> None:
    result, observation = _report(
        tmp_path,
        setup
        + "class Base:\n"
        + decorators
        + "    def get(self: str) -> str: ...\nclass Child(Base): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )


def test_unproven_metaclass_keeps_inherited_mro_unknown(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "class Meta(type): pass\nclass Base(metaclass=Meta):\n"
        "    def get(self) -> str: ...\nclass Child(Base): pass\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"


@pytest.mark.parametrize(
    "variant,status,count",
    [
        ("class-a-inherited-local-declared", "PASS", 0),
        ("class-a-inherited-local-broad", "FAIL", 0),
        ("class-a-inherited-local-unknown", "UNKNOWN", 1),
    ],
)
def test_cli_and_report_agree_on_the_inherited_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], variant: str, status: str, count: int
) -> None:
    from fixtures.architecture_demo import main as demo_main

    output = tmp_path / f"{variant}.json"
    assert demo_main(["--replay", variant, "--output", str(output)]) == (
        2 if status == "FAIL" else 0
    )
    validation, report = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert validation["exit_code"] == (2 if status == "FAIL" else 0)
    assert report["exit_code"] == 0
    [assessment] = [row for row in report["rule_assessments"] if row["id"] == "APP-TYPES-NOT-DICT"]
    assert assessment["status"] == status and assessment["undecided"] == count
    assert report["measurements"]["scalars"]["unknown_positions"] == count
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert unknown_positions(observation) == count
    html = output.with_suffix(".report.html").read_text()
    if status == "FAIL":
        [finding] = trace_valid_violations(observation)
        assert finding.subjects[1] == "shop.app.service.Child.convert"
        assert finding.title in html
        method = next(
            row
            for row in observation.records("symbols") or ()
            if row.data.get("qualified_name") == "shop.app.base.impl.Base.convert"
        )
        assert method.id in finding.fact_ids
        assert "def convert(self, value: str)" in html
    elif status == "UNKNOWN":
        assert "Child.__inherited_methods__ inherited methods: inherited_surface" in html


def test_unproven_child_override_does_not_clear_inherited_surface(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "def wrap(fn): return fn\nclass Base:\n    def get(self) -> str: ...\n"
        "class Child(Base):\n    @wrap\n    def get(self) -> str: ...\n",
    )
    assert unknown_positions(observation) >= 1
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("descriptor", ["staticmethod", "classmethod"])
def test_proven_aliased_descriptor_preserves_the_first_real_input(
    tmp_path: Path, descriptor: str
) -> None:
    parameters = "payload: dict" if descriptor == "staticmethod" else "cls, payload: dict"
    result, observation = _report(
        tmp_path,
        f"from builtins import {descriptor} as descriptor\nclass Base:\n"
        f"    @descriptor\n    def get({parameters}) -> str: ...\nclass Child(Base): pass\n",
    )
    _assert_decided(result, observation, status="FAIL")
    [finding] = trace_valid_violations(observation)
    assert finding.data.get("position") == "payload"


def test_shadowed_descriptor_is_not_a_proven_static_method(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from builtins import staticmethod as descriptor\ndef descriptor(fn): return fn\n"
        "class Base:\n    @descriptor\n    def get(payload: dict) -> str: ...\n"
        "class Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    method = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base.get"
    )
    assert method.data.get("method_kind") == "instance"


@pytest.mark.parametrize("source", ["Child", "Alias"])
def test_escaped_reexport_retains_origin_identity_and_surface_unknown(
    tmp_path: Path, source: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import Child as Alias\n__all__ = ['Alias']\n"
        "def mutate(cls): cls.get = lambda self: {}\n"
        + ("Child = Alias\n" if source == "Child" else "")
        + f"mutate({source})\n",
        public=["sample.app.api:Alias"],
        implementation="class Base:\n    def get(self) -> str: ...\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    imported = next(
        item for item in observation.records("imports") or () if item.data.get("binding") == "Alias"
    )
    assert imported.data.get("source_binding_unique") is True
    assert imported.data.get("source_member_binding_static") is False
    origin = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.Child"
    )
    assert origin.data.get("source_binding_unique") is True
    assert origin.data.get("source_member_binding_static") is False
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )
    assert not any(
        item.data.get("reason") == "unresolved_reexport_route"
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "name,definition", [("Marker", "class Marker: pass"), ("TOKEN", "TOKEN = 1")]
)
def test_ordinary_type_and_constant_arguments_preserve_reexport_identity(
    tmp_path: Path, name: str, definition: str
) -> None:
    result, observation = _report(
        tmp_path,
        f"from .impl import {name}, consume\n__all__ = ['{name}']\n"
        f"consume({name})\n"
        "class Base:\n    def get(self) -> str: ...\nclass Child(Base): pass\n",
        public=[f"sample.app.api:{name}", "sample.app.api:Child"],
        implementation=definition + "\ndef consume(value): return None\n",
    )
    _assert_decided(result, observation)
    imported = next(
        item for item in observation.records("imports") or () if item.data.get("binding") == name
    )
    assert imported.data.get("source_binding_unique") is True
    assert imported.data.get("reexport") is True


@pytest.mark.parametrize("entry", ["base", "facade"])
def test_intermediate_reexport_escape_cannot_disappear_at_the_origin(
    tmp_path: Path, entry: str
) -> None:
    result, observation = _report(
        tmp_path,
        (
            "from .impl import Alias\nclass Child(Alias): pass\n"
            if entry == "base"
            else "from .impl import Alias as Child\n__all__ = ['Child']\n"
        ),
        implementation=(
            "from . import " + ("Base" if entry == "base" else "Child") + " as Alias\n"
            "__all__ = ['Alias']\ndef mutate(cls): cls.get = lambda self: {}\nmutate(Alias)\n"
        ),
        init="class Base:\n    def get(self) -> str: ...\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )
    assert not any(
        item.data.get("reason") == "unresolved_reexport_route"
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "source",
    [
        "class Replacer:\n    def __set_name__(self, owner, name):\n"
        "        owner.get = lambda self: {}\nclass Base:\n"
        "    _private = Replacer()\n    def get(self) -> str: return ''\nclass Child(Base): pass\n",
        "import sys\ndef alter(fn):\n"
        "    sys._getframe(1).f_locals['get'] = lambda self: 'safe'\n    return fn\n"
        "class Base:\n    def get(self) -> dict: return {}\n"
        "    @alter\n    def marker(self) -> str: return ''\nclass Child(Base): pass\n",
    ],
    ids=["private-descriptor-hook", "decorator-neighbor-mutation"],
)
def test_unproven_class_creation_cannot_certify_neighboring_inherited_methods(
    tmp_path: Path, source: str
) -> None:
    result, observation = _report(tmp_path, source)
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "call",
    [
        "Base.configure()",
        "configure = Base.configure\nconfigure()",
        "configured = [Base.configure]\nconfigured[0]()",
        "def choose(): return Base.configure\nchoose()()",
    ],
    ids=["receiver", "bound-value", "contained-value", "returned-value"],
)
def test_called_and_escaped_bound_class_methods_prevent_inherited_closure(
    tmp_path: Path, call: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    @classmethod\n"
        "    def configure(cls) -> None: cls.get = lambda self: {}\n"
        "    def get(self) -> str: return ''\n" + call + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "member,call",
    [
        ("def configure(self) -> None: self.__class__.get = lambda self: {}", "Base().configure()"),
        ("def __init__(self) -> None: type(self).get = lambda self: {}", "Base()"),
    ],
)
def test_constructor_and_instance_receiver_effects_keep_members_unproven(
    tmp_path: Path, member: str, call: str
) -> None:
    result, observation = _report(
        tmp_path,
        f"class Base:\n    {member}\n    def get(self) -> str: return ''\n"
        f"{call}\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "imported",
    [
        "from .api import Base\nBase.configure()",
        "import sample.app.api as api\napi.Base.configure()",
        "from .api import Base\nlocals()['Base'].get = lambda self: {}",
        "from .api import Base\nvars()['Base'].get = lambda self: {}",
        "from .api import Base\nns = locals\nns()['Base'].get = lambda self: {}",
    ],
)
def test_an_escaped_imported_origin_cannot_be_certified_in_its_defining_module(
    tmp_path: Path, imported: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    @classmethod\n"
        "    def configure(cls) -> None: cls.get = lambda self: {}\n"
        "    def get(self) -> str: return ''\nfrom . import impl\nclass Child(Base): pass\n",
        implementation=imported + "\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "store",
    [
        "def choose(): return Base\nchoose().configure()",
        "registry = [Base]\nregistry[0].configure()",
        "registry = {'base': Base}\nregistry['base'].configure()",
        "class Registry: pass\nRegistry.base = Base\nRegistry.base.configure()",
        "def mutate(cls=Base): cls.get = lambda self: {}\nmutate()",
        "(Alias := Base)\nAlias.configure()",
        "registry = []\nregistry += [Base]\nregistry[0].configure()",
        "for cls in [Base]: cls.configure()",
        "mutate = lambda cls=Base: setattr(cls, 'get', lambda self: {})\nmutate()",
        "[cls.configure() for cls in [Base]]",
        "class Holder:\n    base = Base\n    def __enter__(self): return self.base\n"
        "    def __exit__(self, *args): pass\nwith Holder() as cls: cls.configure()",
        "def choose(): yield from [Base]\nnext(choose()).configure()",
        "def mutate(*, cls=Base): cls.get = lambda self: {}\nmutate()",
        "match Base:\n    case cls: cls.get = lambda self: {}",
    ],
)
def test_stored_and_returned_class_values_are_member_escapes(tmp_path: Path, store: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    @classmethod\n"
        "    def configure(cls) -> None: cls.get = lambda self: {}\n"
        "    def get(self) -> str: return ''\n" + store + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


@pytest.mark.parametrize("mutation", ["", "    Base.get = lambda self: {}\n"])
def test_conditional_import_identity_is_separate_from_an_incoming_member_escape(
    tmp_path: Path, mutation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nclass Child(Base): pass\n",
        implementation="from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
        "    from .api import Base\n" + mutation,
    )
    if mutation:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN"
        assert unknown_positions(observation) >= 1
    else:
        _assert_decided(result, observation)


def test_an_escaped_ambiguous_reexport_keeps_each_candidate_origin_unproven(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nclass Other:\n"
        "    def get(self) -> str: ...\nclass Child(Base): pass\n",
        init="def choose() -> bool: return True\nif choose():\n"
        "    from .api import Base as Alias\nelse:\n    from .api import Other as Alias\n"
        "__all__ = ['Alias']\n",
        implementation="from sample.app import Alias\nAlias.get = lambda self: {}\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


@pytest.mark.parametrize(
    "extra",
    [
        "def helper(value: Base, marker=1) -> Base: ...",
        "def helper(value: list[Base] | None) -> Base: ...",
        "from typing import TypeAlias\nAlias: TypeAlias = Base",
        "for marker in [0]: pass",
        "match 0:\n    case marker: pass",
    ],
)
def test_annotations_and_constant_value_bindings_do_not_escape_the_class(
    tmp_path: Path, extra: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\n" + extra + "\nclass Child(Base): pass\n",
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize(
    "use",
    [
        "registry = Modifier()\nregistry[Base]",
        "Modifier()[Base]",
        "Base == Modifier()",
        "Base + Modifier()",
        "Base in Modifier()",
        "@Base._configure\ndef helper(): pass",
    ],
    ids=["stored-subscription", "subscription", "comparison", "addition", "contains", "decorator"],
)
def test_implicit_class_value_calls_prevent_inherited_closure(tmp_path: Path, use: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: return ''\n    @classmethod\n"
        "    def _configure(cls, fn):\n        cls.get = lambda self: {}\n        return fn\n"
        "class Modifier:\n    def __getitem__(self, cls): cls.get = lambda self: {}\n"
        "    def __eq__(self, cls): cls.get = lambda self: {}; return True\n"
        "    def __radd__(self, cls): cls.get = lambda self: {}; return self\n"
        "    def __contains__(self, cls): cls.get = lambda self: {}; return True\n"
        + use
        + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "creation",
    [
        "class Meta(type):\n    def __new__(mcls, name, bases, namespace):\n"
        "        bases[0].get = lambda self: {}\n"
        "        return super().__new__(mcls, name, bases, namespace)\n"
        "class Mutator(Base, metaclass=Meta): pass\n",
        "def decorate(cls):\n    cls.__bases__[0].get = lambda self: {}\n"
        "    return cls\n@decorate\nclass Mutator(Base): pass\n",
        "class Descriptor:\n    def __set_name__(self, owner, name):\n"
        "        owner.__bases__[0].get = lambda self: {}\n"
        "class Mutator(Base):\n    _private = Descriptor()\n",
        "class Hook:\n    def __init_subclass__(cls):\n"
        "        cls.__bases__[0].get = lambda self: {}\n"
        "class Mutator(Base, Hook): pass\n",
        "from typing import Generic\nclass Hook:\n    def __init_subclass__(cls):\n"
        "        cls.__bases__[0].get = lambda self: {}\n"
        "Generic = Hook\nclass Mutator(Base, Generic): pass\n",
        "from typing import Generic\nclass Hook:\n    def __init_subclass__(cls):\n"
        "        cls.__bases__[0].get = lambda self: {}\n"
        "def create(Generic=Hook):\n    class Mutator(Base, Generic): pass\ncreate()\n",
        "from typing import Generic\nclass Hook:\n    def __init_subclass__(cls):\n"
        "        cls.__bases__[0].get = lambda self: {}\n"
        "class Holder:\n    Generic = Hook\n    class Mutator(Base, Generic): pass\n",
    ],
    ids=[
        "metaclass",
        "class-decorator",
        "private-descriptor",
        "multiple-base-hook",
        "rebound-framework-base",
        "function-shadowed-framework-base",
        "class-shadowed-framework-base",
    ],
)
def test_unproven_sibling_class_creation_does_not_certify_its_shared_base(
    tmp_path: Path, creation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: return ''\n"
        + creation
        + "class Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()
    [position] = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert position.data.get("reason") == "inherited_surface"
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "owner,use",
    [
        ("def helper(value: Base): pass\n", "mutate(helper)\n"),
        ("class Holder:\n    value: Base\n", "mutate(Holder)\n"),
        ("def helper(value: Base): pass\n", "Alias = helper\nmutate(Alias)\n"),
        ("@mutate\ndef helper(value: Base): pass\n", ""),
        ("@mutate\nclass Holder:\n    value: Base\n", ""),
        (
            "class Descriptor:\n    def __set_name__(self, owner, name):\n"
            "        owner.__annotations__['value'].get = lambda self: {}\n"
            "class Holder:\n    value: Base\n    marker = Descriptor()\n",
            "",
        ),
        ("value: Base\n", "__annotations__['value'].get = lambda self: {}\n"),
        (
            "class Sibling(Base): pass\ndef mutate_bases(owner):\n"
            "    owner.__bases__[0].get = lambda self: {}\n",
            "mutate_bases(Sibling)\n",
        ),
        (
            "class Sibling(Base):\n    def __init__(self) -> None:\n"
            "        type(self).__bases__[0].get = lambda self: {}\n",
            "Sibling()\n",
        ),
    ],
    ids=[
        "function",
        "class",
        "alias",
        "function-decorator",
        "class-decorator",
        "descriptor",
        "module",
        "base-container",
        "constructed-base-container",
    ],
)
def test_annotation_metadata_owner_escape_prevents_member_closure(
    tmp_path: Path, owner: str, use: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import mutate\nclass Base:\n    def get(self) -> str: return ''\n"
        + owner
        + use
        + "class Child(Base): pass\n",
        implementation=(
            "def mutate(owner):\n    owner.__annotations__['value'].get = lambda self: {}\n"
            "    return owner\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("owner", ["helper", "Holder"])
def test_imported_annotation_owner_escape_reaches_its_local_class(
    tmp_path: Path, owner: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: return ''\n"
        "def helper(value: Base): pass\nclass Holder:\n    value: Base\n"
        "class Child(Base): pass\n",
        implementation=(
            f"from .api import {owner} as Alias\n"
            "def mutate(value): value.__annotations__['value'].get = lambda self: {}\n"
            "mutate(Alias)\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("owner", ["helper", "Holder"])
@pytest.mark.parametrize("dotted", [False, True], ids=["symbol-import", "module-import"])
def test_imported_annotation_owner_escape_reaches_an_imported_class(
    tmp_path: Path, owner: str, dotted: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from .base import Base\ndef helper(value: Base): pass\nclass Holder:\n    value: Base\n",
        public=["sample.app.base:Child"],
        implementation=(
            (
                f"import sample.app.api as api\nAlias = api.{owner}\n"
                if dotted
                else f"from .api import {owner} as Alias\n"
            )
            + "def mutate(value): value.__annotations__['value'].get = lambda self: {}\n"
            "mutate(Alias)\n"
        ),
        extra_files={
            "sample/app/base.py": "class Base:\n    def get(self) -> str: return ''\n"
            "class Child(Base): pass\n"
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.base.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "owner,use",
    [
        ("def helper() -> None: pass\n", "mutate(helper)\n"),
        ("def helper() -> None: pass\n", "Alias = helper\nmutate(Alias)\n"),
        ("helper = lambda: None\n", "mutate(helper)\n"),
        (
            "class Holder:\n    def helper(self) -> None: pass\n",
            "mutate_method(Holder)\n",
        ),
    ],
    ids=["function", "function-alias", "lambda", "class-method"],
)
def test_exposed_native_owner_carries_its_defining_namespace(
    tmp_path: Path, owner: str, use: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import mutate, mutate_method\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        + owner
        + use
        + "class Child(Base): pass\n",
        implementation=(
            "def mutate(owner):\n    getattr(owner, '__globals__')['Base'].get = lambda self: {}\n"
            "def mutate_method(owner):\n"
            "    owner.helper.__globals__['Base'].get = lambda self: {}\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("owner", ["helper", "Holder"])
def test_incoming_native_owner_namespace_reaches_imported_class(tmp_path: Path, owner: str) -> None:
    result, observation = _report(
        tmp_path,
        "from .base import Base\ndef helper() -> None: pass\n"
        "class Holder:\n    def helper(self) -> None: pass\n",
        public=["sample.app.base:Child"],
        implementation=(
            f"from .api import {owner} as Alias\n"
            "def mutate(value):\n"
            + (
                "    value.__globals__['Base'].get = lambda self: {}\n"
                if owner == "helper"
                else "    value.helper.__globals__['Base'].get = lambda self: {}\n"
            )
            + "mutate(Alias)\n"
        ),
        extra_files={
            "sample/app/base.py": "class Base:\n    def get(self) -> str: return ''\n"
            "class Child(Base): pass\n"
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.base.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("dotted", [False, True], ids=["symbol-import", "module-import"])
def test_unproven_imported_creation_hook_exposes_consumer_metadata(
    tmp_path: Path, dotted: bool
) -> None:
    imported, hook = (
        ("from . import impl", "impl.Hook") if dotted else ("from .impl import Hook", "Hook")
    )
    result, observation = _report(
        tmp_path,
        imported + "\nclass Base:\n    def get(self) -> str: return ''\n"
        f"class Holder({hook}):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "class Hook:\n    def __init_subclass__(cls):\n"
            "        cls.__annotations__['value'].get = lambda self: {}\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "imported,hook",
    [
        ("from external_hook import Hook", "Hook"),
        ("from external_hook import Hook\nAlias = Hook", "Alias"),
        ("import external_hook", "external_hook.Hook"),
        ("import external_hook\nAlias = external_hook.Hook", "Alias"),
    ],
    ids=["symbol", "symbol-alias", "module", "module-alias"],
)
def test_unscanned_creation_provider_does_not_certify_contained_local_types(
    tmp_path: Path, imported: str, hook: str
) -> None:
    result, observation = _report(
        tmp_path,
        imported + "\nclass Base:\n    def get(self) -> str: return ''\n"
        f"class Holder({hook}):\n    value: Base\nclass Child(Base): pass\n",
        extra_files={
            "external_hook.py": "class Hook:\n    def __init_subclass__(cls):\n"
            "        cls.__annotations__['value'].get = lambda self: {}\n"
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "imported,base,decided",
    [
        ("from typing import Protocol", "Protocol", True),
        ("from typing import Protocol as Alias", "Alias", True),
        ("from typing import Protocol\nAlias = Protocol", "Alias", False),
        ("import typing", "typing.Protocol", False),
    ],
    ids=["symbol", "import-alias", "assignment-alias", "module"],
)
def test_exact_native_framework_base_retains_existing_proof(
    tmp_path: Path, imported: str, base: str, decided: bool
) -> None:
    result, observation = _report(
        tmp_path,
        imported + f"\nclass Base({base}):\n    def get(self) -> str: ...\n"
        "class Child(Base): pass\n",
    )
    if decided:
        _assert_decided(result, observation)
    else:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1


@pytest.mark.parametrize(
    "imported,mutation",
    [
        ("from abc import ABC", "ABC.__init_subclass__ = classmethod(hook)"),
        ("from abc import ABC as Native", "Native.__init_subclass__ = classmethod(hook)"),
        ("from abc import ABC\nAlias = ABC", "Alias.__init_subclass__ = classmethod(hook)"),
        ("import abc as native", "native.ABC.__init_subclass__ = classmethod(hook)"),
        ("from abc import *", "ABC.__init_subclass__ = classmethod(hook)"),
        ("from abc import ABCMeta", "ABCMeta.__init__ = lambda cls, *a, **kw: hook(cls)"),
        (
            "from abc import ABCMeta",
            "def mutate(owner): owner.__init__ = lambda cls, *a, **kw: hook(cls)\nmutate(ABCMeta)",
        ),
        (
            "from abc import ABCMeta as Native",
            "def mutate(owner): owner.__init__ = lambda cls, *a, **kw: hook(cls)\nmutate(Native)",
        ),
        (
            "from abc import ABCMeta\nAlias = ABCMeta",
            "def mutate(owner): owner.__init__ = lambda cls, *a, **kw: hook(cls)\n"
            "mutate(owner=Alias)",
        ),
        (
            "from abc import ABCMeta",
            "class Registry:\n    def __getitem__(self, owner):\n"
            "        owner.__init__ = lambda cls, *a, **kw: hook(cls)\n"
            "        return lambda: None\nregistry = Registry()\nregistry[ABCMeta]()",
        ),
        (
            "from abc import ABCMeta",
            "def wrap(owner):\n"
            "    owner.helper.__globals__['ABCMeta'].__init__ = lambda cls, *a, **kw: hook(cls)\n"
            "    return owner\n@wrap\nclass Owner:\n    def helper(self): pass",
        ),
    ],
    ids=[
        "symbol",
        "import-alias",
        "assignment-alias",
        "module",
        "star",
        "metaclass",
        "passed-metaclass",
        "passed-import-alias",
        "passed-assignment-alias",
        "callable-subscript-owner",
        "implicit-wrapper-owner",
    ],
)
def test_shared_native_origin_mutation_invalidates_other_importers(
    tmp_path: Path, imported: str, mutation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC as Native\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(Native):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            imported
            + "\ndef hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            + mutation
            + "\nmutated = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "implementation",
    [
        "from abc import ABC as Native\nclass Inert(Native): pass\nmutated = True\n",
        "from abc import ABCMeta\nmutated = True\n",
    ],
    ids=["inert-base", "inert-metaclass"],
)
def test_shared_native_origin_without_member_escape_retains_existing_proof(
    tmp_path: Path, implementation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=implementation,
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize("decorator", ["dataclass", "dataclass(frozen=True, slots=True)"])
def test_native_dataclass_does_not_expose_an_unrelated_creation_provider(
    tmp_path: Path, decorator: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\nfrom dataclasses import dataclass\n"
            f"@{decorator}\nclass Owner:\n    def helper(self): pass\nmutated = True\n"
        ),
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize(
    "creation",
    [
        "@dataclass(frozen=choose())\nclass Owner:\n    def helper(self): pass\n",
        "@dataclass\nclass Owner(Hook):\n    def helper(self): pass\n",
        "@dataclass\nclass Owner(metaclass=Meta):\n    def helper(self): pass\n",
        "@dataclass\nclass Owner:\n    marker = Descriptor()\n    def helper(self): pass\n",
        "@dataclass\nclass Owner:\n    def helper(self, value=choose()): pass\n",
    ],
    ids=["option-call", "custom-base", "metaclass", "descriptor", "method-default-call"],
)
def test_native_dataclass_with_unproven_creation_keeps_provider_uncertainty(
    tmp_path: Path, creation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\nfrom dataclasses import dataclass\n"
            "def choose(): return False\nclass Hook: pass\nclass Meta(type): pass\n"
            "class Descriptor:\n    def __set_name__(self, owner, name): pass\n"
            + creation
            + "mutated = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize("incoming", [False, True], ids=["visible", "incoming"])
def test_mutated_native_dataclass_does_not_certify_its_owners(
    tmp_path: Path, incoming: bool
) -> None:
    mutation = (
        "from dataclasses import dataclass\n"
        "def replace(cls=None, **kwargs): return cls\n"
        "def mutate(owner): owner.__code__ = replace.__code__\nmutate(dataclass)\n"
    )
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\nfrom dataclasses import dataclass as native\n"
            + ("from . import mutator\n" if incoming else mutation)
            + "@native(frozen=True, slots=True)\nclass Owner:\n"
            "    def helper(self): pass\nmutated = True\n"
        ),
        extra_files={"sample/app/mutator.py": mutation} if incoming else None,
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


def test_native_dataclass_generated_surface_still_needs_proof(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from dataclasses import dataclass\n@dataclass(frozen=True, slots=True)\n"
        "class Base:\n    def get(self) -> str: return ''\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions(observation) == 1


def test_imported_native_dataclass_carrier_exposes_its_provider_namespace(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\nfrom dataclasses import dataclass\n"
            "@dataclass(frozen=True, slots=True)\nclass Owner:\n    def helper(self): pass\n"
            "from .mutator import mutated\n"
        ),
        extra_files={
            "sample/app/mutator.py": (
                "from .impl import Owner\n"
                "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
                "def mutate(owner):\n"
                "    owner.helper.__globals__['ABCMeta'].__init__ = "
                "lambda cls, *a, **kw: hook(cls)\n"
                "mutate(Owner)\nmutated = True\n"
            )
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize(
    "imported, base",
    [
        ("from external_hook import Hook", "Hook"),
        ("from external_hook import Hook\nAlias = Hook", "Alias"),
        ("import external_hook", "external_hook.Hook"),
        ("import external_hook\nAlias = external_hook.Hook", "Alias"),
    ],
    ids=["symbol", "symbol-alias", "module", "module-alias"],
)
def test_unscanned_creation_hook_exposes_a_native_provider_namespace(
    tmp_path: Path, imported: str, base: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import mutated\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\n" + imported + "\n"
            f"class Owner({base}):\n    def helper(self): pass\nmutated = True\n"
        ),
        extra_files={
            "external_hook.py": (
                "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
                "class Hook:\n    def __init_subclass__(cls):\n"
                "        cls.helper.__globals__['ABCMeta'].__init__ = "
                "lambda cls, *a, **kw: hook(cls)\n"
            )
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize(
    "owner",
    [
        "def helper(value: Base) -> None: pass\n",
        "class Holder:\n    value: Base\n",
        "class Holder:\n    @staticmethod\n    def helper(value: Base) -> None: pass\n",
        "value: Base\n",
        "class Sibling(Base): pass\n",
    ],
    ids=["function", "class", "static-method", "module", "base-container"],
)
def test_unexposed_native_annotation_metadata_preserves_member_proof(
    tmp_path: Path, owner: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: return ''\n" + owner + "class Child(Base): pass\n",
    )
    _assert_decided(result, observation)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize("escaped", [False, True], ids=["inert", "escaped"])
def test_native_alias_value_requires_unexposed_metadata(tmp_path: Path, escaped: bool) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import mutate\nclass Base:\n    def get(self) -> str: return ''\n"
        "type Alias = Base\n"
        + ("mutate(Alias)\n" if escaped else "")
        + "class Child(Base): pass\n",
        implementation="def mutate(owner): owner.__value__.get = lambda self: {}\n",
    )
    if escaped:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1
        assert unknown_positions(observation) == 1
    else:
        _assert_decided(result, observation)


@pytest.mark.parametrize("dotted", [False, True])
def test_implicit_calls_preserve_import_identity_and_invalidate_its_surface(
    tmp_path: Path, dotted: bool
) -> None:
    imported, target = (
        ("import sample.app.impl as impl", "impl.Base")
        if dotted
        else ("from .impl import Base as Alias", "Alias")
    )
    result, observation = _report(
        tmp_path,
        imported
        + "\nclass Modifier:\n    def __getitem__(self, cls): cls.get = lambda self: {}\n"
        + f"Modifier()[{target}]\nclass Child({target}): pass\n",
        implementation="class Base:\n    def get(self) -> str: return ''\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    imported_record = next(
        item
        for item in observation.records("imports") or ()
        if item.data.get("binding") == ("impl" if dotted else "Alias")
    )
    assert imported_record.data.get("source_binding_unique") is True
    assert imported_record.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "use", ["def helper(value: mutate(Base)): pass", "class Other(mutate(Base)): pass"]
)
def test_calls_inside_type_contexts_still_escape_the_class(tmp_path: Path, use: str) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\ndef mutate(cls):\n"
        "    cls.get = lambda self: {}\n    return cls\n" + use + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


@pytest.mark.parametrize(
    "use", ["def helper(value: registry[Base]): pass", "class Other(registry[Base]): pass"]
)
def test_unproven_subscription_in_type_contexts_is_an_executable_escape(
    tmp_path: Path, use: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nclass Modifier:\n"
        "    def __getitem__(self, cls):\n        cls.get = lambda self: {}\n        return cls\n"
        "registry = Modifier()\n" + use + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


@pytest.mark.parametrize(
    "setup,use",
    [
        ("", "def helper(value: list[registry[Base]]): pass"),
        ("list = registry\n", "def helper(value: list[Base]): pass"),
        ("", "def helper(value: Base | registry): pass"),
    ],
    ids=["nested-subscription", "shadowed-native-header", "operator-annotation"],
)
def test_type_context_exemptions_do_not_hide_nested_or_shadowed_effects(
    tmp_path: Path, setup: str, use: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\nclass Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return cls\n"
        "    def __ror__(self, cls): cls.get = lambda self: {}; return cls\n"
        "registry = Modifier()\n" + setup + use + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


def test_deferred_unproven_annotation_does_not_prove_member_stability(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from __future__ import annotations\nclass Base:\n    def get(self) -> str: ...\n"
        "class Modifier:\n    def __getitem__(self, cls): cls.get = lambda self: {}; return cls\n"
        "registry = Modifier()\ndef helper(value: registry[Base]): pass\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


def test_custom_generic_hook_does_not_certify_inherited_methods(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from __future__ import annotations\nfrom typing import Generic, TypeVar\n"
        "T = TypeVar('T')\nclass Base(Generic[T]):\n    def get(self) -> dict: ...\n"
        "    @classmethod\n    def __class_getitem__(cls, key: type[str]) -> type[Base]:\n"
        "        cls.get = lambda self: ''\n        return cls\nclass Child(Base[str]): pass\n",
        public=["sample.app.api:Base", "sample.app.api:Child"],
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status != "PASS"
    assert unknown_positions(observation) >= 1
    assert any(
        item.data.get("reason") == "inherited_surface"
        for item in observation.records("unknowns") or ()
    )
    assert not any(
        "sample.app.api.Child.get" in item.subjects for item in trace_valid_violations(observation)
    )


@pytest.mark.parametrize(
    "use",
    [
        "class Holder:\n    Optional = registry\n    def helper(value: Optional[Base]): pass",
        "def outer(Optional=registry):\n    def helper(value: Optional[Base]): pass\nouter()",
    ],
    ids=["class-scope", "function-scope"],
)
def test_scoped_shadow_of_an_imported_native_header_is_not_proven(tmp_path: Path, use: str) -> None:
    result, observation = _report(
        tmp_path,
        "from typing import Optional\nclass Base:\n    def get(self) -> str: ...\n"
        "class Modifier:\n    def __getitem__(self, cls): cls.get = lambda self: {}; return cls\n"
        "registry = Modifier()\n" + use + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1


@pytest.mark.parametrize(
    "annotation", ["registry[Base]", "'registry[Base]'", "list['registry[Base]']"]
)
def test_evaluated_deferred_annotations_do_not_certify_inherited_methods(
    tmp_path: Path, annotation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from __future__ import annotations\nfrom typing import get_type_hints\n"
        "class Base:\n    def get(self) -> str: return ''\nclass Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return str\n"
        "registry = Modifier()\n" + f"def helper(value: {annotation}) -> None: pass\n"
        "get_type_hints(helper)\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "imported,call",
    [
        ("from typing import get_type_hints", "get_type_hints(helper)"),
        ("from typing import get_type_hints as hints", "hints(helper)"),
        ("import typing as hints", "hints.get_type_hints(helper)"),
        ("from typing import get_type_hints\nhints = get_type_hints", "hints(helper)"),
    ],
    ids=["direct", "import-alias", "dotted", "assignment-alias"],
)
def test_annotation_namespace_evaluation_prevents_member_surface_closure(
    tmp_path: Path, imported: str, call: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from typing import ForwardRef\n" + imported + "\nclass Base:\n"
        "    def get(self) -> str: return ''\nclass Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return str\n"
        "registry = Modifier()\nannotation = ForwardRef('registry[Base]')\n"
        "def helper(value: annotation) -> None: pass\n" + call + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("annotation", ["Base", "'Base'", "list['Base']"])
def test_deferred_native_type_references_preserve_local_inherited_methods(
    tmp_path: Path, annotation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from __future__ import annotations\nclass Base:\n    def get(self) -> str: ...\n"
        + f"def helper(value: {annotation}) -> None: pass\nclass Child(Base): pass\n",
    )
    _assert_decided(result, observation)


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize(
    "value,use,decided",
    [
        ("registry[Base]", "Alias.__value__", False),
        ("Base", "", True),
        ("Base", "Alias.__value__", False),
    ],
    ids=["unproven", "native-inert", "native-exposed"],
)
def test_pep695_alias_values_use_the_same_member_surface_proof(
    tmp_path: Path, value: str, use: str, decided: bool
) -> None:
    setup = (
        "class Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return str\n"
        "registry = Modifier()\n"
        if value != "Base"
        else ""
    )
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: ...\n" + setup + f"type Alias = {value}\n{use}\n"
        "class Child(Base): pass\n",
    )
    if decided:
        _assert_decided(result, observation)
    else:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN"
        assert unknown_positions(observation) >= 1


@pytest.mark.parametrize(
    "imported,call",
    [
        ("from inspect import get_annotations", "get_annotations(helper, eval_str=True)"),
        ("import inspect as annotations", "annotations.get_annotations(helper, eval_str=True)"),
    ],
    ids=["direct", "dotted"],
)
def test_inspect_annotation_evaluation_prevents_member_surface_closure(
    tmp_path: Path, imported: str, call: str
) -> None:
    result, observation = _report(
        tmp_path,
        imported + "\nclass Base:\n    def get(self) -> str: return ''\nclass Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return str\n"
        "registry = Modifier()\ndef helper(value: 'registry[Base]') -> None: pass\n"
        + call
        + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    "ancestor",
    [
        "class Meta(type):\n    def __new__(mcls, name, bases, namespace):\n"
        "        cls = super().__new__(mcls, name, bases, namespace)\n"
        "        cls.get = lambda self: ''\n        return cls\nclass Root(metaclass=Meta): pass\n",
        "class Root:\n    def __init_subclass__(cls) -> None:\n        cls.get = lambda self: ''\n",
    ],
    ids=["metaclass", "subclass-hook"],
)
def test_unproven_ancestor_transformations_do_not_certify_intermediate_methods(
    tmp_path: Path, ancestor: str
) -> None:
    result, observation = _report(
        tmp_path,
        ancestor
        + "class Base(Root):\n    def get(self) -> dict: return {}\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "imported,dispatch",
    [
        (
            "from typing import get_type_hints",
            "inspectors = [get_type_hints]\ninspectors[0](helper)",
        ),
        (
            "from typing import get_type_hints",
            "def choose(): return get_type_hints\nchoose()(helper)",
        ),
        (
            "import inspect",
            "inspectors = [inspect.get_annotations]\ninspectors[0](helper, eval_str=True)",
        ),
    ],
    ids=["stored", "returned", "dotted-stored"],
)
def test_namespace_evaluator_value_escapes_prevent_member_surface_closure(
    tmp_path: Path, imported: str, dispatch: str
) -> None:
    result, observation = _report(
        tmp_path,
        imported + "\nclass Base:\n    def get(self) -> str: return ''\nclass Modifier:\n"
        "    def __getitem__(self, cls): cls.get = lambda self: {}; return str\n"
        "registry = Modifier()\ndef helper(value: 'registry[Base]') -> None: pass\n"
        + dispatch
        + "\nclass Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    assert unknown_positions(observation) >= 1
    assert trace_valid_violations(observation) == ()
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is True
    assert base.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("namespace", ["globals", "locals", "vars"])
def test_stored_global_namespace_access_does_not_prove_class_identity(
    tmp_path: Path, namespace: str
) -> None:
    result, observation = _report(
        tmp_path,
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Replacement:\n    def get(self) -> dict: return {}\n"
        f"namespaces = [{namespace}]\nnamespaces[0]()['Base'] = Replacement\n"
        "class Child(Base): pass\n",
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN"
    base = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.Base"
    )
    assert base.data.get("source_binding_unique") is False


@pytest.mark.parametrize(
    "mutation",
    [
        "import abc\ndef rewrite(cls):\n    arm(cls.helper.__globals__)\n    return cls\n"
        "abc.update_abstractmethods = rewrite\n",
        "import inspect\ndef rewrite(cls):\n    arm(cls.helper.__globals__)\n    return ''\n"
        "inspect.signature = rewrite\n",
        "import functools\ndef rewrite(fn):\n    arm(fn.__globals__)\n"
        "    return lambda wrapper: wrapper\nfunctools.wraps = rewrite\n",
        "import builtins\noriginal_exec = builtins.exec\n"
        "def rewrite(text, namespace, local):\n    arm(namespace)\n"
        "    return original_exec(text, namespace, local)\nbuiltins.exec = rewrite\n",
    ],
    ids=["abc-update-abstractmethods", "inspect-signature", "functools-wraps", "builtins-exec"],
)
def test_native_dataclass_dependencies_may_expose_the_defining_namespace(
    tmp_path: Path, mutation: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import marker\nfrom typing import Generic, TypeVar\nT = TypeVar('T')\n"
        "class Base(Generic[T]):\n    def get(self) -> str: return ''\n"
        "class Child(Base[str]): pass\n",
        implementation=(
            "from dataclasses import dataclass\nfrom typing import TypeVar\n"
            "from .mutator import armed\n@dataclass\nclass Holder:\n"
            "    def helper(self) -> None: pass\nmarker = True\n"
        ),
        extra_files={
            "sample/app/mutator.py": (
                "def arm(namespace):\n"
                "    native = namespace['TypeVar'].__init__.__globals__['Generic']\n"
                "    original = native.__init_subclass__.__func__\n"
                "    def transformed(cls, *args, **kwargs):\n"
                "        original(cls, *args, **kwargs)\n        cls.get = lambda self: {}\n"
                "    native.__init_subclass__ = classmethod(transformed)\n"
                + mutation
                + "armed = True\n"
            )
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()


def test_native_dataclass_generated_methods_carry_nonliteral_default_namespaces(
    tmp_path: Path,
) -> None:
    result, observation = _report(
        tmp_path,
        "from .impl import marker\nfrom typing import Protocol\n"
        "class Base(Protocol):\n    def get(self) -> str: return ''\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\nfrom typing import TypeVar\n"
            "class Poison:\n    def __repr__(self):\n"
            "        native = self.__repr__.__func__.__globals__['TypeVar']"
            ".__init__.__globals__['Generic']\n"
            "        native.__init_subclass__ = classmethod("
            "lambda cls: setattr(cls, 'get', lambda self: {}))\n        return 'poison'\n"
            "poison = Poison()\n@dataclass\nclass Holder:\n"
            "    value: int = (poison,)\nmarker = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize("provider", ["dataclasses", "typing"])
def test_scanned_native_provider_is_not_a_native_creation_proof(
    tmp_path: Path, provider: str
) -> None:
    if provider == "dataclasses":
        implementation = (
            "from dataclasses import dataclass\nfrom typing import TypeVar\n"
            "@dataclass\nclass Holder:\n    def helper(self): pass\nmarker = True\n"
        )
        local_provider = (
            "def dataclass(cls):\n"
            "    native = cls.helper.__globals__['TypeVar'].__init__.__globals__['Generic']\n"
            "    native.__init_subclass__ = classmethod("
            "lambda cls: setattr(cls, 'get', lambda self: {}))\n    return cls\n"
        )
        api = (
            "from .impl import marker\nfrom typing import Protocol\n"
            "class Base(Protocol):\n    def get(self) -> str: return ''\nclass Child(Base): pass\n"
        )
    else:
        implementation = ""
        local_provider = (
            "class TypedDict:\n    def __init_subclass__(cls):\n"
            "        names = __import__('sys').modules[cls.__module__].__dict__\n"
            "        names['ABCMeta'].__init__ = lambda cls, *a, **kw: setattr("
            "names['Base'], 'get', lambda self: {})\n"
        )
        api = (
            "from __future__ import annotations\nfrom abc import ABC, ABCMeta\n"
            "from typing import TypedDict\nclass Owner(TypedDict):\n    value: 'str'\n"
            "class Base:\n    def get(self) -> str: return ''\n"
            "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n"
        )
    _write_app(
        tmp_path, public=["sample.app.api:Child"], init="", api=api, implementation=implementation
    )
    (tmp_path / "sample").rename(tmp_path / provider)
    (tmp_path / provider / "__init__.py").write_text(local_provider)
    contract = tmp_path / "contract.json"
    contract.write_text(contract.read_text().replace("sample", provider))
    model, code = analyze_snapshot(
        tmp_path,
        git_head="a" * 40,
        dirty=False,
        roots=(provider,),
        namespace=provider,
        contract_path=contract,
    )
    assert code == 0
    observation = parse_observation(decode_canonical_model(model))
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "future, declaration, decided",
    [
        (False, "class Owner(TypedDict):\n    value: 'int'\n", True),
        (True, "class Owner(TypedDict):\n    value: list[int]\n", True),
        (False, "class Owner(TypedDict):\n    value: int\n", False),
        (True, "class Owner(TypedDict, total=False):\n    value: int\n", False),
        (True, "class Owner(TypedDict):\n    value: int = 1\n", False),
        (True, "class Owner(TypedDict):\n    def helper(self): pass\n", False),
    ],
    ids=["string", "future", "eager", "option", "value", "method"],
)
def test_native_typed_dict_owner_creation_has_only_inert_field_inputs(
    tmp_path: Path, future: bool, declaration: str, decided: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            ("from __future__ import annotations\n" if future else "")
            + "from abc import ABCMeta\nfrom typing import TypedDict\n"
            + declaration
            + "marker = True\n"
        ),
    )
    if decided:
        _assert_decided(result, observation)
    else:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1


@pytest.mark.parametrize(
    "future, body, decided",
    [
        (False, "    value: 'int' = (1, 'a', None)\n", True),
        (True, "    value: int = -1\n", True),
        (False, "    marker = ({'x': [1, 2]},)\n", True),
        (False, "    def helper(self, value=(1, 'a'), *, flag=False) -> None: pass\n", True),
        (False, "    value: int = 1\n", False),
        (False, "    def helper(self, value: int) -> None: pass\n", False),
        (False, "    def __init__(self, value: list[int]): pass\n", False),
        (False, "    def helper(self, value=(poison,)): pass\n", False),
        (False, "    marker = ({'x': [poison]},)\n", False),
        (False, "    marker = set()\n", False),
        (False, "    import abc\n", False),
        (False, "    class Nested: pass\n", False),
        (False, "    assert True\n", False),
        (False, "    1 + 2\n", False),
    ],
    ids=[
        "literal-field",
        "future-field",
        "literal-container",
        "literal-method-defaults",
        "eager-field",
        "eager-method",
        "eager-init",
        "nonliteral-default",
        "nested-nonliteral",
        "set-call",
        "body-import",
        "nested-class",
        "assertion",
        "expression",
    ],
)
def test_native_dataclass_owner_creation_requires_inert_headers_and_body(
    tmp_path: Path, future: bool, body: str, decided: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            ("from __future__ import annotations\n" if future else "")
            + "from abc import ABCMeta\nfrom dataclasses import dataclass\npoison = object()\n"
            + "@dataclass\nclass Owner:\n"
            + body
            + "marker = True\n"
        ),
    )
    if decided:
        _assert_decided(result, observation)
    else:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1


def test_passed_generated_dataclass_owner_carries_its_defining_namespace(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return ''\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from abc import ABCMeta\nfrom dataclasses import dataclass\n"
            "@dataclass\nclass Owner:\n    value: 'int' = 1\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "def mutate(owner):\n    owner.__init__.__globals__['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: hook(cls)\nmutate(Owner)\nmarker = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize(
    "binding, redirected, implicit_exposure",
    [
        ("__module__ = 'abc'", True, False),
        ("__module__: 'str' = 'abc'", True, False),
        ("other = __module__ = 'abc'", True, False),
        ("__module__: 'str'", False, False),
        ("locals().update({'__module__': 'abc'})", True, True),
        ("def helper(self, value=(__module__ := 'abc')): pass", True, False),
        ("helper = lambda self, value=(__module__ := 'abc'): None", True, False),
        ("def helper(self, __module__='abc'): pass", False, False),
        ("helper = lambda self: (__module__ := 'abc')", False, False),
        ("match 'abc':\n        case __module__:\n            pass", True, True),
        (
            "__module__: 'str'\n    def helper(self, value=(__module__ := 'abc')): pass",
            True,
            False,
        ),
    ],
    ids=[
        "direct",
        "annotated-value",
        "chained",
        "annotation-only",
        "dynamic-body",
        "method-default-binding",
        "lambda-default-binding",
        "method-parameter",
        "lambda-body",
        "capture-binding",
        "annotation-and-real-binding",
    ],
)
@pytest.mark.parametrize("passed", [False, True], ids=["inert", "passed"])
def test_generated_dataclass_owner_can_redirect_its_native_namespace(
    tmp_path: Path, binding: str, redirected: bool, implicit_exposure: bool, passed: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\n@dataclass\nclass Owner:\n"
            f"    {binding}\n    value: 'int' = 1\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "def mutate(owner):\n    namespace = owner.__init__.__globals__\n"
            "    if 'ABCMeta' in namespace:\n        namespace['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: hook(cls)\n"
            + ("mutate(Owner)\n" if passed else "")
            + "marker = True\n"
        ),
    )
    if implicit_exposure or passed and redirected:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1
        assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    else:
        _assert_decided(result, observation)


@pytest.mark.parametrize("route", ["assignment-alias", "import-alias", "reexport"])
def test_redirected_generated_owner_transfer_uses_existing_import_closure(
    tmp_path: Path, route: str
) -> None:
    mutation = (
        "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
        "def mutate(owner):\n    owner.__init__.__globals__['ABCMeta'].__init__ = "
        "lambda cls, *a, **kw: hook(cls)\nmutate(Carrier)\nmarker = True\n"
    )
    extra_files = {}
    if route == "assignment-alias":
        footer = "Carrier = Owner\n" + mutation
    else:
        footer = "from .mutator import marker\n"
        if route == "import-alias":
            imported = "from .impl import Owner as Carrier\n"
        else:
            imported = "from .forward import Carrier\n"
            extra_files["sample/app/forward.py"] = "from .impl import Owner as Carrier\n"
        extra_files["sample/app/mutator.py"] = imported + mutation
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\n@dataclass\nclass Owner:\n"
            "    __module__ = 'abc'\n    value: 'int' = 1\n" + footer
        ),
        extra_files=extra_files,
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize(
    "body, namespace_proven",
    [
        ("    value: 'int' = field(default=1)\n", False),
        ("    value: int = 1\n", True),
        ("    def helper(self, value=object()): pass\n", True),
        ("    value: 'tuple' = (1, 'safe')\n", True),
        ("    helper = lambda self: None\n", True),
        ("    @staticmethod\n    def helper(value=object()): pass\n", True),
        ("    @classmethod\n    def helper(cls): pass\n", True),
        ("    @property\n    def helper(self): return None\n", True),
        ("    class Nested: pass\n", True),
    ],
    ids=[
        "field-factory",
        "eager-annotation",
        "method-default",
        "literal-container",
        "lambda",
        "static-method",
        "class-method",
        "property",
        "plain-nested-class",
    ],
)
@pytest.mark.parametrize("passed", [False, True], ids=["inert", "passed"])
def test_generated_owner_creation_limits_do_not_redirect_its_namespace(
    tmp_path: Path, body: str, namespace_proven: bool, passed: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass, field\n@dataclass\nclass Owner:\n"
            + body
            + "def mutate(owner):\n    namespace = owner.__init__.__globals__\n"
            "    if 'ABCMeta' in namespace:\n        namespace['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: None\n"
            + ("mutate(Owner)\n" if passed else "")
            + "marker = True\n"
        ),
    )
    if not namespace_proven:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1
        assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    else:
        _assert_decided(result, observation)


@pytest.mark.parametrize(
    "binding, redirected",
    [
        ("value = descriptor", True),
        ("value: 'int' = descriptor", True),
        ("value: 'int' = field(default=descriptor)", True),
        ("value: 'tuple' = (descriptor,)", False),
        ("value, = (descriptor,)", True),
        ("value, = (1,)", False),
    ],
    ids=["assigned", "annotated-value", "field-forwarded", "contained", "extracted", "literal"],
)
@pytest.mark.parametrize("passed", [False, True], ids=["inert", "passed"])
def test_generated_owner_descriptor_can_redirect_its_native_namespace(
    tmp_path: Path, binding: str, redirected: bool, passed: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass, field\n"
            "class Descriptor:\n    def __set_name__(self, owner, name):\n"
            "        owner.__module__ = 'abc'\ndescriptor = Descriptor()\n"
            "@dataclass\nclass Owner:\n"
            f"    {binding}\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "def mutate(owner):\n    namespace = owner.__init__.__globals__\n"
            "    if 'ABCMeta' in namespace:\n        namespace['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: hook(cls)\n"
            + ("mutate(Owner)\n" if passed else "")
            + "marker = True\n"
        ),
    )
    if redirected:
        [assessment] = result.rule_assessments or ()
        assert assessment.status == "UNKNOWN" and assessment.undecided == 1
        assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
    else:
        _assert_decided(result, observation)


@pytest.mark.parametrize(
    "setup, body",
    [
        (
            "class Descriptor:\n    def __set_name__(self, owner, name):\n"
            "        owner.__module__ = 'abc'\ndef wrap(fn): return Descriptor()\n",
            "    @wrap\n    def helper(self): pass\n",
        ),
        (
            "class Meta(type):\n    def __set_name__(cls, owner, name):\n"
            "        owner.__module__ = 'abc'\n",
            "    class Nested(metaclass=Meta): pass\n",
        ),
    ],
    ids=["decorated-method", "nested-metaclass"],
)
@pytest.mark.parametrize("passed", [False, True], ids=["implicit-only", "later-passed"])
def test_generated_owner_declarations_can_receive_and_redirect_owner(
    tmp_path: Path, setup: str, body: str, passed: bool
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\n"
            + setup
            + "@dataclass\nclass Owner:\n"
            + body
            + "    value: 'int' = 1\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "def mutate(owner):\n    owner.__init__.__globals__['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: hook(cls)\n"
            + ("mutate(Owner)\n" if passed else "")
            + "marker = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize("changed", [False, True], ids=["inert-repr", "changed-repr"])
@pytest.mark.parametrize(
    "body",
    [
        "    value: 'int' = descriptor\n",
        "    value: 'int'\n    def helper(self, arg=(value := Descriptor())): pass\n",
        "    value: 'int'\n    match Descriptor():\n        case value: pass\n",
        "    value: 'int'\n    match [Descriptor()]:\n        case [value, *extra]: pass\n",
        "    value: 'int'\n    match {'first': Descriptor()}:\n"
        "        case {'first': value, **extra}: pass\n",
    ],
    ids=["direct-binding", "named-expression", "capture", "sequence-star", "mapping-rest"],
)
def test_generated_owner_descriptor_receives_owner_without_later_transfer(
    tmp_path: Path, changed: bool, body: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\nclass Descriptor:\n"
            "    def __set_name__(self, owner, name):\n"
            "        owner.__module__ = 'abc'\n        self.owner = owner\n"
            "    def __repr__(self):\n        namespace = self.owner.__init__.__globals__\n"
            + (
                "        namespace['ABCMeta'].__init__ = lambda cls, *a, **kw: hook(cls)\n"
                if changed
                else ""
            )
            + "        return 'descriptor'\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "descriptor = Descriptor()\n@dataclass\nclass Owner:\n" + body + "marker = True\n"
        ),
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}


@pytest.mark.parametrize("passed", [False, True], ids=["implicit-only", "later-passed"])
@pytest.mark.parametrize(
    "binding",
    ["from .carrier import descriptor as item", "import sample.app.carrier as item"],
    ids=["import-from", "import-module"],
)
def test_generated_owner_imported_member_requires_owner_receipt_proof(
    tmp_path: Path, passed: bool, binding: str
) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\n@dataclass\nclass Owner:\n"
            f"    {binding}\n    value: 'int' = 1\n"
            "def hook(cls): cls.__annotations__['value'].get = lambda self: {}\n"
            "def mutate(owner):\n    owner.__init__.__globals__['ABCMeta'].__init__ = "
            "lambda cls, *a, **kw: hook(cls)\n"
            + ("mutate(Owner)\n" if passed else "")
            + "marker = True\n"
        ),
        extra_files={
            "sample/app/carrier.py": (
                "class Descriptor:\n    def __set_name__(self, owner, name):\n"
                "        owner.__module__ = 'abc'\ndescriptor = Descriptor()\n"
            )
        },
    )
    [assessment] = result.rule_assessments or ()
    assert assessment.status == "UNKNOWN" and assessment.undecided == 1
    assert unknown_positions_by_rule(observation) == {"APP-TYPES-NOT-DICT": 1}
