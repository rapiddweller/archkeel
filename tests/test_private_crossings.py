# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #88: private attribute access through an untyped boundary is UNKNOWN."""

from pathlib import Path

from archkeel.analyzer import observe
from archkeel.check.ratchets import measure_python_ratchets


def _observe(tmp_path: Path, source: str):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "__init__.py").write_text("")
    (sample / "access.py").write_text(source)
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "architecture-contract.json").write_text(
        '{"schema_version":"2.1.0","components":[],"rules":[]}'
    )
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="architecture-contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None
    return result.observation


def test_untyped_and_any_private_access_are_unknown_and_counted(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any\n\n"
        "def untyped(ctx):\n    return ctx.root._registry\n\n"
        "def any_value(ctx: Any):\n    return ctx._secret\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    actual = {
        (
            record.data.get("function"),
            record.data.get("parameter"),
            record.data.get("attribute"),
        )
        for record in limits
    }
    assert actual == {
        ("sample.access.any_value", "ctx", "_secret"),
        ("sample.access.untyped", "ctx", "_registry"),
    }
    measurements = measure_python_ratchets(observation)
    assert measurements.scalars.private_crossings == 0
    assert measurements.scalars.untyped_private_accesses == 2
    metrics = {
        record.kind: record.data.get("value") for record in observation.records("metrics") or ()
    }
    assert metrics["private_crossings"] == 0
    assert metrics["untyped_private_accesses"] == 2


def test_any_alias_is_resolved_and_shadowed_alias_fails_closed(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any as T\n"
        "from typing import Any as Shadowed\n\n"
        "Shadowed = object\n\n"
        "def aliased(ctx: T):\n    return ctx._secret\n\n"
        "def shadowed(ctx: Shadowed):\n    return ctx._secret\n\n"
        "def spelling(ctx: AnyLike):\n    return ctx._secret\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    assert [(record.data.get("function"), record.data.get("parameter")) for record in limits] == [
        ("sample.access.aliased", "ctx"),
        ("sample.access.spelling", "ctx"),
    ]


def test_unresolved_outer_owner_is_unknown_but_local_class_and_container_are_known(
    tmp_path: Path,
) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any\n\n"
        "class Context: pass\n\n"
        "def unresolved(ctx: Unknown[Any]):\n    return ctx._unknown\n\n"
        "def local_class(ctx: Context):\n    return ctx._local\n\n"
        "def local_container(ctx: list[Any]):\n    return ctx._container\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    assert [(record.data.get("function"), record.data.get("attribute")) for record in limits] == [
        ("sample.access.unresolved", "_unknown")
    ]


def test_qualified_any_alias_root_shadowing_fails_closed(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "import typing as t\nt = object\n\ndef shadowed(ctx: t.Any):\n    return ctx._secret\n",
    )

    assert not any(
        record.kind == "private_attribute_access_limit"
        for record in observation.records("unknowns") or ()
    )


def test_enclosing_local_any_alias_shadowing_fails_closed(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any as T\n\n"
        "def outer():\n"
        "    T = object\n"
        "    def inner(ctx: T):\n"
        "        return ctx._secret\n"
        "    return inner\n",
    )

    assert not any(
        record.kind == "private_attribute_access_limit"
        for record in observation.records("unknowns") or ()
    )


def test_local_any_import_does_not_prove_annotation_alias(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any as T\n\n"
        "def module_alias(ctx: T):\n    return ctx._module_secret\n\n"
        "def local_alias(ctx: T):\n"
        "    from typing import Any as T\n"
        "    return ctx._local_secret\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    assert [(record.data.get("function"), record.data.get("attribute")) for record in limits] == [
        ("sample.access.module_alias", "_module_secret")
    ]


def test_nested_any_keeps_the_outer_annotation_owner(tmp_path: Path) -> None:
    observation = _observe(
        tmp_path,
        "from typing import Any, Optional\n"
        "from typing import Any as T\n"
        "import typing\n\n"
        "def bare(ctx: Any):\n    return ctx._bare\n\n"
        "def qualified(ctx: typing.Any):\n    return ctx._qualified\n\n"
        "def alias(ctx: T):\n    return ctx._alias\n\n"
        "def list_any(ctx: list[Any]):\n    return ctx._list\n\n"
        "def dict_any(ctx: dict[str, Any]):\n    return ctx._dict\n\n"
        "def optional_list_any(ctx: Optional[list[Any]]):\n    return ctx._optional\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    assert {(record.data.get("function"), record.data.get("attribute")) for record in limits} == {
        ("sample.access.alias", "_alias"),
        ("sample.access.bare", "_bare"),
        ("sample.access.qualified", "_qualified"),
    }


def test_typed_local_and_public_access_are_excluded_and_chained_access_is_deduped(
    tmp_path: Path,
) -> None:
    observation = _observe(
        tmp_path,
        "class Context: pass\n\n"
        "def typed(ctx: Context):\n    return ctx._secret\n\n"
        "def local():\n"
        "    value = Context()\n"
        "    return value._secret\n\n"
        "def public(ctx):\n    return ctx.value\n\n"
        "def chained(ctx):\n    return ctx.root._registry\n",
    )

    limits = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "private_attribute_access_limit"
    ]
    assert [(record.data.get("function"), record.data.get("path")) for record in limits] == [
        ("sample.access.chained", "root._registry")
    ]
