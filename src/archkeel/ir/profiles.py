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
from enum import StrEnum
from typing import Final, Literal, TypeAlias

from .facts import Language as Language
from .facts import SourceProfile, SourceSectionName

ObservedSection: TypeAlias = SourceSectionName


class UnmeasurableScalar(StrEnum):
    PRIVATE_CROSSINGS = "private_crossings"
    TYPING_POSITIONS = "typing_positions"
    CALLS_UNRESOLVED = "calls_unresolved"
    UNTYPED_PRIVATE_ACCESSES = "untyped_private_accesses"


DeclarationField: TypeAlias = Literal["context_roots", "facade_budgets", "coupling_budgets"]


PYTHON_ANALYZER: Final = SourceProfile.PYTHON.value
DART_ANALYZER: Final = SourceProfile.DART.value
TYPESCRIPT_ANALYZER: Final = SourceProfile.TYPESCRIPT.value


@dataclass(frozen=True, slots=True)
class Profile:
    """One analyzer's reach: every rule kind not named here is decided."""

    analyzer: str
    source_suffix: str
    unsupported_rules: frozenset[str] = frozenset()
    dependency_symbols: bool = True
    complete_api_crossings: bool = True
    complete_unread_binding_inventory: bool = False
    project_import_closure: bool = False
    unsupported_declarations: frozenset[DeclarationField] = frozenset()
    unmeasured: frozenset[UnmeasurableScalar] = frozenset()
    # A section the profile never produces is null in the observation, so a claim built on it
    # reads UNKNOWN (signal missing) instead of "0 candidates".
    absent_sections: frozenset[ObservedSection] = frozenset()
    # Each group's sections are one atomic receipt: all null or all arrays. Different groups
    # may be measured independently, retaining compatibility with older observations.
    optional_section_groups: tuple[frozenset[ObservedSection], ...] = ()
    # Top-level import names `complete_external_scope` exempts as the language's own library.
    standard_library: frozenset[str] = frozenset()
    # Library names a `forbidden_dependency` target may name although no scanned module has them.
    sdk_libraries: frozenset[str] = frozenset()
    # Exact caller/target grants may permit Python module-object imports.
    module_object_imports: bool = False

    @property
    def optional_sections(self) -> frozenset[ObservedSection]:
        """The existing optional-section API, derived from the owned receipt groups."""
        return frozenset(section for group in self.optional_section_groups for section in group)


PYTHON: Final = Profile(
    analyzer=PYTHON_ANALYZER,
    module_object_imports=True,
    source_suffix=".py",
    complete_unread_binding_inventory=True,
    standard_library=frozenset(sys.stdlib_module_names) | frozenset(sys.builtin_module_names),
)

DART: Final = Profile(
    analyzer=DART_ANALYZER,
    complete_api_crossings=False,
    source_suffix=".dart",
    # `no_component_cycles` stays decided with `level: "module"` and `components` (AD-98): a
    # library is a module, and every directive edge a module cycle closes over is a FACT.
    unsupported_rules=frozenset({"symbol_placement", "boundary_types"}),
    # AD-99: Dart has no `__all__` and its public names are UNKNOWN, so no facade count exists.
    unsupported_declarations=frozenset({"context_roots", "facade_budgets", "coupling_budgets"}),
    unmeasured=frozenset(
        {
            UnmeasurableScalar.TYPING_POSITIONS,
            UnmeasurableScalar.CALLS_UNRESOLVED,
            UnmeasurableScalar.PRIVATE_CROSSINGS,
            UnmeasurableScalar.UNTYPED_PRIVATE_ACCESSES,
        }
    ),
    absent_sections=frozenset({ObservedSection.TYPING_SIGNALS, ObservedSection.CONSTRUCTS}),
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
    dependency_symbols=False,
    complete_api_crossings=False,
    project_import_closure=True,
    unsupported_rules=frozenset(
        {
            "symbol_placement",
            "boundary_types",
        }
    ),
    unsupported_declarations=frozenset({"context_roots", "facade_budgets", "coupling_budgets"}),
    unmeasured=frozenset(
        {
            UnmeasurableScalar.TYPING_POSITIONS,
            UnmeasurableScalar.CALLS_UNRESOLVED,
            UnmeasurableScalar.PRIVATE_CROSSINGS,
            UnmeasurableScalar.UNTYPED_PRIVATE_ACCESSES,
        }
    ),
    absent_sections=frozenset({ObservedSection.TYPING_SIGNALS}),
    optional_section_groups=(
        frozenset(
            {
                ObservedSection.SYMBOLS,
                ObservedSection.REFERENCES,
                ObservedSection.BINDINGS,
                ObservedSection.CALLS,
            }
        ),
        frozenset({ObservedSection.CONSTRUCTS}),
    ),
)

PROFILES: Final[dict[Language, Profile]] = {
    Language.PYTHON: PYTHON,
    Language.DART: DART,
    Language.TYPESCRIPT: TYPESCRIPT,
}
_ANALYZER_PROFILES: Final = {
    SourceProfile.PYTHON: PYTHON,
    SourceProfile.DART: DART,
    SourceProfile.TYPESCRIPT: TYPESCRIPT,
}


def profile_for(analyzer: str) -> Profile:
    """Return the profile for a published analyzer identity."""
    try:
        return _ANALYZER_PROFILES[SourceProfile(analyzer)]
    except (KeyError, ValueError) as error:
        raise ValueError(f"unsupported analyzer identity: {analyzer}") from error


def delta_dimension_applicable(profile: Profile, dimension: str) -> bool:
    """Whether the profile provides complete evidence for this historical dimension."""
    if dimension == "api_crossings":
        return profile.complete_api_crossings
    if dimension == UnmeasurableScalar.PRIVATE_CROSSINGS:
        return UnmeasurableScalar.PRIVATE_CROSSINGS not in profile.unmeasured
    if dimension == ObservedSection.TYPING_SIGNALS:
        return UnmeasurableScalar.TYPING_POSITIONS not in profile.unmeasured
    return True
