# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Prove which script writes publish a global, and which alias reads or calls a site."""

from __future__ import annotations

from collections.abc import Sequence

from .syntax import ScriptAlias, ScriptGlobal, ScriptRoot, Site, SiteKind, Span, Syntax


def stable_publication(
    name: str,
    publishers: list[tuple[str, ScriptGlobal]],
    writes: Sequence[tuple[str, str | None, Span]],
) -> bool:
    return (
        len(publishers) == 1
        and publishers[0][1].stable
        and [
            (writer_rel, span)
            for writer_rel, written, span in writes
            if written is None or written == name
        ]
        == [(publishers[0][0], publishers[0][1].span)]
    )


def source_origin(
    name: str,
    publishers: list[tuple[str, ScriptGlobal]],
    writes: Sequence[tuple[str, str | None, Span]],
) -> bool:
    return (
        len(publishers) == 1
        and (publishers[0][1].stable or publishers[0][1].source_origin)
        and [(rel, span) for rel, written, span in writes if written is None or written == name]
        == [(publishers[0][0], publishers[0][1].span)]
    )


def site_aliases(syntax: Syntax, site: Site) -> tuple[ScriptAlias | None, ScriptAlias | None]:
    call = next(
        (
            alias
            for alias in syntax.script_aliases
            if (site.kind is SiteKind.CALL or alias.factory)
            # An alias of the global object itself has no name to follow (#1007).
            and ScriptRoot.unrooted(alias.path)
            and len(site.path) == 2
            and site.path[0] == alias.name
            and site.span in (*alias.calls, *alias.reads)
        ),
        None,
    )
    initializer = next(
        (
            alias
            for alias in syntax.script_aliases
            if alias.reference_span == site.span
            and (site.kind is SiteKind.REFERENCE or alias.factory)
        ),
        None,
    )
    return call, initializer
