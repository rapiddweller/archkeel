# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The plants of the proof review of AD-512 and the counts of their rows (parts A and B).

Each plant gives the files, the UML target, the row of release 4.0.1 and the row of the core.
"""

from __future__ import annotations

from test_cli_core_uml_compare import ONE, module
from uml_symbol_plants import (
    FILES,
    RELATIONSHIPS,
    edge,
    edit,
    foreign,
    more,
    param,
    signature,
    sym,
    target,
)
from uml_symbol_sources import (
    AMBIENT,
    ARROW,
    CATCH,
    CTOR,
    DECORATED,
    DROPPING,
    DYNAMIC,
    HASH,
    HIDDEN,
    LOCAL_BASE,
    LOCAL_CLASS,
    LOCAL_FUNCTION,
    LOCAL_INTERFACE,
    LOCAL_METHOD,
    LOOSE,
    MERGED,
    MIXIN,
    NAMESPACE,
    NAMESPACE_IMPORT,
    OTHER,
    PARAMETER,
    REBOUND,
    RENAMED,
    REQUIRED,
    TYPE_IMPORT,
    TYPE_PARAMETER,
)

REVIEW_PLANTS: dict[str, tuple[dict[str, str], dict, str, str]] = {
    # B-1: a name that a scope below the module declares is not the module symbol. 4.0.1 gives
    # PASS for each of these plants (wrong); the core gives UNKNOWN.
    "local-function-shadow": (
        edit("export type Text", LOCAL_FUNCTION + "export type Text"),
        more(
            sym("go", "function", "go", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "go", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-method-shadow": (
        edit("export type Text", LOCAL_METHOD + "export type Text"),
        more(
            sym("holder", "class", "Holder"),
            sym("hold", "method", "Holder.hold", "holder", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "hold", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "catch-binding-shadow": (
        edit("export type Text", CATCH + "export type Text"),
        more(
            sym("guard", "function", "guard", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("calls", "guard", "helper")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-class-creates-shadow": (
        edit("export type Text", LOCAL_CLASS + "export type Text"),
        more(
            sym("make", "function", "make", signature=signature("void")),
            sym("made", "binding", "make.made", "make", visibility=None),
            relationships=[
                *RELATIONSHIPS,
                edge("creates", "make", "unit"),
                edge("instance_of", "made", "unit"),
            ],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "type-parameter-shadow": (
        edit("export type Text", TYPE_PARAMETER + "export type Text"),
        more(
            sym("gen", "function", "gen", signature=signature("Unit", param("x", "Unit"))),
            relationships=[*RELATIONSHIPS, edge("references", "gen", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-interface-shadow": (
        edit("export type Text", LOCAL_INTERFACE + "export type Text"),
        more(
            sym("use-port", "function", "usePort", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("references", "use-port", "port")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "local-base-shadow": (
        edit("export type Text", LOCAL_BASE + "export type Text"),
        more(
            sym("derived", "class", "derive.Derived", "derive"),
            sym("derive", "function", "derive", signature=signature("void")),
            relationships=[*RELATIONSHIPS, edge("inherits", "derived", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    # Controls: 4.0.1 and the core give UNKNOWN already.
    "local-arrow-control": (
        edit("export type Text", ARROW + "export type Text"),
        more(
            sym("arrow", "function", "arrow", signature=signature("number")),
            relationships=[*RELATIONSHIPS, edge("calls", "arrow", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "parameter-control": (
        edit("export type Text", PARAMETER + "export type Text"),
        more(
            sym("take", "function", "take", signature=signature("number", param("helper", "any"))),
            relationships=[*RELATIONSHIPS, edge("calls", "take", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    # B-2: a variable that is written twice or typed any or unknown is not proven.
    "rebound-binding": (
        edit("export type Text", REBOUND + "export type Text"),
        more(
            sym("swap", "function", "swap", signature=signature("void")),
            sym("swapped", "binding", "swap.swapped", "swap", visibility=None),
            relationships=[*RELATIONSHIPS, edge("instance_of", "swapped", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    "any-binding": (
        edit("export type Text", LOOSE + "export type Text"),
        more(
            sym("loose", "function", "loose", signature=signature("void")),
            sym("held", "binding", "loose.held", "loose", visibility=None),
            relationships=[*RELATIONSHIPS, edge("instance_of", "held", "unit")],
        ),
        "PASS",
        "UNKNOWN",
    ),
    # Part A: planned class members that the class lacks are FAIL in 4.0.1 and UNKNOWN in the core.
    "mixin-base-receipt": (
        edit("export type Text", MIXIN + "export type Text"),
        more(
            sym("mx", "class", "Mx"),
            relationships=[*RELATIONSHIPS, edge("realizes", "mx", "port")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "member-plain-constructor-parameter": (
        edit("export type Text", CTOR + "export type Text"),
        more(sym("pp", "class", "PP"), sym("pp-z", "attribute", "PP.z", "pp")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-hash-private": (
        edit("export type Text", HASH + "export type Text"),
        more(sym("pv", "class", "Pv"), sym("pv-x", "attribute", "Pv.x", "pv")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-enum-literal-gone": (
        FILES,
        more(sym("gone", "enum_literal", "State.GONE", "state")),
        "FAIL",
        "UNKNOWN",
    ),
    "member-decorator-made": (
        edit("export type Text", DECORATED + "export type Text"),
        more(
            sym("dec", "class", "Dec"),
            sym("dec-gen", "method", "Dec.gen", "dec", signature=signature("void")),
        ),
        "FAIL",
        "UNKNOWN",
    ),
    "member-namespace-merge": (
        edit("export type Text", MERGED + "export type Text"),
        more(
            sym("nm", "class", "Nm"),
            sym("nm-f", "method", "Nm.f", "nm", signature=signature("void")),
        ),
        "FAIL",
        "UNKNOWN",
    ),
    # Part A: a symbol of an ambient module or a namespace is no module-level symbol of the file.
    "ambient-module-class": (
        edit("export type Text", AMBIENT + "export type Text"),
        more(
            sym("amb", "class", "Amb"),
            sym("amb-z", "attribute", "Amb.z", "amb", annotation="number"),
        ),
        "PASS",
        "UNKNOWN",
    ),
    "namespace-member-constant": (
        edit("export type Text", NAMESPACE + "export type Text"),
        more(sym("k", "constant", "k")),
        "PASS",
        "UNKNOWN",
    ),
    # Not run by the reviewers: each form must not give PASS without proof.
    "dynamic-import": (
        {**edit("export type Text", DYNAMIC + "export type Text"), **OTHER},
        more(
            sym("dyn", "function", "dyn", signature=signature("Promise<void>")),
            foreign("tfn", "tfn"),
            relationships=[*RELATIONSHIPS, edge("calls", "dyn", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "namespace-import-call": (
        {**edit("export type Text", NAMESPACE_IMPORT + "export type Text"), **OTHER},
        more(
            sym("via-ns", "function", "viaNs", signature=signature("void")),
            foreign("tfn", "tfn"),
            relationships=[*RELATIONSHIPS, edge("calls", "via-ns", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "type-import-reference": (
        {**edit("export type Text", TYPE_IMPORT + "export type Text"), **OTHER},
        more(
            sym(
                "use-type", "function", "useType", signature=signature("void", param("x", "Alias"))
            ),
            foreign("alias", "Alias", "type_alias"),
            relationships=[*RELATIONSHIPS, edge("references", "use-type", "alias")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "renamed-reexport-call": (
        {**edit("export type Text", RENAMED + "export type Text"), **OTHER},
        more(
            sym("via-shown", "function", "viaShown", signature=signature("void")),
            foreign("shown", "shown"),
            relationships=[*RELATIONSHIPS, edge("calls", "via-shown", "shown")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "require-in-cts": (
        {**OTHER, "src/a/c.cts": REQUIRED},
        target(
            [
                module("c", ONE.replace("one_x2e_ts", "c_x2e_cts")),
                sym("via-require", "function", "viaRequire", signature=signature("void"))
                | {
                    "qualified_name": ONE.replace("one_x2e_ts", "c_x2e_cts") + ".viaRequire",
                    "parent_id": "c",
                },
                foreign("tfn", "tfn"),
            ],
            relationships=[edge("calls", "via-require", "tfn")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "site-in-dropped-file": (
        {
            **FILES,
            "src/a/hidden.ts": HIDDEN,
            "tsconfig.json": DROPPING,
        },
        more(
            sym("hid", "function", "hid", signature=signature("void"))
            | {
                "qualified_name": ONE.replace("one_x2e_ts", "hidden_x2e_ts") + ".hid",
                "parent_id": "one",
            },
            relationships=[*RELATIONSHIPS, edge("calls", "hid", "helper")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
}

REVIEW_CAUSES: dict[str, str | tuple[str, ...]] = {
    "local-function-shadow": "unresolved calls site",
    "local-method-shadow": "unresolved calls site",
    "catch-binding-shadow": "unresolved calls site",
    "local-class-creates-shadow": "unresolved creates site",
    "type-parameter-shadow": "unresolved references site",
    "local-interface-shadow": "unresolved references site",
    "local-base-shadow": "unresolved inherits site",
    "local-arrow-control": "unresolved calls site",
    "parameter-control": "unresolved calls site",
    "rebound-binding": "absent symbol",
    "any-binding": "absent symbol",
    "mixin-base-receipt": "realizes inventory is not complete",
    "member-plain-constructor-parameter": "absent symbol",
    "member-hash-private": "absent symbol",
    "member-enum-literal-gone": "absent symbol",
    "member-decorator-made": "absent symbol",
    "member-namespace-merge": "absent symbol",
    "ambient-module-class": "absent symbol",
    "namespace-member-constant": "absent symbol",
    "dynamic-import": "unresolved calls site",
    "namespace-import-call": "unresolved calls site",
    "type-import-reference": "absent symbol",
    "renamed-reexport-call": "absent symbol",
    "require-in-cts": "unresolved calls site",
    "site-in-dropped-file": "absent symbol",
}


# The core PASS needs resolved definitions and a complete scope. Where 4.0.1 passes on partial
# coverage, the core stays UNKNOWN (AD-512 lists the forms). Any other difference is a bug.
# (equal, PASS to UNKNOWN, FAIL to UNKNOWN, all plants)
COUNTS = (44, 12, 5, 61)
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# Plants where the 4.0.1 PASS is wrong: the drawn relationship or symbol is absent in the code.
# The core gives UNKNOWN for them, so they are no limit of the core (AD-512).
WRONG_RELEASE_PASS = {
    "local-function-shadow",
    "local-method-shadow",
    "catch-binding-shadow",
    "local-class-creates-shadow",
    "type-parameter-shadow",
    "local-interface-shadow",
    "local-base-shadow",
    "rebound-binding",
    "any-binding",
    "ambient-module-class",
    "namespace-member-constant",
}
