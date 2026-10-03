# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""What each analyzer profile can decide, as data both the analyzer and `check` read (AD-97).

The analyzer gates a contract on it (an unsupported rule or declaration is exit 2, never a
silent PASS) and `check` reads it to leave a scalar the profile never measured `null` rather
than 0. One table, so the two can never disagree about what a Dart scan saw.
"""

import sys
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

from .measurements import UnmeasurableScalar

Language: TypeAlias = Literal["python", "dart", "typescript"]
DeclarationField: TypeAlias = Literal["context_roots", "facade_budgets", "coupling_budgets"]
ObservedSection: TypeAlias = Literal[
    "symbols", "references", "bindings", "calls", "typing_signals", "constructs"
]

PYTHON_ANALYZER: Final = "archkeel-python-analyzer"
DART_ANALYZER: Final = "archkeel-dart-directives"
TYPESCRIPT_ANALYZER: Final = "archkeel-typescript-imports"


@dataclass(frozen=True, slots=True)
class Profile:
    """One analyzer's reach: every rule kind not named here is decided."""

    analyzer: str
    source_suffix: str
    unsupported_rules: frozenset[str] = frozenset()
    unsupported_declarations: frozenset[DeclarationField] = frozenset()
    unmeasured: frozenset[UnmeasurableScalar] = frozenset()
    # A section the profile never produces is null in the observation, so a claim built on it
    # reads UNKNOWN (signal missing) instead of "0 candidates".
    absent_sections: frozenset[ObservedSection] = frozenset()
    # Top-level import names `complete_external_scope` exempts as the language's own library.
    standard_library: frozenset[str] = frozenset()
    # Library names a `forbidden_dependency` target may name although no scanned module has them.
    sdk_libraries: frozenset[str] = frozenset()


PYTHON: Final = Profile(
    analyzer=PYTHON_ANALYZER,
    source_suffix=".py",
    standard_library=frozenset(sys.stdlib_module_names) | frozenset(sys.builtin_module_names),
)

DART: Final = Profile(
    analyzer=DART_ANALYZER,
    source_suffix=".dart",
    # `no_component_cycles` stays decided with `level: "module"` and `components` (AD-98): a
    # library is a module, and every directive edge a module cycle closes over is a FACT.
    unsupported_rules=frozenset({"symbol_placement", "boundary_types", "forbidden_construct"}),
    # AD-99: Dart has no `__all__` and its public names are UNKNOWN, so no facade count exists.
    unsupported_declarations=frozenset({"context_roots", "facade_budgets", "coupling_budgets"}),
    unmeasured=frozenset(
        {"typing_positions", "calls_unresolved", "private_crossings", "untyped_private_accesses"}
    ),
    absent_sections=frozenset({"symbols", "references", "bindings"}),
    # Only `dart:` URIs are the SDK; reusing Python's set would exempt `package:http` (A2).
    standard_library=frozenset({"dart"}),
    sdk_libraries=frozenset(
        f"dart.{library}"
        for library in (
            "async",
            "collection",
            "convert",
            "core",
            "developer",
            "ffi",
            "html",
            "io",
            "isolate",
            "js",
            "js_interop",
            "js_interop_unsafe",
            "js_util",
            "math",
            "mirrors",
            "typed_data",
            "ui",
            "ui_web",
            "indexed_db",
            "svg",
            "web_audio",
            "web_gl",
        )
    ),
)

TYPESCRIPT: Final = Profile(
    analyzer=TYPESCRIPT_ANALYZER,
    source_suffix=".ts",
    unsupported_rules=frozenset(
        {
            "symbol_placement",
            "boundary_types",
            "forbidden_construct",
            "forbidden_call",
            "private_access",
            "api_surface",
            "facade",
        }
    ),
    unsupported_declarations=frozenset({"facade_budgets", "coupling_budgets"}),
    unmeasured=frozenset({"typing_positions", "calls_unresolved", "private_crossings"}),
    absent_sections=frozenset(
        {"symbols", "references", "bindings", "calls", "typing_signals", "constructs"}
    ),
)

PROFILES: Final[dict[Language, Profile]] = {
    "python": PYTHON,
    "dart": DART,
    "typescript": TYPESCRIPT,
}
_ANALYZER_PROFILES: Final = {
    PYTHON_ANALYZER: PYTHON,
    DART_ANALYZER: DART,
    TYPESCRIPT_ANALYZER: TYPESCRIPT,
}


def profile_for(analyzer: str) -> Profile:
    """Return the profile for a published analyzer identity."""
    try:
        return _ANALYZER_PROFILES[analyzer]
    except KeyError as error:
        raise ValueError(f"unsupported analyzer identity: {analyzer}") from error
