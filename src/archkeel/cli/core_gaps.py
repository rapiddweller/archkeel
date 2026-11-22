# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The text of the gaps of a scan (#1614, #1615): grouped by cause, with a count and one example.

A kind of gap can have several causes. The title of a group never takes the example of its first
gap; the three largest causes come first, then the count of the rest.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

from .core_evidence import CollectionGap
from .core_frame import CoreFrame
from .core_trojan_horses import DECLARED, declared
from .core_words import NOT_FOUND_PREFIX, kind_label, plain

SHOWN = 3


def rest(total: int, shown: int, show_all: bool) -> str:
    """The words for what a list leaves out: nothing when all are shown."""
    return "" if show_all or total <= shown else f" and {total - shown} more (--all lists them)"


def places(frame: CoreFrame, evidence: Sequence[str], limit: int) -> list[str]:
    """The `path:line` of the first places of a piece of evidence."""
    return [
        f"{location.path}:{location.line}" if location.line else location.path
        for key in evidence
        if (location := frame.locations.get(key))
    ][:limit]


_UNRESOLVED: Final = "Unresolved module: "
_NAMESSHOWN = 5


def _package_of(specifier: str) -> str | None:
    """The package that a bare import names (`react`, `@scope/pkg`); `None` for a path."""
    if not specifier or specifier[0] in "./~#" or ":" in specifier:
        return None
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def not_installed_lines(frame: CoreFrame) -> list[str]:
    """#1615: one line for the imports of packages that the scan did not find installed."""
    counts: Counter[str] = Counter()
    for gap in frame.collection_gaps:
        if gap.reason.startswith(_UNRESOLVED) and (
            package := _package_of(gap.reason.removeprefix(_UNRESOLVED))
        ):
            counts[package] += 1
    if not counts:
        return []
    names = [name for name, _ in counts.most_common(_NAMESSHOWN)]
    rest = len(counts) - len(names)
    listed = ", ".join(names) + (f" and {rest} more" if rest else "")
    return [
        f"  {sum(counts.values())} imports point to packages that could not be found "
        f"(most likely not installed): {listed}",
        "      Fix: if they are not installed, install them (your package manager) and run again; "
        "or leave out the files that import them.",
    ]


_NOT_FOUND_LABEL = "an imported module that has no file in the scan"


def _missing(gap: CollectionGap) -> str | None:
    """The module name of a gap `project_module_not_found: NAME`, or `None`."""
    return (
        gap.reason.removeprefix(NOT_FOUND_PREFIX)
        if gap.reason.startswith(NOT_FOUND_PREFIX)
        else None
    )


def group_lines(
    frame: CoreFrame, show_all: bool, ignored: Mapping[str, str] | None = None
) -> tuple[list[str], list[tuple[str, int]]]:
    """The source gaps grouped by cause, the largest group first, and the ranking.

    A module that is imported and has no file is its own group: the line says whether a Git ignore
    rule covers the file (the usual case of a generated module) and what to do.
    """
    groups: dict[str, list[int]] = {}
    for index, gap in enumerate(frame.collection_gaps):
        lines_of = [place.line for e in gap.evidence if (place := frame.locations.get(e))]
        if declared(gap.subjects, lines_of, frame.trojan_horses):
            key = kind_label(DECLARED)
        else:
            key = _NOT_FOUND_LABEL if _missing(gap) is not None else kind_label(gap.kind)
        groups.setdefault(key, []).append(index)
    ranked = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    lines: list[str] = []
    jobs: list[tuple[str, int]] = []
    for label, members in ranked:
        causes = _causes(frame, members) if label not in _PLAIN_LABELS else {label: members}
        if len(causes) > 1:
            lines.extend(_cause_lines(frame, label, members, causes, show_all))
            if label != kind_label(DECLARED):
                jobs.extend((cause, len(rows)) for cause, rows in causes.items())
            continue
        first = frame.collection_gaps[members[0]]
        lead = "" if label == _NOT_FOUND_LABEL else f": {plain(first.reason)}"
        lines.append(f"  {len(members)} x {label}{lead}")
        lines.extend(_member_lines(frame, members, show_all, ignored))
        if label == _NOT_FOUND_LABEL:
            lines.append(
                "      Fix: generate or build the module before the scan, or leave out the files "
                "that import it."
            )
        if label != kind_label(DECLARED):
            jobs.append((label, len(members)))
    return lines, jobs


_PLAIN_LABELS = frozenset({_NOT_FOUND_LABEL})


def _cause(gap: CollectionGap) -> str:
    """The cause of a gap: its reason up to the first colon (the part that names the variable
    thing, such as the module or the alias, follows the colon)."""
    return plain(gap.reason).split(": ", 1)[0]


def _causes(frame: CoreFrame, members: Sequence[int]) -> dict[str, list[int]]:
    """The members of one kind of gap by cause, the largest cause first."""
    found: dict[str, list[int]] = {}
    for index in members:
        found.setdefault(_cause(frame.collection_gaps[index]), []).append(index)
    return dict(sorted(found.items(), key=lambda item: (-len(item[1]), item[0])))


def _member_lines(
    frame: CoreFrame, members: Sequence[int], show_all: bool, ignored: Mapping[str, str] | None
) -> list[str]:
    """The places of the members of one group: three, or all with `--all`."""
    lines = []
    for index in members if show_all else members[:SHOWN]:
        gap = frame.collection_gaps[index]
        where = ", ".join(places(frame, gap.evidence, 1)) or ", ".join(gap.subjects[:1])
        name = _missing(gap)
        note = _generated(name, ignored or {}) if name is not None else ""
        tail = f" ({plain(gap.detail)})" if gap.detail else ""
        lines.append(f"      {where}{': ' + name if name else ''}{note}{tail}")
    if more := rest(len(members), SHOWN, show_all):
        lines.append(f"      {more.strip()}")
    return lines


def _cause_lines(
    frame: CoreFrame,
    label: str,
    members: Sequence[int],
    causes: Mapping[str, Sequence[int]],
    show_all: bool,
) -> list[str]:
    """One kind of gap with several causes: the count of each cause and one example each.

    The three largest causes come first, then `and N more causes`; `--all` lists every cause with
    every place.
    """
    lines = [f"  {len(members)} x {label}, in {len(causes)} causes:"]
    shown = list(causes.items()) if show_all else list(causes.items())[:SHOWN]
    for cause, rows in shown:
        gap = frame.collection_gaps[rows[0]]
        where = ", ".join(places(frame, gap.evidence, 1)) or ", ".join(gap.subjects[:1])
        lines.append(f"      {len(rows)} x {cause}")
        if show_all:
            lines.extend(f"      {line}" for line in _member_lines(frame, rows, True, None))
        else:
            example = plain(gap.reason)
            lines.append(f"          e.g. {example} ({where})")
    if hidden := len(causes) - len(shown):
        lines.append(
            f"      and {hidden} more {'cause' if hidden == 1 else 'causes'} (--all lists them)"
        )
    return lines


def _generated(name: str, ignored: Mapping[str, str]) -> str:
    """What a Git ignore rule says about the missing module, or what to check without one."""
    rule = ignored.get(name)
    if rule is None:
        return " (no file; it may be generated, or the import is wrong)"
    return f" (no file; the ignore rule {rule} covers it, so it is probably generated)"
