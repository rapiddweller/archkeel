# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290, AD-291: the story specs of one root, checked on demand against the explore snapshot."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .api import Json, StoryRow, StorySource

SUFFIX: Final = ".story.json"
# A name that cannot leave the folder: no dot, no slash.
ID_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
# The optional fields of a stored spec that say where it comes from; text of the author.
PROVENANCE: Final = ("created", "git_head", "author_kind", "agent")


@dataclass(frozen=True)
class CheckResult:
    """The result of `archkeel view check`; `rebound` says that the spec named another snapshot."""

    result: Mapping[str, Json]
    rebound: bool


# The CLI injects the checker: spec bytes and the path of `architecture.json` give the checked
# result against that snapshot, whatever digests the spec names. A spec the checker cannot read
# raises ValueError.
CheckStory = Callable[[bytes, Path], CheckResult]
# The CLI injects the trace: a snapshot path and a function give a draft spec with empty text.
DraftStory = Callable[[Path, str], Mapping[str, Json]]
# The CLI injects the commit of the root now, or None when there is none.
HeadOf = Callable[[], str | None]


@dataclass(frozen=True)
class Found:
    source: StorySource
    spec: bytes


class Stories:
    """The `*.story.json` files of the folders in order of rank; Studio only reads them.

    On an equal id the first folder wins, so the committed story of the repository wins over a
    local one.
    """

    def __init__(
        self,
        folders: Sequence[tuple[StorySource, Path]],
        check: CheckStory,
        draft: DraftStory,
        head: HeadOf,
    ) -> None:
        self.folders = tuple((source, folder.resolve()) for source, folder in folders)
        self.check = check
        self.draft = draft
        self.head = head

    def find(self, story_id: str) -> Found | None:
        """The spec of one id from the first folder that has it; never a path outside a folder."""
        if ID_PATTERN.fullmatch(story_id) is None:
            return None
        for source, folder in self.folders:
            target = folder / f"{story_id}{SUFFIX}"
            if target.resolve().parent == folder and target.is_file():
                return Found(source, target.read_bytes())
        return None

    def rows(self) -> list[StoryRow]:
        """One row for each id; a file that does not parse is a row with zero steps."""
        rows: dict[str, StoryRow] = {}
        for source, folder in self.folders:
            for path in sorted(folder.glob(f"*{SUFFIX}")):
                story_id = path.name.removesuffix(SUFFIX)
                if ID_PATTERN.fullmatch(story_id) is None or story_id in rows:
                    continue
                body = _read(path)
                title = body.get("title") if body is not None else None
                steps = body.get("steps") if body is not None else None
                rows[story_id] = StoryRow(
                    story_id,
                    title if isinstance(title, str) else story_id,
                    len(steps) if isinstance(steps, list) else 0,
                    source,
                )
        return sorted(rows.values(), key=lambda row: row.id)


def _decoded(raw: bytes) -> Mapping[str, Json] | None:
    """The top-level object of a spec, or None when it is not JSON or not an object."""
    try:
        body: Json = json.loads(raw)
    except ValueError:
        return None
    return body if isinstance(body, Mapping) else None


def _read(path: Path) -> Mapping[str, Json] | None:
    try:
        return _decoded(path.read_bytes())
    except OSError:
        return None


def provenance(spec: bytes) -> dict[str, str | None]:
    """The optional fields that say where a spec comes from; absent or not text gives None."""
    found = _decoded(spec) or {}
    result: dict[str, str | None] = {}
    for name in PROVENANCE:
        value = found.get(name)
        result[name] = value if isinstance(value, str) else None
    return result
