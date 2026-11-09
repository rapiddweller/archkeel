# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A claimed section without a record needs the statement that each file was examined (AD-344).

A collector that claims a section and sends no record says one of two things: the source has no
such fact, or the collector did not look. The reply separates them. For each claimed section from
`CHECKED_SECTIONS` that has no record, `capabilities.examined` holds a digest of the paths that the
collector examined. The host compares it with the parsed files of the reply. A missing or different
digest rejects the reply, so an empty claimed section never reads as a PASS.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import replace

from .facts import Capabilities, FactSection, FileFact, SourceFacts, SourceSectionName
from .protocol import CollectionRequest

CHECKED_SECTIONS = frozenset(
    {
        SourceSectionName.CALLS,
        SourceSectionName.REFERENCES,
        SourceSectionName.CONSTRUCTS,
        SourceSectionName.UNKNOWNS,
    }
)
Statements = tuple[tuple[SourceSectionName, str], ...]


def examined_digest(paths: Iterable[str]) -> str:
    """Digest the set of paths: the order does not change it, and a path keeps its boundary."""
    listing = "\n".join(sorted(set(paths)))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def examined_statements(files: Iterable[FileFact], sections: Iterable[FactSection]) -> Statements:
    """State the examined files for each checked section that has no record."""
    digest = examined_digest(file.rel_path for file in files)
    return tuple(
        (item.name, digest)
        for item in sorted(sections, key=lambda item: item.name.value)
        if item.name in CHECKED_SECTIONS and not item.records
    )


def check_examined(facts: SourceFacts) -> None:
    """Reject a reply with an empty checked section that lacks a right statement."""
    claimed = {section.name: section for section in facts.sections}
    states = dict(facts.capabilities.examined)
    if len(states) != len(facts.capabilities.examined):
        raise ValueError("examined statement is repeated for a section")
    digest = examined_digest(file.rel_path for file in facts.files)
    for name, state in states.items():
        if name not in CHECKED_SECTIONS or name not in claimed:
            raise ValueError(f"examined statement names section {name.value}, which is not claimed")
        if state != digest:
            raise ValueError(f"examined statement of section {name.value} names other files")
    if not facts.files:
        return
    for name in sorted(CHECKED_SECTIONS & claimed.keys(), key=lambda item: item.value):
        if not claimed[name].records and name not in states:
            raise ValueError(
                f"claimed section {name.value} has no record and no examined statement"
            )


def decode_examined(raw: object) -> Statements:
    """Read `capabilities.examined`; a reply without it states nothing."""
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not raw:
        raise ValueError("capabilities.examined must be a nonempty object")
    try:
        names = [(SourceSectionName(name), digest) for name, digest in raw.items()]
    except ValueError as error:
        raise ValueError("capabilities.examined names an unknown section") from error
    if any(not isinstance(digest, str) or not digest for _, digest in names):
        raise ValueError("capabilities.examined holds a digest that is not a string")
    return tuple(names)


def encode_examined(capabilities: Capabilities) -> dict[str, dict[str, str]]:
    """Write `capabilities.examined` only when a section has a statement."""
    states = {name.value: digest for name, digest in capabilities.examined}
    return {"examined": states} if states else {}


def states_examined(
    collect: Callable[[CollectionRequest], SourceFacts],
) -> Callable[[CollectionRequest], SourceFacts]:
    """Make a collector state the examined files of each empty checked section."""

    def stated(request: CollectionRequest) -> SourceFacts:
        facts = collect(request)
        states = examined_statements(facts.files, facts.sections)
        return replace(facts, capabilities=replace(facts.capabilities, examined=states))

    return stated
