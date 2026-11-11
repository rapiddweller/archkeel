# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#758, #759: class_a rows of a guarded effect that has no guard facts of its function.

A call in a class body and a bare decorator are calls without path facts. The rule is UNKNOWN,
never a proven PASS (AD-356).
"""

from __future__ import annotations

from fixtures.demo_catalog_support import HEADER, Variant

# The guard path limit that an UNKNOWN guarded row records for the seeded token function.
TOKEN_GUARD_LIMIT = (("guarded_effect_limit", "shop.app.tokens.token_for_run"),)


def _tokens(docstring: str, branch: str) -> str:
    return HEADER + (
        f'"""{docstring}"""\n\n'
        "import secrets\n\n\n"
        "def token_for_run(seeded: bool) -> str:\n"
        "    if seeded:\n"
        f"{branch}"
        '    return "fixed-token"\n'
    )


_CLASS_BODY_ALIAS = Variant(
    id="class-a-forbidden-effect-under-condition-class-body-call",
    section="class_a",
    item="forbidden_effect_under_condition:effect in a class body",
    summary="The seeded branch declares a class whose body calls secrets.token_hex through an "
    "alias. A class-body call has no path facts of its function, so the rule is UNKNOWN. "
    "Before #758 no limit applied to a call without a binding: a false proven PASS.",
    files={
        "shop/app/tokens.py": _tokens(
            "Generate tokens in a class body under the seeded branch.",
            "        class Local:\n"
            "            draw = secrets.token_hex\n"
            "            token = draw(8)\n\n"
            "        return Local.token\n",
        )
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=TOKEN_GUARD_LIMIT,
    expected_declared_rules="UNKNOWN",
)
_BARE_DECORATOR = Variant(
    id="class-a-forbidden-effect-under-condition-bare-decorator",
    section="class_a",
    item="forbidden_effect_under_condition:bare decorator is the effect",
    summary="The seeded branch decorates a local function with @secrets.token_hex. The "
    "decorator is the call secrets.token_hex(local), with no call node, so the rule is UNKNOWN. "
    "Before #759 the collector recorded no call for it: a false proven PASS.",
    files={
        "shop/app/tokens.py": _tokens(
            "Generate tokens through a decorator under the seeded branch.",
            "        @secrets.token_hex\n"
            "        def local() -> None:\n"
            "            return None\n\n"
            "        return str(local)\n",
        )
    },
    expected_violations=(),
    expected_codes=(),
    expected_unknowns=TOKEN_GUARD_LIMIT,
    expected_declared_rules="UNKNOWN",
)

VARIANTS: tuple[Variant, ...] = (_CLASS_BODY_ALIAS, _BARE_DECORATOR)
