# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 forbidden_construct rows: one probe module per ForbiddenConstructKind value."""

from __future__ import annotations

import sys

from archkeel.ir.model import ForbiddenConstructKind
from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    Variant,
    contract_rule_field,
    contract_with_rule,
)

_CONSTRUCT_SOURCE: dict[ForbiddenConstructKind, str] = {
    ForbiddenConstructKind.GETATTR: HEADER
    + (
        '"""Getattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def read_value() -> object:\n"
        '    return getattr(_Box(), "value")\n'
    ),
    ForbiddenConstructKind.HASATTR: HEADER
    + (
        '"""Hasattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def has_value() -> bool:\n"
        '    return hasattr(_Box(), "value")\n'
    ),
    ForbiddenConstructKind.CAST: HEADER
    + (
        '"""Cast probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import cast\n\n\n"
        "def as_int(value: object) -> int:\n"
        "    return cast(int, value)\n"
    ),
    ForbiddenConstructKind.EVAL: HEADER
    + (
        '"""Eval probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def compute() -> int:\n"
        '    return eval("1 + 1")\n'
    ),
    ForbiddenConstructKind.EXEC: HEADER
    + (
        '"""Exec probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def run() -> None:\n"
        '    exec("pass")\n'
    ),
    ForbiddenConstructKind.DYNAMIC_IMPORT: HEADER
    + (
        '"""Dynamic import probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "import importlib\n\n\n"
        "def load_json_module() -> object:\n"
        '    return importlib.import_module("json")\n'
    ),
    ForbiddenConstructKind.TYPE_IGNORE: HEADER
    + (
        '"""Type-ignore probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def broken() -> None:\n"
        '    value: int = "oops"  # type: ignore\n'
        "    del value\n"
    ),
    ForbiddenConstructKind.ANY_ANNOTATION: HEADER
    + (
        '"""Any-annotation probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        # AD-62: a module-level annotated variable is a second owner shape the parameter case
        # alone never exercised, since the analyzer once left it unscoped and blind.
        "VALUE: dict[str, Any] = {}\n\n\n"
        "def widen(value: Any) -> str:\n"
        "    return str(value)\n"
    ),
    ForbiddenConstructKind.PLACEHOLDER_BODY: HEADER
    + (
        '"""Placeholder-body probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def apply_discount(amount: int) -> int:\n"
        "    pass\n"
    ),
    ForbiddenConstructKind.ASSERT: HEADER
    + (
        '"""Assert probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def check(value: int) -> int:\n"
        "    assert value > 0\n"
        "    return value\n"
    ),
    ForbiddenConstructKind.BROAD_EXCEPT: HEADER
    + (
        '"""Broad-except probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def guard() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return 0\n"
    ),
    ForbiddenConstructKind.SETATTR: HEADER
    + (
        '"""Setattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def write_value() -> None:\n"
        '    setattr(_Box(), "value", 2)\n'
    ),
    ForbiddenConstructKind.DELATTR: HEADER
    + (
        '"""Delattr probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def drop_value() -> None:\n"
        '    delattr(_Box, "value")\n'
    ),
    ForbiddenConstructKind.VARS: HEADER
    + (
        '"""Vars probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def fields() -> dict[str, object]:\n"
        "    return vars(_Box())\n"
    ),
    ForbiddenConstructKind.DUNDER_DICT: HEADER
    + (
        '"""Dunder-dict probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "class _Box:\n"
        "    value = 1\n\n\n"
        "def fields() -> dict[str, object]:\n"
        "    return _Box().__dict__\n"
    ),
    ForbiddenConstructKind.STRING_LITERAL_COMPARE: HEADER
    + (
        '"""String-literal-compare probe for the architecture demo."""\n\n'
        "from __future__ import annotations\n\n\n"
        "from typing import Final\n\n"
        'EXPRESS: Final = "express"\n\n'
        "class Methods:\n"
        '    ECONOMY: Final = "economy"\n\n\n'
        "def shipping_cents(method: str) -> int:\n"
        '    if method == "express":\n'
        "        return 900\n"
        "    if method == EXPRESS:\n"
        "        return 700\n"
        "    if method == Methods.ECONOMY:\n"
        "        return 300\n"
        "    return 300\n"
    ),
}
_CONSTRUCT_RULE: dict[ForbiddenConstructKind, str] = {
    kind: (
        "CONSTRUCT-NO-ASSERT"
        if kind is ForbiddenConstructKind.ASSERT
        else "CONSTRUCT-NO-BROAD-EXCEPT"
        if kind is ForbiddenConstructKind.BROAD_EXCEPT
        else "CONSTRUCT-NO-ANY"
        if kind is ForbiddenConstructKind.ANY_ANNOTATION
        else "CONSTRUCT-NO-PLACEHOLDER"
        if kind is ForbiddenConstructKind.PLACEHOLDER_BODY
        else "CONSTRUCT-NO-STRING-LITERAL-COMPARE"
        if kind is ForbiddenConstructKind.STRING_LITERAL_COMPARE
        else "CONSTRUCT-NO-DYNAMIC"
    )
    for kind in ForbiddenConstructKind
}
# any_annotation's probe carries two owner shapes (a module variable and a parameter), and the
# string-literal probe carries three comparisons; both preserve one diagnostic code per finding.
_CONSTRUCT_VIOLATION_COUNT: dict[ForbiddenConstructKind, int] = {
    kind: (
        2
        if kind is ForbiddenConstructKind.ANY_ANNOTATION
        else 3
        if kind is ForbiddenConstructKind.STRING_LITERAL_COMPARE
        else 1
    )
    for kind in ForbiddenConstructKind
}
_CONSTRUCT_VARIANTS = tuple(
    Variant(
        id=f"class-a-construct-{kind.value}",
        section="class_a",
        item=f"forbidden_construct:{kind.value}",
        summary=f"A new shop.model probe module uses {kind.value}, firing {_CONSTRUCT_RULE[kind]}.",
        files={f"shop/model/probe_{kind.value}.py": _CONSTRUCT_SOURCE[kind]},
        expected_violations=(_CONSTRUCT_RULE[kind],) * _CONSTRUCT_VIOLATION_COUNT[kind]
        + (("EXTERNAL-JSON-STORE",) if kind is ForbiddenConstructKind.DYNAMIC_IMPORT else ()),
        expected_codes=("rule.violated",) * _CONSTRUCT_VIOLATION_COUNT[kind]
        + (("rule.violated",) if kind is ForbiddenConstructKind.DYNAMIC_IMPORT else ()),
    )
    for kind in ForbiddenConstructKind
)
# One scope below the boundary: `parse_quantity`'s owner is shop.cli.main.main.parse_quantity.
_MAIN_WITH_NESTED_HANDLER = HEADER + (
    '"""Argument parsing and composition; the single broad error boundary lives here."""\n\n'
    "from __future__ import annotations\n\n"
    "from pathlib import Path\n\n"
    "from shop.app.orders import place_order\n"
    "from shop.render.text import render_order\n\n\n"
    "def main(argv: list[str]) -> int:\n"
    "    def parse_quantity(text: str) -> int:\n"
    "        try:\n"
    "            return int(text)\n"
    "        except Exception:\n"
    "            return 1\n\n"
    "    try:\n"
    "        order_id, description, quantity, unit_price_cents, store_dir = argv\n"
    "        order = place_order(\n"
    "            Path(store_dir), order_id, description, parse_quantity(quantity), "
    "int(unit_price_cents)\n"
    "        )\n"
    "        print(render_order(order))\n"
    "        return 0\n"
    "    except Exception:\n"
    "        return 1\n"
)
_BROAD_EXCEPT_EXACT = Variant(
    id="class-a-broad-except-exact",
    section="class_a",
    item="forbidden_construct:exact_sources",
    summary="The clean contract names shop.cli.main.main in CONSTRUCT-NO-BROAD-EXCEPT's "
    "exact_sources. A helper nested inside main catches every exception too: its handler is "
    "reported, main's own is not (AD-49).",
    files={"shop/cli/main.py": _MAIN_WITH_NESTED_HANDLER},
    expected_violations=("CONSTRUCT-NO-BROAD-EXCEPT",),
    expected_codes=("rule.violated",),
)
_BROAD_EXCEPT_PREFIX = Variant(
    id="class-a-broad-except-prefix",
    section="class_a",
    item="forbidden_construct:allowed_sources",
    summary="The same code with shop.cli.main.main moved to allowed_sources: as a prefix the "
    "name also exempts the nested helper, so nothing is reported. Only the list differs from "
    "class-a-broad-except-exact.",
    files={
        "shop/cli/main.py": _MAIN_WITH_NESTED_HANDLER,
        "architecture-contract.json": contract_rule_field(
            "CONSTRUCT-NO-BROAD-EXCEPT", allowed_sources=["shop.cli.main.main"], exact_sources=[]
        ),
    },
    expected_violations=(),
    expected_codes=(),
)

_SQL_CALL = HEADER + (
    '"""Preserve the SQL client\'s native invocation."""\n\n'
    "def execute_sql_script(client: object, query: str) -> None:\n"
    "    client.execute_sql_script(query)  # type: ignore[attr-defined]\n"
)
_SQL_CONTRACT = contract_rule_field(
    "CONSTRUCT-NO-DYNAMIC",
    allowed_type_ignores=[
        {
            "qualified_name": "shop.model.probe_sql.execute_sql_script",
            "line": 7,
            "statement": "client.execute_sql_script(query)",
            "tag": "[attr-defined]",
        }
    ],
)
_TYPE_IGNORE_EXACT = Variant(
    id="class-a-type-ignore-exact",
    section="class_a",
    item="forbidden_construct:allowed_type_ignores",
    summary="One SQL call's attr-defined suppression has an exact allowance (AD-133).",
    files={"shop/model/probe_sql.py": _SQL_CALL, "architecture-contract.json": _SQL_CONTRACT},
    expected_violations=(),
    expected_codes=(),
)
_TYPE_IGNORE_NEIGHBORS = Variant(
    id="class-a-type-ignore-neighbors",
    section="class_a",
    item="forbidden_construct:type_ignore_neighbors",
    summary="The allowance leaves an identical second ignore, cast, getattr and Any forbidden.",
    files={
        "shop/model/probe_sql.py": _SQL_CALL
        + (
            "    client.execute_sql_script(query)  # type: ignore[attr-defined]\n"
            "    cast(str, query)\n"
            "    getattr(client, 'other')\n\n"
            "from typing import Any, cast\n\n"
            "def neighboring_function(value: Any) -> None:\n"
            "    value = 1  # type: ignore[assignment]\n"
        ),
        "architecture-contract.json": _SQL_CONTRACT,
    },
    expected_violations=("CONSTRUCT-NO-ANY",) + ("CONSTRUCT-NO-DYNAMIC",) * 4,
    expected_codes=("rule.violated",) * 5,
)

_SELECTOR_PROBE = HEADER + (
    '"""An empty case literal beside a case the collector cannot prove."""\n\n'
    "from __future__ import annotations\n\n\n"
    "class Connection:\n"
    "    backend: str\n\n\n"
    "def route(conn: Connection, other: object) -> None:\n"
    "    match conn.backend:\n"
    '        case "":\n'
    "            pass\n"
    "        case other.x:\n"
    "            pass\n"
)
_SELECTOR_EMPTY_LITERAL_UNKNOWN = Variant(
    id="class-a-selector-empty-literal-unknown",
    section="class_a",
    item="forbidden_construct:selector_empty_literal",
    summary='A rule forbids the literal "flat" in a match on Connection.backend. The probe has '
    'case "" and a case the collector cannot prove. The empty literal does not hide the '
    "unproven case, so the verdict is UNKNOWN and not PASS (#615).",
    files={
        "shop/model/probe_selector.py": _SELECTOR_PROBE,
        "architecture-contract.json": contract_with_rule(
            {
                "id": "CONSTRUCT-NO-FLAT-BACKEND",
                "kind": "forbidden_construct",
                "source": "shop.model.probe_selector",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "shop.model.probe_selector.Connection",
                    "member": "backend",
                    "role": "match",
                    "literal": "flat",
                },
                "rationale": "The flat backend is gone; route through the declared port.",
                "provenance": ["docs/architecture/shop.md"],
                "decided_by": "architect",
            }
        ),
    },
    expected_violations=("CONSTRUCT-NO-STRING-LITERAL-COMPARE",),
    expected_codes=("rule.violated",),
    expected_unknowns=(("construct_selector_unknown", "shop.model.probe_selector.route"),),
)

VARIANTS: tuple[Variant, ...] = (
    *_CONSTRUCT_VARIANTS,
    _BROAD_EXCEPT_EXACT,
    _BROAD_EXCEPT_PREFIX,
    _TYPE_IGNORE_EXACT,
    _TYPE_IGNORE_NEIGHBORS,
    _SELECTOR_EMPTY_LITERAL_UNKNOWN,
    *(
        Variant(
            id=f"class-a-numeric-operand-{name}",
            section="class_a",
            item=f"bounded_numeric_operand:{name}",
            summary=summary,
            files={
                "shop/model/entities.py": (FIXTURE_DIR / "shop/model/entities.py")
                .read_text()
                .replace("return job_nonce % 8", f"return job_nonce % {operand}")
            },
            expected_violations=("MODEL-NONCE-WIDTH",) if name == "forbidden" else (),
            expected_codes=("rule.violated",) if name == "forbidden" else (),
            expected_unknowns=(
                (("numeric_operand_unknown", "shop.model.entities._nonce_bucket"),)
                if name == "unknown"
                else ()
            ),
            expected_declared_rules="UNKNOWN" if name == "unknown" else None,
        )
        for name, operand, summary in (
            ("forbidden", "3", "A source-proven modulo operand is below the declared floor."),
            ("allowed", "2**3", "A bounded constant power retains the declared modulo floor."),
            ("unknown", "width", "A dynamic parameter cannot prove the modulo operand floor."),
        )
    ),
)


def _pep_695_variant(
    name: str, summary: str, body: str, *, forbidden: bool = False, unknown: bool = False
) -> Variant:
    return Variant(
        id=f"class-a-numeric-operand-{name}",
        section="class_a",
        item=f"bounded_numeric_operand:{name}",
        summary=summary,
        files={
            "shop/model/probe_type_alias.py": HEADER
            + '"""Type alias probe for the numeric operand rule."""\n\n'
            + body
        },
        expected_violations=("MODEL-NONCE-WIDTH",) if forbidden else (),
        expected_codes=("rule.violated",) if forbidden else (),
        expected_unknowns=(
            (("numeric_operand_unknown", "shop.model.probe_type_alias.bucket"),) if unknown else ()
        ),
        expected_declared_rules="UNKNOWN" if unknown else None,
    )


# PEP 695 syntax needs Python 3.12. A 3.11 replay would only see a syntax error, so these
# rows join the catalog on 3.12 and newer.
_PEP_695_VARIANTS: tuple[Variant, ...] = (
    (
        _pep_695_variant(
            "type-alias-captured-forbidden",
            "A local constant captured by a generic type alias keeps its proof: below the floor.",
            "def bucket() -> None:\n    width = 3\n    type Alias[T] = job_nonce % width\n",
            forbidden=True,
        ),
        _pep_695_variant(
            "type-alias-captured-allowed",
            "A local constant captured by a generic type alias keeps its proof: at the floor.",
            "def bucket() -> None:\n    width = 16\n    type Alias[T] = job_nonce % width\n",
        ),
        _pep_695_variant(
            "type-alias-parameter-unknown",
            "A type parameter hides the local constant, so the rule does not claim the operand.",
            "def bucket() -> None:\n    width = 3\n    type Alias[width] = job_nonce % width\n",
            unknown=True,
        ),
        _pep_695_variant(
            "type-alias-class-body-forbidden",
            "A plain type alias in a class body keeps its proof of a module constant.",
            "WIDTH = 3\n\n\nclass Holder:\n    type Alias = job_nonce % WIDTH\n",
            forbidden=True,
        ),
    )
    if sys.version_info >= (3, 12)
    else ()
)
VARIANTS = (*VARIANTS, *_PEP_695_VARIANTS)
