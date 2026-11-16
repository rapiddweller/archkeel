# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The `init` command, and the draft that `validate` and `report` make without `archkeel.toml`.

Both use the draft of `init_draft` (AD-626, AD-638). The draft decides nothing: its first verdict
is UNKNOWN with the open decisions. A file that exists is never replaced. Where writing is wrong
(a folder that cannot be written, `--no-init`, `ARCHKEEL_NO_INIT=1`), nothing is written and the
run stops with the draft in words, because the core reads files and cannot take a draft from memory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .core_arguments import Options
from .core_frame import CoreCommand as Command
from .init_draft import CONFIG, CONTRACT, DOCUMENT, Draft, NothingToDraft, draft, write_missing

OPT_OUT: Final = "ARCHKEEL_NO_INIT"


@dataclass(frozen=True)
class Created:
    """What a run wrote for a project without `archkeel.toml`."""

    files: tuple[str, ...]
    result: Draft

    def lines(self) -> list[str]:
        """The one block that opens the output: what was written, why and the next step."""
        count = len(self.result.components)
        if CONTRACT in self.files:
            made = f"archkeel.toml and a first contract draft with {count} components"
        else:
            made = f"archkeel.toml for your existing {CONTRACT}"
        out = [
            f"ArchKeel created {made} from your {_layout(self.result)} layout.",
            f"Why: there was no {CONFIG}. Written: {', '.join(self.files)}. No file was replaced.",
        ]
        if self.result.note:
            out.append(f"Note: {self.result.note}")
        out.append(
            "Review the open decisions listed below, then run archkeel validate again. "
            f"Guide: {DOCUMENT}"
        )
        return out

    def as_json(self) -> dict[str, object]:
        """The same block for JSON output."""
        return {
            "written": list(self.files),
            "components": list(self.result.components),
            "language": self.result.language,
            "note": self.result.note,
            "message": " ".join(self.lines()),
        }


def _layout(result: Draft) -> str:
    return {"python": "package", "rust": "Cargo workspace", "typescript": "workspace"}.get(
        result.language, result.language
    )


def project_root(path: Path) -> Path | None:
    """The Git work tree at or above `path`, or `None` outside a repository."""
    return next((folder for folder in (path, *path.parents) if (folder / ".git").exists()), None)


def opted_out(options: Options) -> str | None:
    """The words for the way the user opted out of writing, or `None`."""
    if options.no_init:
        return "--no-init"
    if os.environ.get(OPT_OUT, "") not in {"", "0"}:
        return f"{OPT_OUT}={os.environ[OPT_OUT]}"
    return None


def declined(result: Draft, why: str, root: Path) -> str:
    """The stop text: nothing was written, what the layout would give, and the way to save it."""
    return (
        f"No {CONFIG} in {root}, and nothing was written ({why}). The layout would give "
        f"{len(result.components)} components for {result.language} (namespace "
        f"{result.namespace}): {', '.join(result.components)}. Run `archkeel init` in a folder "
        f"that can be written to save it, then `archkeel validate`. Guide: {DOCUMENT}"
    )


def prepare(options: Options, root: Path) -> Created | str | None:
    """Make the files for a project without `archkeel.toml`.

    Gives `Created` after a write, the stop text when nothing may or can be written, and `None`
    when this is not a first run (a configuration other than the default, or no Git work tree),
    so that the core gives its own refusal.
    """
    # An explicit `--root` is the project; without it the project is the work tree above.
    base = root if options.root is not None and (root / ".git").exists() else None
    base = base or (project_root(root) if options.root is None else None)
    if options.config != CONFIG or base is None or (base / options.config).exists():
        return None
    try:
        result = draft(base)
    except NothingToDraft as error:
        return str(error)
    if (reason := opted_out(options)) is not None:
        return declined(result, f"switched off by {reason}", base)
    try:
        return Created(tuple(write_missing(base, result)), result)
    except OSError as error:
        return declined(result, f"cannot write: {error}", base)


def run_init(as_json: bool, root: Path) -> int:
    """The command `archkeel init`: draft the files, or refuse and write nothing."""
    result = draft(root)
    files = write_missing(root, result)
    if not files:
        raise FileExistsError(f"{CONFIG} and {CONTRACT} exist in {root}; init replaces no file")
    if as_json:
        document: dict[str, object] = {"command": Command.INIT, "exit_code": 0, "files": files}
        document |= {"components": result.components, "language": result.language}
        document["note"] = result.note
        print(json.dumps(document))
        return 0
    print(f"Drafted {len(files)} files for {result.language} ({_layout(result)} layout):")
    for name in files:
        print(f"  {name}")
    print(f"Components ({len(result.components)}): {', '.join(result.components)}")
    if result.note:
        print(f"Note: {result.note}")
    print("Every responsibility and rationale is a TODO. Replace each with your decision, then run")
    print(f"  archkeel validate\nGuide: {DOCUMENT}")
    return 0
