# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Class namespace proofs retain source dependencies and reject user code effects."""

import ast
import sys
from pathlib import Path
from types import ModuleType

import pytest
from test_local_inherited_methods import _assert_decided, _report

from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
from archkeel.analyzer.python.source import (
    ParsedModule,
    class_namespace_static,
    parse_sources,
    unproven_member_bindings,
)


def _resolve(root: Path, source: str, *, extra: dict[str, str] | None = None) -> ParsedModule:
    files = {"owner.py": source, **(extra or {})}
    package = root / "sample"
    package.mkdir()
    for name, content in files.items():
        (package / name).write_text(content)
    parsed = parse_sources(sorted(package.glob("*.py")), root=root, namespace="sample").modules
    imports = collect_imports(parsed, {module.module for module in parsed}, {}, namespace="sample")
    resolve_reexports(imports, {module.module: module.all_exports for module in parsed}, parsed)
    return next(module for module in parsed if module.module == "sample.owner")


def _namespace_proven(module: ParsedModule) -> bool:
    owner = next(
        node for node in module.tree.body if isinstance(node, ast.ClassDef) and node.name == "Owner"
    )
    return class_namespace_static(module, owner)


@pytest.mark.parametrize(
    "setup, expression, extra",
    [
        ("", "64 * 1024 * 1024", {}),
        ("LIMIT = 64\n", "LIMIT * 1024", {}),
        ("LIMIT = 64\nALIAS = LIMIT\n", "-ALIAS", {}),
        ("VALUE = ('safe', 1)\n", "VALUE", {}),
        ("from .values import LIMIT as BUDGET\n", "BUDGET * 1024", {"values.py": "LIMIT = 64\n"}),
    ],
    ids=["arithmetic", "constant", "alias", "literal-container", "imported-constant"],
)
def test_closed_values_prove_the_class_namespace(
    tmp_path: Path, setup: str, expression: str, extra: dict[str, str]
) -> None:
    module = _resolve(tmp_path, setup + f"class Owner:\n    value = {expression}\n", extra=extra)
    assert _namespace_proven(module)
    assert {ast.unparse(value) for value in module._proven_class_values} == {expression}


@pytest.mark.parametrize(
    "setup, body, footer, extra",
    [
        ("VALUE = descriptor\n", "value = VALUE", "", {}),
        ("VALUE = Descriptor()\n", "value = VALUE", "", {}),
        ("VALUE = set()\n", "value = VALUE", "", {}),
        ("VALUE = (set(),)\n", "value = VALUE", "", {}),
        ("VALUE = Operator()\n", "value = VALUE * 1024", "", {}),
        ("VALUE = 1\nVALUE = descriptor\n", "value = VALUE", "", {}),
        (
            "VALUE = 1\n",
            "value = VALUE",
            "def replace():\n    global VALUE\n    VALUE = descriptor\n",
            {},
        ),
        ("VALUE = 1\n", "VALUE = descriptor\n    value = VALUE", "", {}),
        ("", "value = VALUE", "VALUE = 1\n", {}),
        ("from missing import VALUE\n", "value = VALUE", "", {}),
        (
            "from .values import VALUE\n",
            "value = VALUE",
            "",
            {"values.py": "VALUE = descriptor\n"},
        ),
        (
            "from .values import VALUE\n",
            "value = VALUE",
            "from . import values\nvalues.VALUE = descriptor\n",
            {"values.py": "VALUE = 1\n"},
        ),
    ],
    ids=[
        "unknown-value",
        "descriptor-constructor",
        "literal-eval-call",
        "nested-literal-eval-call",
        "overloaded-operator",
        "rebound",
        "global-rebound",
        "class-shadowed",
        "late-binding",
        "missing-source",
        "unproven-source",
        "source-member-mutated",
    ],
)
def test_unproven_or_changed_values_keep_the_class_namespace_unknown(
    tmp_path: Path, setup: str, body: str, footer: str, extra: dict[str, str]
) -> None:
    module = _resolve(tmp_path, setup + f"class Owner:\n    {body}\n" + footer, extra=extra)
    assert not _namespace_proven(module)


def test_proven_constant_default_keeps_native_inheritance_decided(tmp_path: Path) -> None:
    result, observation = _report(
        tmp_path,
        "from abc import ABC\nfrom .impl import marker\n"
        "class Base:\n    def get(self) -> str: return 'safe'\n"
        "class Holder(ABC):\n    value: Base\nclass Child(Base): pass\n",
        implementation=(
            "from dataclasses import dataclass\nLIMIT = 64\n"
            "@dataclass\nclass Owner:\n    value: 'int' = LIMIT * 1024\nmarker = True\n"
        ),
    )
    _assert_decided(result, observation)


@pytest.mark.parametrize("body", ["pass", '"plain value"', "value: str", "value: 'Unknown'"])
def test_unexposed_plain_constructor_return_preserves_class_members(
    tmp_path: Path, body: str
) -> None:
    module = _resolve(
        tmp_path,
        f"class Owner:\n    {body}\ndef make() -> Owner:\n    return Owner()\nalias = make\n",
    )
    assert "Owner" not in unproven_member_bindings(module)


@pytest.mark.parametrize(
    ("header", "annotation"),
    [
        ("(value=opaque_probe()) -> Owner", False),
        ("(*, value=opaque_probe()) -> Owner", False),
        ("(value: opaque_probe()) -> Owner", True),
        ("(*values: opaque_probe()) -> Owner", True),
        ("() -> opaque_probe()", True),
    ],
    ids=[
        "default",
        "keyword-default",
        "argument-annotation",
        "vararg-annotation",
        "return-annotation",
    ],
)
@pytest.mark.parametrize("future", [False, True], ids=["eager", "future"])
def test_constructor_return_headers_follow_their_execution_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, header: str, annotation: bool, future: bool
) -> None:
    provider = ModuleType("ctor_review_provider")

    def opaque_probe():
        sys._getframe(1).f_globals["Owner"].__annotations__["value"] = dict
        return str

    provider.__dict__["opaque_probe"] = opaque_probe
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    source = (
        ("from __future__ import annotations\n" if future else "")
        + "from ctor_review_provider import opaque_probe\n"
        f"class Owner:\n    value: str\ndef make{header}:\n    return Owner()\n"
    )
    runtime = {"__name__": "sample.owner"}
    exec(source, runtime)
    # The analyzer keeps the eager reading of annotations; Python 3.14 defers them (PEP 649).
    executed = not future or not annotation
    ran = executed and not (annotation and sys.version_info >= (3, 14))
    assert (runtime["Owner"].__annotations__["value"] is dict) is ran

    module = _resolve(tmp_path, source)
    assert ("Owner" in unproven_member_bindings(module)) is executed
    assert bool(module._proven_constructor_returns) is not executed


@pytest.mark.parametrize(
    ("header", "annotation"),
    [
        ("(value=Missing) -> Owner", False),
        ("(value: Missing) -> Owner", True),
        ("() -> Missing", True),
        ("(value: Missing.attribute) -> Owner", True),
        ("(value: Missing[str]) -> Owner", True),
        ("() -> Missing | str", True),
    ],
)
def test_constructor_return_header_requires_name_binding_evidence(
    tmp_path: Path, header: str, annotation: bool
) -> None:
    source = f"class Owner:\n    value: str\ndef make{header}:\n    return Owner()\n"
    # Python 3.14 defers annotations (PEP 649), so only a default value fails at definition time.
    if not annotation or sys.version_info < (3, 14):
        with pytest.raises(NameError):
            exec(source, {"__name__": "sample.owner"})
    module = _resolve(tmp_path, source)
    assert "Owner" in unproven_member_bindings(module)
    assert not module._proven_constructor_returns


@pytest.mark.parametrize("exposed", [False, True])
def test_constructor_return_retains_its_eager_header_class_dependency(
    tmp_path: Path, exposed: bool
) -> None:
    module = _resolve(
        tmp_path,
        "class Other: pass\nclass Owner:\n    value: str\n"
        "def make(value: Other) -> Owner:\n    return Owner()\n"
        + ("consume(Other)\n" if exposed else ""),
    )
    assert ("Owner" in unproven_member_bindings(module)) is exposed
    assert bool(module._proven_constructor_returns) is not exposed


@pytest.mark.parametrize(
    "header",
    [
        "(value: str = 'safe') -> Owner",
        "(*, value: int = 0) -> Owner",
        "(value: 'Missing' = None) -> 'Missing'",
    ],
)
def test_constructor_return_inert_headers_remain_proven(tmp_path: Path, header: str) -> None:
    module = _resolve(
        tmp_path,
        f"class Owner:\n    value: str\ndef make{header}:\n    return Owner()\n",
    )
    assert "Owner" not in unproven_member_bindings(module)
    assert module._proven_constructor_returns


@pytest.mark.parametrize(
    "source",
    [
        "class Owner:\n    value: str = 'value'\ndef make(): return Owner()\n",
        "class Owner:\n    def __init__(self): pass\ndef make(): return Owner()\n",
        "class Owner:\n    def __new__(cls): pass\ndef make(): return Owner()\n",
        "class Owner:\n    def __del__(self): pass\ndef make(): return Owner()\n",
        "class Owner:\n    def helper(self): pass\ndef make(): return Owner()\n",
        "class Base: pass\nclass Owner(Base): pass\ndef make(): return Owner()\n",
        "class Meta(type): pass\nclass Owner(metaclass=Meta): pass\ndef make(): return Owner()\n",
        "@wrap\nclass Owner: pass\ndef make(): return Owner()\n",
        "class Owner:\n    value: evaluate()\ndef make(): return Owner()\n",
        "class Owner: pass\ndef make(): return Owner(1)\n",
        "class Owner: pass\ndef make(): return Owner(value=1)\n",
        "class Owner: pass\nAlias = Owner\ndef make(): return Alias()\n",
        "class Owner: pass\ndef make(Owner): return Owner()\n",
        "class Owner: pass\ndef make():\n    Owner = replacement\n    return Owner()\n",
        "class Owner: pass\ndef make():\n    global Owner\n    return Owner()\n",
        "class Owner: pass\ndef make():\n    from missing import Owner\n    return Owner()\n",
        "class Owner: pass\ndef make():\n    return Owner()\n    Owner = replacement\n",
        "class Owner: pass\ndef make(): return Owner()\nOwner = replacement\n",
        "def make(): return Owner()\nclass Owner: pass\n",
        "class Owner: pass\ndef outer():\n    def make(): return Owner()\n",
        "class Owner: pass\ndef make(value=Owner()): return value\n",
        "class Owner: pass\ndef make():\n    value = Owner()\n    return value\n",
        "class Owner: pass\ndef make(): return consume(Owner())\n",
        "class Owner: pass\ndef make(): return Owner().__class__\n",
        "class Owner: pass\ndef make(): return (Owner(),)\n",
        "class Owner: pass\n@wrap\ndef make(): return Owner()\n",
    ],
    ids=[
        "default-value",
        "initializer",
        "allocator",
        "destructor",
        "method-globals",
        "base",
        "metaclass",
        "class-decorator",
        "effectful-annotation",
        "argument",
        "keyword",
        "class-alias",
        "parameter-shadow",
        "local-shadow",
        "global-declaration",
        "import-shadow",
        "later-local-shadow",
        "rebound",
        "forward-class",
        "nested-function",
        "default-time",
        "assigned-result",
        "passed-result",
        "chained-result",
        "contained-result",
        "function-decorator",
    ],
)
def test_constructor_return_proof_rejects_unproven_bindings_and_effects(
    tmp_path: Path, source: str
) -> None:
    module = _resolve(tmp_path, source)
    assert "Owner" in unproven_member_bindings(module)


@pytest.mark.parametrize(
    ("footer", "extra"),
    [
        ("make()\n", {}),
        ("consume(make)\n", {}),
        ("alias = make\nalias()\n", {}),
        ("alias = make\nconsume(alias)\n", {}),
        ("alias = make\nforward = alias\nforward()\n", {}),
        ("instance = make()\ninstance.__class__.changed = True\n", {}),
        ("make.__globals__['Owner'].changed = True\n", {}),
        ("", {"consumer.py": "from .owner import make\nmake()\n"}),
        ("", {"consumer.py": "from .owner import make as alias\nconsume(alias)\n"}),
        ("", {"consumer.py": "from . import owner\nconsume(owner.make)\n"}),
        ("", {"consumer.py": "from . import owner\nowner.make()\n"}),
        ("", {"consumer.py": "import sample.owner as receiver\nreceiver.make()\n"}),
        (
            "",
            {
                "facade.py": "from .owner import make\n__all__ = ['make']\n",
                "consumer.py": "from . import facade\nfacade.make()\n",
            },
        ),
        (
            "",
            {"consumer.py": "from . import owner\nreceiver = owner\nreceiver.make()\n"},
        ),
        (
            "",
            {
                "facade.py": "from .owner import make\n__all__ = ['make']\n",
                "consumer.py": "from .facade import make as alias\nalias()\n",
            },
        ),
        (
            "",
            {
                "facade.py": "from .owner import make\n__all__ = ['make']\n",
                "consumer.py": "from .facade import make as alias\nconsume(alias)\n",
            },
        ),
    ],
    ids=[
        "called",
        "passed",
        "alias-called",
        "alias-passed",
        "alias-chain",
        "instance-class-mutation",
        "function-globals",
        "import-called",
        "import-passed",
        "module-import",
        "module-dotted-called",
        "module-import-dotted-called",
        "facade-module-dotted-called",
        "module-receiver-alias-called",
        "reexport-called",
        "reexport-passed",
    ],
)
def test_constructor_return_proof_retracts_when_its_function_namespace_is_exposed(
    tmp_path: Path, footer: str, extra: dict[str, str]
) -> None:
    module = _resolve(
        tmp_path,
        "class Owner:\n    value: str\ndef make() -> Owner:\n    return Owner()\n" + footer,
        extra=extra,
    )
    assert "Owner" in unproven_member_bindings(module)
    assert not module._proven_constructor_returns


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax requires Python 3.12")
@pytest.mark.parametrize(
    "source",
    [
        "class Owner[T]: pass\ndef make(): return Owner()\n",
        "class Owner: pass\ndef make[Owner](): return Owner()\n",
    ],
    ids=["generic-class", "type-parameter-shadow"],
)
def test_constructor_return_proof_rejects_generic_binding_ambiguity(
    tmp_path: Path, source: str
) -> None:
    module = _resolve(tmp_path, source)
    assert "Owner" in unproven_member_bindings(module)


@pytest.mark.parametrize(
    "body, creation_static",
    [
        ("def helper(self, value=(__module__ := 'abc')): pass", True),
        ("helper = lambda self, value=(__module__ := 'abc'): opaque()", True),
        ("helper = lambda self: opaque()", True),
        ("helper = lambda self, value=opaque(): None", False),
        ("helper = lambda self, *, value=opaque(): None", False),
        ("helper = lambda self, value=(bound := unknown): None", False),
        ("helper = lambda self, value=(bound := (nested := unknown)): None", False),
        ("def helper(self, value=(__init_subclass__ := lambda cls: opaque())): pass", False),
        ("def get(self): return ''\n    def helper(self, value=(get := 1)): pass", True),
    ],
)
def test_native_creation_keeps_eager_effects_and_member_binding_proofs_separate(
    tmp_path: Path, body: str, creation_static: bool
) -> None:
    from archkeel.analyzer.python.source import native_owner_creation_static, unproven_class_body

    module = _resolve(
        tmp_path,
        "from dataclasses import dataclass\n@dataclass\nclass Owner:\n"
        f"    {body}\n    value: 'int' = 1\n",
    )
    owner = next(node for node in module.tree.body if isinstance(node, ast.ClassDef))
    assert native_owner_creation_static(module, owner, frozenset()) is creation_static
    assert unproven_class_body(module, owner)


@pytest.mark.parametrize("default, expected", [("", []), ("value=opaque()", ["called"])])
def test_lambda_creation_executes_defaults_before_its_deferred_body(default: str, expected) -> None:
    namespace = {"effects": []}
    exec(
        f"def opaque():\n    effects.append('called')\ncallback = lambda {default}: opaque()\n",
        namespace,
    )
    assert namespace["effects"] == expected
    namespace["callback"]()
    assert namespace["effects"] == [*expected, "called"]
