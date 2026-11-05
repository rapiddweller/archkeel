# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-292: the snapshot index that decides what is OBSERVED, and the strict check of an answer."""

import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Final

from .api import (
    AgentKind,
    CallStatus,
    ChatAnswer,
    ChatBlock,
    ChatBlockKind,
    ChatError,
    ChatFailure,
    Fact,
    Json,
    Place,
    SnapshotCompleteness,
    SymbolKind,
    data_of,
    decoded,
    first_place,
    member,
    places,
    rows,
    text_at,
    texts_at,
)

PROPOSAL_LABEL: Final = "PROPOSED - NOT APPLIED"
_BLOCK_LIMIT = 10
_TEXT_LIMIT = 2000
_REF_LIMIT = 20
_LISTED = 30
_UNKNOWN_LISTED = 10
_EXPRESSION_LIMIT = 80
_DROPPED_LIMIT = 50
_DROPPED_LENGTH = 300
_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\s*\Z", re.DOTALL)
_BLOCK_KEYS = {"kind", "text", "refs"}


def _listing(label: str, names: list[str], cap: int) -> str:
    """`label: a, b, and 3 more`, or `label: none`."""
    shown = names[:cap]
    if len(names) > cap:
        shown.append(f"and {len(names) - cap} more")
    return f"{label}: {', '.join(shown) if shown else 'none'}"


def _invalid(why: str) -> ChatFailure:
    return ChatFailure(ChatError.INVALID_ANSWER, f"The agent answer is not accepted: {why}")


def _object(text: str) -> Mapping[str, Json]:
    stripped = text.strip()
    if fenced := _FENCE.match(stripped):
        stripped = fenced.group(1)
    body = decoded(stripped)
    if body is None:
        raise _invalid("it is not one JSON object")
    return body


class Snapshot:
    """The symbols and calls of the explore snapshot; the only source of a fact."""

    def __init__(
        self,
        model: Mapping[str, Json],
        completeness: SnapshotCompleteness = SnapshotCompleteness.COMPLETE,
    ) -> None:
        self.completeness = completeness
        found = places(model)
        self._symbols: dict[str, tuple[str, Place]] = {}
        for record in rows(model, "symbols"):
            name = text_at(data_of(record), "qualified_name")
            if name:
                self._symbols[name] = (text_at(record, "kind"), first_place(record, found))
        self._callers: dict[str, set[str]] = defaultdict(set)
        self._callees: dict[str, set[str]] = defaultdict(set)
        self._unknown: dict[str, list[str]] = defaultdict(list)
        for record in rows(model, "calls"):
            data = data_of(record)
            scope = text_at(data, "source_scope")
            if member(CallStatus, data.get("status")) is CallStatus.RESOLVED:
                for target in texts_at(data, "targets"):
                    self._callers[target].add(scope)
                    self._callees[scope].add(target)
            else:
                self._unknown[scope].append(text_at(data, "expression")[:_EXPRESSION_LIMIT])

    def has(self, name: str) -> bool:
        return name in self._symbols

    def is_callable(self, name: str) -> bool:
        symbol = self._symbols.get(name)
        if symbol is None:
            return False
        kind = member(SymbolKind, symbol[0])
        return kind is SymbolKind.FUNCTION or kind is SymbolKind.METHOD

    def fact(self, name: str) -> Fact:
        _, place = self._symbols[name]
        return Fact(
            name,
            place.file,
            place.line,
            len(self._callers.get(name, ())),
            len(self._callees.get(name, ())),
            len(self._unknown.get(name, ())),
        )

    def neighborhood(self, name: str) -> str:
        """The lines of the prompt about one symbol and its direct callers and callees."""
        kind, place = self._symbols[name]
        unknown = self._unknown.get(name, [])
        return "\n".join(
            (
                f"{name} ({kind}) {place.file}:{place.line}" if place.file else f"{name} ({kind})",
                _listing("callers", sorted(self._callers.get(name, ())), _LISTED),
                _listing("callees", sorted(self._callees.get(name, ())), _LISTED),
                _listing(f"unknown calls ({len(unknown)})", unknown, _UNKNOWN_LISTED),
            )
        )

    def check(
        self,
        text: str,
        agent: AgentKind,
    ) -> ChatAnswer:
        """Parse the agent text strictly. Keep the refs that exist; report the others."""
        body = _object(text)
        blocks = body.get("blocks")
        if body.keys() != {"blocks"} or not isinstance(blocks, list) or len(blocks) > _BLOCK_LIMIT:
            raise _invalid(f'it must be {{"blocks": [...]}} with at most {_BLOCK_LIMIT} blocks')
        kept: list[ChatBlock] = []
        facts: dict[str, Fact] = {}
        dropped: dict[str, None] = {}
        for item in blocks:
            if not isinstance(item, dict) or item.keys() != _BLOCK_KEYS:
                raise _invalid("a block needs kind, text and refs, and nothing else")
            words, refs = item["text"], item["refs"]
            if not isinstance(words, str) or len(words) > _TEXT_LIMIT:
                raise _invalid(f"a text must be a string of at most {_TEXT_LIMIT} characters")
            if (
                not isinstance(refs, list)
                or len(refs) > _REF_LIMIT
                or not all(isinstance(ref, str) for ref in refs)
            ):
                raise _invalid(f"refs must be at most {_REF_LIMIT} strings")
            try:
                kind = ChatBlockKind(item["kind"])
            except ValueError as error:
                raise _invalid("a kind must be claim or proposal") from error
            valid: list[str] = []
            for ref in refs:
                if self.has(ref):
                    valid.append(ref)
                    facts.setdefault(ref, self.fact(ref))
                else:
                    dropped[ref[:_DROPPED_LENGTH]] = None
            label = PROPOSAL_LABEL if kind is ChatBlockKind.PROPOSAL else None
            kept.append(ChatBlock(kind, words, tuple(valid), label))
        return ChatAnswer(
            agent,
            self.completeness,
            tuple(kept),
            tuple(facts.values()),
            tuple(dropped)[:_DROPPED_LIMIT],
        )
