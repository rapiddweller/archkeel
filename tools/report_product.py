# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The facts of one self run that the product page shows (AD-462).

The page decides nothing. `part_of` copies counts, names and states out of one CLI envelope: the
rule rows, `topology`, `explain.cycles`, `details` and `collection_gaps`. A fact that the frame
does not hold is left out and never read from the source. The numbering of the violated places
follows the page of the part report (`#x1`, `#x2`, ...). The page keeps a link only when the report
that the CLI wrote holds that id.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

STATUSES = ("PASS", "FAIL", "UNKNOWN")
# The most places the part report shows; a longer list is cut there (AD-496).
MAX_PLACES = 100
# A state with more components than this is a count on the card, not a row of names.
NAMED_LIMIT = 8
# The most exceptions that one verdict block lists.
LISTED_LIMIT = 8
DIGEST_SHOWN = 16


@dataclass(frozen=True)
class Place:
    """One violated place of the part report: an import or a cycle."""

    number: int
    text: str
    rules: int
    components: tuple[str, ...]


@dataclass(frozen=True)
class Tile:
    """A named component with an exception, or a count of the rest."""

    label: str
    state: str  # FAIL, UNKNOWN or "" (no exception)
    place: int | None = None  # the first violated place of a FAIL component
    count: bool = False


@dataclass(frozen=True)
class Part:
    """One run of the product: its verdict, its components and its exceptions."""

    key: str
    title: str
    language: str
    subject: str
    report: str
    status: str = ""
    error: str = ""
    refusal: str = ""
    counts: Mapping[str, int] = field(default_factory=dict)
    components: int = 0
    modules: int = 0
    failing: int = 0
    unknown: int = 0
    tiles: tuple[Tile, ...] = ()
    places: tuple[Place, ...] = ()
    places_total: int = 0
    gaps: int = 0
    engine: str = ""
    contract: str = ""
    binary: str = ""

    @property
    def decided(self) -> bool:
        return bool(self.status) and not self.refusal and not self.error


def _places(
    frame: Mapping[str, Any], owner: Mapping[str, str], names: Mapping[str, str]
) -> tuple[list[Place], int]:
    """The violated places of the part report (imports, then cycles) and their total."""
    cycles = frame.get("explain", {}).get("cycles", {})
    imports: dict[tuple[str, bool, str], int] = {}
    paths: list[dict[str, Any]] = []
    for rule, rows in frame.get("details", {}).items():
        listed = {item["index"]: item for item in cycles.get(rule, {}).get("items", [])}
        for index, row in enumerate(rows):
            if row["cause"] == "dependency cycle" and index in listed:
                paths.append(listed[index])
                continue
            target = row.get("target")
            key = (row["source"], target is not None, target or "")
            imports[key] = imports.get(key, 0) + 1
    found: list[tuple[str, int, tuple[str, ...]]] = []
    for (source, has_target, target), rules in sorted(imports.items()):
        home, goal = owner.get(source), owner.get(target)
        label = names.get(home or "", source)
        if has_target:
            text = f"{label} imports {names.get(goal or '', target)}"
        else:
            text = f"{label} has a finding"
        found.append((text, rules, (home,) if home else ()))
    for path in paths:
        ids = [
            step.get(side) for step in path["path"] for side in ("from_component", "to_component")
        ]
        members = tuple(dict.fromkeys(item for item in ids if item))
        where = names.get(members[0], members[0]) if members else "the contract"
        found.append((f"Cycle of {len(path['members'])} modules in {where}", 1, members))
    shown = [
        Place(number, text, rules, members)
        for number, (text, rules, members) in enumerate(found[:MAX_PLACES], 1)
    ]
    return shown, len(found)


def _tiles(
    order: Sequence[str], names: Mapping[str, str], failing: Mapping[str, int], unknown: set[str]
) -> tuple[Tile, ...]:
    """Named tiles for FAIL and UNKNOWN components; a large state becomes one count tile."""
    states = {
        cid: "FAIL" if cid in failing else "UNKNOWN" if cid in unknown else "" for cid in order
    }
    totals = Counter(states.values())
    tiles: list[Tile] = []
    words = {"FAIL": "with a violation", "UNKNOWN": "with gaps", "": "without an exception"}
    for state in ("FAIL", "UNKNOWN"):
        if totals[state] > NAMED_LIMIT:
            tiles.append(Tile(f"{totals[state]} {words[state]}", state, count=True))
        else:
            tiles += [
                Tile(names[cid], state, failing.get(cid)) for cid in order if states[cid] == state
            ]
    if totals[""]:
        tiles.append(Tile(f"{totals['']} {words['']}", "", count=True))
    return tuple(tiles)


def part_of(
    envelope: Mapping[str, Any] | None,
    entry: Mapping[str, str],
    report: str,
    error: str = "",
) -> Part:
    """The part for one self run. A run without an envelope gets a part that shows the error."""
    base: dict[str, Any] = {
        "key": entry["name"],
        "title": entry["part"],
        "language": entry["language"],
        "subject": entry["title"],
        "report": report,
    }
    if envelope is None:
        return Part(**base, error=error or "no envelope")
    frame = envelope.get("frame") or {}
    refusal = (envelope.get("refusal") or {}).get("message", "")
    if refusal:
        return Part(**base, status=envelope["status"], refusal=refusal)
    topology = frame.get("topology") or {}
    names = {c["id"]: c["name"] for c in topology.get("components", [])}
    owner = {m["name"]: m["component"] for m in topology.get("modules", [])}
    counts = Counter(row[1] for row in frame.get("rules", {}).values())
    places, total = _places(frame, owner, names)
    failing: dict[str, int] = {}
    for place in places:
        for cid in place.components:
            failing.setdefault(cid, place.number)
    unknown = {
        owner[subject]
        for gap in frame.get("collection_gaps", [])
        for subject in gap.get("subjects", [])
        if subject in owner
    } - set(failing)
    order = [cid for cid in names if cid in failing or cid in unknown] + [
        cid for cid in names if cid not in failing and cid not in unknown
    ]
    engine = str(frame.get("engine", ""))
    return Part(
        **base,
        status=envelope["status"],
        counts={name: counts.get(name, 0) for name in STATUSES},
        components=len(names),
        modules=int(topology.get("total", {}).get("modules", len(owner))),
        failing=len(failing),
        unknown=len(unknown),
        tiles=_tiles(order, names, failing, unknown) if names else (),
        places=tuple(places),
        places_total=total,
        gaps=len(frame.get("collection_gaps", [])),
        engine=engine.split()[-1][:DIGEST_SHOWN] if engine else "",
        contract=str(frame.get("contract_digest", ""))[:DIGEST_SHOWN],
        binary=engine.split()[0] if engine else "",
    )


def worst(parts: Sequence[Part]) -> str:
    """The worst status among the parts. It is a heading word, not a joint verdict."""
    seen = {part.status for part in parts if part.decided}
    return next((s for s in ("FAIL", "UNKNOWN", "PASS") if s in seen), "UNKNOWN")
