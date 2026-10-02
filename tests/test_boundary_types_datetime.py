# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Known datetime leaves do not certify arbitrary external or shadowed types."""

from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _write_app


@pytest.mark.parametrize(
    ("imports", "annotation", "unknown", "violates"),
    [
        ("from datetime import datetime", "datetime", False, False),
        ("from datetime import datetime", "datetime | None", False, False),
        ("from datetime import datetime", "list[datetime]", False, False),
        ("from datetime import datetime as Instant", "Instant", False, False),
        ("import datetime", "datetime.datetime", False, False),
        ("import datetime as clock", "clock.datetime", False, False),
        ("from external import datetime", "datetime", True, False),
        ("from datetime import timedelta", "timedelta", True, False),
        ("from datetime import datetime\nfrom external import *", "datetime", True, False),
        ("from datetime import datetime\ndatetime = object()", "datetime", True, False),
        ("from datetime import datetime\nclass datetime: pass", "datetime", True, False),
        ("import datetime\ndatetime = object()", "datetime.datetime", True, False),
        ("import datetime\ndel datetime", "datetime.datetime", True, False),
        ("import datetime\ndatetime.datetime = object", "datetime.datetime", True, False),
        ("import datetime as clock\nclock.datetime = object", "clock.datetime", True, False),
        (
            "import datetime as clock\nclass External: pass\nclock.datetime = External",
            "clock.datetime",
            True,
            False,
        ),
        ("import datetime as clock\ndel clock.datetime", "clock.datetime", True, False),
        (
            "import datetime as clock\nimport datetime as other\nother.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nimport datetime as other\nother.datetime = object\n"
            "import decimal as other",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nimport datetime as other\nother.datetime = object\n"
            "if condition:\n    import decimal as other",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nimport datetime as other\nother.datetime = object\n"
            "def rebound():\n    import decimal as other",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nimport datetime as other\ndel other.datetime",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nclock.datetime = object\nfrom datetime import datetime",
            "datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nother = clock\nother.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nother: object = clock\nother.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nfirst = clock\nother = first\ndel other.datetime",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nclass Mutator:\n    clock.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\ndef mutate():\n    clock.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        (
            "import datetime as clock\nif condition: clock.datetime = object",
            "clock.datetime",
            True,
            False,
        ),
        ("import datetime as clock\nif condition: clock = object()", "clock.datetime", True, False),
        ("", "object", False, True),
    ],
)
def test_datetime_dto_leaf_requires_the_exact_unambiguous_stdlib_origin(
    tmp_path: Path, imports: str, annotation: str, unknown: bool, violates: bool
) -> None:
    _write_app(
        tmp_path,
        implementation=imports
        + "\nfrom dataclasses import dataclass\n"
        + "@dataclass(frozen=True)\nclass Namespace:\n"
        + f"    now: {annotation}\n"
        + "def run() -> Namespace: ...\n",
        declared=("sample.app.impl:run", "sample.app.impl:Namespace"),
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    positions = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert bool(positions) is unknown
    violations = result.observation.records("violations") or ()
    assert bool(violations) is violates
    if positions:
        if "import *" not in imports:
            assert positions[0].data.get("path") == "return.now"


@pytest.mark.parametrize(
    ("implementation", "entry"),
    [
        (
            "from datetime import datetime\nclass Hidden: pass\n"
            "class Namespace:\n    datetime = Hidden\n    now: datetime\n"
            "def run() -> Namespace: ...\n",
            "Namespace",
        ),
        (
            "from datetime import datetime\nclass Hidden: pass\n"
            "class Converter:\n    datetime = Hidden\n"
            "    def convert(self, value: datetime) -> str: ...\n",
            "Converter",
        ),
        (
            "import datetime as clock\nclass Hidden: pass\n"
            "class Namespace:\n    clock = Hidden\n    now: clock.datetime\n"
            "def run() -> Namespace: ...\n",
            "Namespace",
        ),
        (
            "from __future__ import annotations\nfrom datetime import datetime\n"
            "class Hidden: pass\nclass Namespace:\n    now: datetime\n"
            "    datetime = Hidden\ndef run() -> Namespace: ...\n",
            "Namespace",
        ),
        (
            "from datetime import datetime\nclass Hidden: pass\n"
            "class Namespace:\n    datetime = Hidden\n    now: 'datetime'\n"
            "def run() -> Namespace: ...\n",
            "Namespace",
        ),
        (
            "from datetime import datetime\nclass Hidden: pass\n"
            "class Converter:\n    datetime = Hidden\n"
            "    def convert(self, value: 'datetime') -> str: ...\n",
            "Converter",
        ),
    ],
)
def test_class_annotation_scope_cannot_certify_a_module_datetime_binding(
    tmp_path: Path, implementation: str, entry: str
) -> None:
    _write_app(
        tmp_path,
        implementation=implementation,
        declared=("sample.app.impl:run", f"sample.app.impl:{entry}"),
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )


def test_class_datetime_uncertainty_retains_a_known_broad_union_member(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from datetime import datetime\nclass Hidden: pass\n"
            "class Namespace:\n    datetime = Hidden\n    now: datetime | object\n"
            "def run() -> Namespace: ...\n"
        ),
        declared=("sample.app.impl:run", "sample.app.impl:Namespace"),
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert result.observation.records("violations")
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("deferred", [False, True])
def test_class_scope_does_not_hide_another_dtos_broad_field(tmp_path: Path, deferred: bool) -> None:
    _write_app(
        tmp_path,
        implementation=(
            ("from __future__ import annotations\n" if deferred else "")
            + "class Hidden: pass\nclass Payload:\n    content: object\n"
            "class Converter:\n    object = Hidden\n"
            "    def convert(self, value: tuple[object, Payload]) -> str: ...\n"
        ),
        declared=("sample.app.impl:Converter", "sample.app.impl:Payload"),
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert any(
        str(item.data.get("path", "")).endswith(".content")
        for item in result.observation.records("violations") or ()
    )
