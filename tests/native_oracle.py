# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python TypeScript collector as the native one is: the 4.2 gap for script facts (AD-340).

The native collector produces every section of the inner-UML capability: imports with their bound
names, symbols, calls, references, bindings and constructs. It does not analyse script globals
yet (PR 4.3a-4 and 4.3a-5). This module runs the unmodified Python collector with one producer
replaced, `_script_dependencies`, which reports the same gap as the native collector for each file
that can use a browser global, and the feature `script-globals-v1` removed from its capability
(the native collector does not declare it). Everything else is the Python code. It is a temporary
oracle: PR 4.3a-5 deletes it.

Run as a script, it is a collector process for `[scan].collector_argv`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from unittest import mock

from archkeel.analyzer.typescript import collect as python_collector
from archkeel.analyzer.typescript import entry
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionRequest, TypeScriptSettings

# The reason that the native collector gives for each file that can use a browser global.
GLOBALS_UNEXAMINED = "Script-global dependencies are not examined by the native collector"


def _globals_unexamined(self: python_collector._Collection) -> None:
    """What `_script_dependencies` does in the legacy mode: the same gap as the native collector."""
    evidence = {file.rel_path: file.evidence_id for file in self.files}
    for rel in self.syntax:
        if self._global_dependency_scope(rel):
            self._gap(
                GLOBALS_UNEXAMINED,
                (evidence[rel],),
                self.modules[rel],
                kind=python_collector._GapKind.RESOLUTION,
            )


# The producer that the native collector does not have yet, as a method of the Python collector.
# It reports that it examined nothing.
_OFF: dict[str, Callable[..., object]] = {"_script_dependencies": _globals_unexamined}
SCRIPT_GLOBALS = "script-globals-v1"
_FACTS = python_collector._Collection.facts


def _without_script_globals(self: python_collector._Collection) -> SourceFacts:
    """`facts` of Python, with the feature that only the script analysis earns removed."""
    facts = _FACTS(self)
    kept = tuple(item for item in facts.capabilities.resolution_features if item != SCRIPT_GLOBALS)
    capabilities = replace(facts.capabilities, resolution_features=kept)
    return replace(facts, capabilities=capabilities)


@contextmanager
def legacy_mode() -> Iterator[None]:
    with ExitStack() as stack:
        for name, replacement in _OFF.items():
            stack.enter_context(mock.patch.object(python_collector._Collection, name, replacement))
        stack.enter_context(
            mock.patch.object(python_collector._Collection, "facts", _without_script_globals)
        )
        yield


def legacy_facts(request: CollectionRequest) -> tuple[SourceFacts, tuple[str, ...]]:
    """The facts, and the files that the Python collector read as global scripts.

    A global script gets script gaps that the native collector cannot give. The oracle does not
    hide them: a test fails when a tree holds such a file.
    """
    settings = request.resolver
    assert isinstance(settings, TypeScriptSettings)
    with legacy_mode():
        collection = python_collector._Collection(request, settings)
        facts = collection.facts()
    scripts = tuple(sorted(rel for rel, syntax in collection.syntax.items() if syntax.script_mode))
    return facts, scripts


if __name__ == "__main__":
    with legacy_mode():
        raise SystemExit(entry.main())
