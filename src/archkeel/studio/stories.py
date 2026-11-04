# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290, AD-291: the story specs of one root, checked on demand against the explore snapshot."""

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from .api import Json, StoryRow

SUFFIX: Final = ".story.json"
# A name that cannot leave the folder: no dot, no slash.
ID_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
# The CLI injects the checker: spec bytes and the path of `architecture.json` give the checked
# result of `archkeel view check`. A spec the checker cannot read raises ValueError.
CheckStory = Callable[[bytes, Path], Mapping[str, Json]]
# The CLI injects the trace: a snapshot path and a function give a draft spec with empty text.
DraftStory = Callable[[Path, str], Mapping[str, Json]]


class Stories:
    """The `*.story.json` files of one folder; Studio only reads them."""

    def __init__(self, folder: Path, check: CheckStory, draft: DraftStory) -> None:
        self.folder = folder.resolve()
        self.check = check
        self.draft = draft

    def spec(self, story_id: str) -> bytes | None:
        """The bytes of one spec by its id, else None; never a path outside the folder."""
        if ID_PATTERN.fullmatch(story_id) is None:
            return None
        target = self.folder / f"{story_id}{SUFFIX}"
        return (
            target.read_bytes()
            if target.resolve().parent == self.folder and target.is_file()
            else None
        )

    def rows(self) -> list[StoryRow]:
        """One row for each spec file; a file that does not parse is a row with zero steps."""
        rows = []
        for path in sorted(self.folder.glob(f"*{SUFFIX}")):
            story_id = path.name.removesuffix(SUFFIX)
            if ID_PATTERN.fullmatch(story_id) is None:
                continue
            try:
                body = json.loads(path.read_bytes())
            except (OSError, ValueError):
                body = None
            title = body.get("title") if isinstance(body, dict) else None
            steps = body.get("steps") if isinstance(body, dict) else None
            rows.append(
                StoryRow(
                    story_id,
                    title if isinstance(title, str) else story_id,
                    len(steps) if isinstance(steps, list) else 0,
                )
            )
        return rows
