# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-292: the snapshot index that decides what is OBSERVED, and the strict check of an answer."""

import json
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
)

PROPOSAL_LABEL: Final = "PROPOSED - NOT APPLIED"
_BLOCK_LIMIT = 10
_TEXT_LIMIT = 2000
_REF_LIMIT = 20
_LISTED = 30
_UNKNOWN_LISTED = 10
_EXPRESSION_LIMIT = 80
_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\s*\Z", re.DOTALL)
_BLOCK_KEYS = {"kind", "text", "refs"}


def _records(model: Mapping[str, object], section: str) -> list[Mapping[str, object]]:
    value = model.get(section)
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _data(record: Mapping[str, object]) -> Mapping[str, object]:
    data = record.get("data")
    return data if isinstance(data, Mapping) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _names(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _listing(label: str, names: list[str], cap: int) -> str:
    """`label: a, b, and 3 more`, or `label: none`."""
    shown = names[:cap]
    if len(names) > cap:
        shown.append(f"and {len(names) - cap} more")
    return f"{label}: {', '.join(shown) if shown else 'none'}"


def _invalid(why: str) -> ChatFailure:
    return ChatFailure(ChatError.INVALID_ANSWER, f"The agent answer is not accepted: {why}")


def _object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if fenced := _FENCE.match(stripped):
        stripped = fenced.group(1)
    try:
        body = json.loads(stripped)
    except ValueError as error:
        raise _invalid("it is not one JSON object") from error
    if not isinstance(body, dict):
        raise _invalid("it is not one JSON object")
    return body


class Snapshot:
    """The symbols and calls of the explore snapshot; the only source of a fact."""

    def __init__(self, model: Mapping[str, object]) -> None:
        places = {
            _text(item.get("id")): (_text(item.get("file")), item.get("line"))
            for item in _records(model, "evidence")
        }
        self._symbols: dict[str, tuple[str, str, int]] = {}
        for record in _records(model, "symbols"):
            name = _text(_data(record).get("qualified_name"))
            ids = _names(record.get("evidence_ids"))
            file, line = places.get(ids[0], ("", 0)) if ids else ("", 0)
            if name:
                self._symbols[name] = (
                    _text(record.get("kind")),
                    file,
                    line if isinstance(line, int) else 0,
                )
        self._callers: dict[str, set[str]] = defaultdict(set)
        self._callees: dict[str, set[str]] = defaultdict(set)
        self._unknown: dict[str, list[str]] = defaultdict(list)
        for record in _records(model, "calls"):
            data = _data(record)
            scope = _text(data.get("source_scope"))
            if _text(data.get("status")) == CallStatus.RESOLVED:
                for target in _names(data.get("targets")):
                    self._callers[target].add(scope)
                    self._callees[scope].add(target)
            else:
                self._unknown[scope].append(_text(data.get("expression"))[:_EXPRESSION_LIMIT])

    def has(self, name: str) -> bool:
        return name in self._symbols

    def fact(self, name: str) -> Fact:
        _, file, line = self._symbols[name]
        return Fact(
            name,
            file,
            line,
            len(self._callers.get(name, ())),
            len(self._callees.get(name, ())),
            len(self._unknown.get(name, ())),
        )

    def neighborhood(self, name: str) -> str:
        """The lines of the prompt about one symbol and its direct callers and callees."""
        kind, file, line = self._symbols[name]
        unknown = self._unknown.get(name, [])
        return "\n".join(
            (
                f"{name} ({kind}) {file}:{line}" if file else f"{name} ({kind})",
                _listing("callers", sorted(self._callers.get(name, ())), _LISTED),
                _listing("callees", sorted(self._callees.get(name, ())), _LISTED),
                _listing(f"unknown calls ({len(unknown)})", unknown, _UNKNOWN_LISTED),
            )
        )

    def check(self, text: str, agent: AgentKind) -> ChatAnswer:
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
            if not isinstance(refs, list) or len(refs) > _REF_LIMIT or _names(refs) != refs:
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
                    dropped[ref] = None
            label = PROPOSAL_LABEL if kind is ChatBlockKind.PROPOSAL else None
            kept.append(ChatBlock(kind, words, tuple(valid), label))
        return ChatAnswer(agent, tuple(kept), tuple(facts.values()), tuple(dropped))
