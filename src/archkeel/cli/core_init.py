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
from .init_draft import (
    CONFIG,
    CONTRACT,
    DOCUMENT,
    SYSTEM,
    Draft,
    NothingToDraft,
    draft,
    write_missing,
)

OPT_OUT: Final = "ARCHKEEL_NO_INIT"


@dataclass(frozen=True)
class Created:
    """What a run wrote for a project without `archkeel.toml`."""

    files: tuple[str, ...]
    result: Draft

    def lines(self) -> list[str]:
        """The one block that opens the output: what was written, why and the next step."""
        count = len(self.result.components)
        if self.result.parts:
            made = (
                f"a system document with {len(self.result.parts)} parts "
                f"({', '.join(self.result.parts)}), each with a configuration and a contract "
                f"draft, {count} components in all"
            )
            layout = "mixed-language repository"
        elif CONTRACT in self.files:
            made = f"archkeel.toml and a first contract draft with {count} components"
            layout = _layout(self.result)
        else:
            made = f"archkeel.toml for your existing {CONTRACT}"
            layout = _layout(self.result)
        out = [
            f"ArchKeel created {made} from your {layout} layout.",
            f"Why: there was no {CONFIG}. Written: {', '.join(self.files)}. No file was replaced.",
        ]
        if self.result.parts:
            out.append(_interfaces(self.result))
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
            "parts": list(self.result.parts),
            "interfaces": list(self.result.interfaces),
            "note": self.result.note,
            "message": " ".join(self.lines()),
        }


def _layout(result: Draft) -> str:
    return {
        "python": "package",
        "rust": "Cargo workspace",
        "typescript": "TypeScript",
        "dart": "Dart package",
    }.get(result.language, result.language)


def _interfaces(result: Draft) -> str:
    if result.interfaces:
        return f"Interfaces: {len(result.interfaces)} open (each names a spec file); confirm each."
    return (
        "Interfaces: none drafted. A crossing needs a schema file (OpenAPI, proto, ...); add "
        "`interfaces` to the system document by hand."
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
    what = (
        f"a system of {len(result.parts)} parts ({', '.join(result.parts)})"
        if result.parts
        else f"{len(result.components)} components for {result.language}"
    )
    return (
        f"No {CONFIG} in {root}, and nothing was written ({why}). The layout would give {what}: "
        f"{', '.join(result.components)}. Run `archkeel init` in a folder that can be written to "
        f"save it, then `archkeel validate`. Guide: {DOCUMENT}"
    )


def _with(options: Options, config: str) -> Options:
    found = Options(**vars(options))
    found.config = config
    return found


def prepare(options: Options, root: Path) -> tuple[Options, Created | str | None]:
    """Make the files for a project without a configuration, and find the configuration.

    Without `archkeel.toml` a system document of the repository is the configuration. Gives the
    options (with that configuration), and `Created` after a write, the stop text when nothing
    may or can be written, or `None` when this is not a first run (a configuration other than
    the default, or no Git work tree), so that the core gives its own refusal.
    """
    # An explicit `--root` is the project; without it the project is the work tree above.
    base = root if options.root is not None and (root / ".git").exists() else None
    base = base or (project_root(root) if options.root is None else None)
    if options.config != CONFIG or base is None or (base / options.config).exists():
        return options, None
    if (base / SYSTEM).is_file():
        return _with(options, SYSTEM), None
    try:
        result = draft(base)
    except NothingToDraft as error:
        return options, str(error)
    if (reason := opted_out(options)) is not None:
        return options, declined(result, f"switched off by {reason}", base)
    try:
        written = tuple(write_missing(base, result))
    except OSError as error:
        return options, declined(result, f"cannot write: {error}", base)
    return _with(options, result.entry), Created(written, result)


def run_init(as_json: bool, root: Path) -> int:
    """The command `archkeel init`: draft the files, or refuse and write nothing."""
    result = draft(root)
    files = write_missing(root, result)
    if not files:
        raise FileExistsError(
            f"every file of the draft exists in {root} already; init replaces none"
        )
    if as_json:
        document: dict[str, object] = {"command": Command.INIT, "exit_code": 0, "files": files}
        document |= {"components": result.components, "language": result.language}
        document |= {"parts": result.parts, "interfaces": result.interfaces, "note": result.note}
        print(json.dumps(document))
        return 0
    what = f"a system of {len(result.parts)} parts" if result.parts else _layout(result) + " layout"
    print(f"Drafted {len(files)} files for {result.language} ({what}):")
    for name in files:
        print(f"  {name}")
    if result.parts:
        print(f"Parts: {', '.join(result.parts)}")
        print(_interfaces(result))
    print(f"Components ({len(result.components)}): {', '.join(result.components)}")
    if result.note:
        print(f"Note: {result.note}")
    print("Every responsibility and rationale is a TODO. Replace each with your decision, then run")
    config = (
        ""
        if result.entry == CONFIG or not (root / CONFIG).exists()
        else f" --config {result.entry}"
    )
    print(f"  archkeel validate{config}\nGuide: {DOCUMENT}")
    return 0
