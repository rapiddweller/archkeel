# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python TypeScript collector in the legacy mode of the native collector (AD-319).

The native collector of PR 4.2 records one import for each statement under the legacy capability.
It has no binding expansion, no script globals, no symbols, calls or references. This module runs
the Python collector with exactly those four producers switched off, so the two collectors give the
same sections. It is a temporary oracle. PR 4.3 deletes it, because the native collector then
produces the facts that the patches remove.

Run as a script, it is a collector process for `[scan].collector_argv`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from unittest import mock

from archkeel.analyzer.typescript import collect as python_collector
from archkeel.analyzer.typescript import entry
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionRequest, TypeScriptSettings

# The four producers that the native collector does not have, as methods of the Python collector.
# Each patch returns what the producer returns when it finds nothing.
_OFF: dict[str, Callable[..., object]] = {
    "_named_imports": lambda self: None,
    "_script_dependencies": lambda self: None,
    "_inner_facts": lambda self: ([], [], [], []),
    "_constructs": lambda self: (),
}


@contextmanager
def legacy_mode() -> Iterator[None]:
    with ExitStack() as stack:
        for name, replacement in _OFF.items():
            stack.enter_context(mock.patch.object(python_collector._Collection, name, replacement))
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
