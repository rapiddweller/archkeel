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
from collections.abc import Iterable, Mapping, Sequence
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
# A part with at most this many components shows each one by name, also without an exception.
ALL_NAMED_LIMIT = 12


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
    commit: str = ""
    core: str = ""

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
    if len(order) <= ALL_NAMED_LIMIT:
        rank = {"FAIL": 0, "UNKNOWN": 1, "": 2}
        ranked = sorted(order, key=lambda cid: rank[states[cid]])
        return tuple(Tile(names[cid], states[cid], failing.get(cid)) for cid in ranked)
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


EXIT_STATUS = {0: "PASS", 1: "FAIL", 2: "UNKNOWN"}


@dataclass(frozen=True)
class Judged:
    """What the join trusts of one envelope: the weakest of its word, rows and exit code."""

    status: str
    counts: Mapping[str, int]
    commit: str = ""
    core: str = ""


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def judge(envelope: object) -> Judged | None:
    """The status, counts, commit and core of an envelope, or None when it holds no status.

    The word `status` is a claim. A rule row that FAILs or is UNKNOWN, or an exit code that says
    FAIL or UNKNOWN, makes the status weaker than PASS. Any other exit code is UNKNOWN. Anything
    that is not a mapping, and a status that is no word of the verdict, gives None.
    """
    if not isinstance(envelope, Mapping):
        return None
    word = envelope.get("status")
    if not isinstance(word, str) or word.upper() not in ORDER:
        return None
    frame = _mapping(envelope.get("frame"))
    rows = [row[1] for row in _mapping(frame.get("rules")).values() if _row_ok(row)]
    counts = Counter(str(row).upper() for row in rows)
    seen = [word.upper(), *(name for name in ORDER if counts.get(name))]
    if "exit_code" in envelope:
        code = envelope["exit_code"]
        seen.append(EXIT_STATUS.get(code, "UNKNOWN") if isinstance(code, int) else "UNKNOWN")
    head = _mapping(_mapping(_mapping(frame.get("self_test")).get("collect")).get("request"))
    commit = _mapping(head.get("snapshot")).get("git_head")
    core = frame.get("engine")
    return Judged(
        weakest(seen),
        {name: counts.get(name, 0) for name in STATUSES},
        commit if isinstance(commit, str) else "",
        core if isinstance(core, str) else "",
    )


def _row_ok(row: object) -> bool:
    return isinstance(row, Sequence) and not isinstance(row, str) and len(row) >= 2


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
    judged = judge(envelope)
    if envelope is None or judged is None:
        return Part(**base, error=error or "no result: the envelope holds no status")
    frame = _mapping(envelope.get("frame"))
    refusal = _mapping(envelope.get("refusal")).get("message", "")
    if refusal:
        return Part(**base, status=judged.status, refusal=str(refusal))
    topology = frame.get("topology") or {}
    names = {c["id"]: c["name"] for c in topology.get("components", [])}
    owner = {m["name"]: m["component"] for m in topology.get("modules", [])}
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
        status=judged.status,
        counts=dict(judged.counts),
        commit=judged.commit,
        core=judged.core,
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


@dataclass(frozen=True)
class Contract:
    """One run of an own contract of ArchKeel: one line with its verdict and its rule counts."""

    title: str
    status: str = ""
    counts: Mapping[str, int] = field(default_factory=dict)
    error: str = ""
    commit: str = ""
    core: str = ""

    @property
    def decided(self) -> bool:
        return bool(self.status) and not self.error


def contract_of(envelope: object, title: str, error: str = "") -> Contract:
    """The line of a contract run. A run without a valid result or with a refusal has no counts."""
    judged = judge(envelope)
    if judged is None:
        return Contract(title, error=error or "no result: the envelope holds no status")
    if _mapping(_mapping(envelope).get("refusal")):
        return Contract(title, error="refused")
    return Contract(title, judged.status, judged.counts, "", judged.commit, judged.core)


# ArchKeel as one system. One scan has one profile, so each part is one run (AD-478); the verdict
# of the system is the weakest verdict of its parts. Interim: this ordering is the only one outside
# the core, and it is deleted with the system contract (AD-522), where the core joins the parts.
ORDER = ("FAIL", "UNKNOWN", "PASS")


def weakest(statuses: Iterable[str]) -> str:
    """FAIL before UNKNOWN before PASS. An unknown word, or no part at all, is UNKNOWN."""
    seen = {status if status in ORDER else "UNKNOWN" for status in statuses} or {"UNKNOWN"}
    return next(status for status in ORDER if status in seen)


def summed(counts: Iterable[Mapping[str, int]]) -> dict[str, int]:
    """The rule counts of the parts added up, by PASS, FAIL and UNKNOWN."""
    rows = list(counts)
    return {name: sum(row.get(name, 0) for row in rows) for name in STATUSES}


@dataclass(frozen=True)
class Verdict:
    """The verdict of the system: the weakest status, the counts added up and the cause, if any."""

    status: str
    counts: Mapping[str, int]
    cause: str = ""


def system(items: Sequence[Part | Contract]) -> Verdict:
    """Join the parts. A part without a result is UNKNOWN. Parts from different commits, or run with
    different cores, are UNKNOWN too, whatever each says: they do not describe one system."""
    statuses = [item.status if item.decided else "UNKNOWN" for item in items]
    causes = []
    if len({item.commit for item in items if item.decided and item.commit}) > 1:
        causes.append("parts are from different commits")
    if len({item.core for item in items if item.decided and item.core}) > 1:
        causes.append("parts ran with different cores")
    statuses += ["UNKNOWN"] * len(causes)
    counts = summed(item.counts for item in items if item.decided)
    return Verdict(weakest(statuses), counts, "; ".join(causes))


def worst(parts: Sequence[Part | Contract]) -> str:
    """The verdict of the system: the weakest of its parts (see `system`)."""
    return system(parts).status


def system_line(name: str, items: Sequence[Part | Contract]) -> str:
    """The one line that `make self-validate` shows for the system."""
    verdict = system(items)
    words = " · ".join(f"{verdict.counts[name]} {name}" for name in STATUSES)
    cause = f" ({verdict.cause})" if verdict.cause else ""
    return f"{name}: {verdict.status}: {words}{cause}"
