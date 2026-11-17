# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The `init` command, and the draft that `validate` and `report` make without `archkeel.toml`.

Both use the draft of `init_draft` (AD-626, AD-638). The draft decides nothing: its first verdict
is UNKNOWN with the open decisions. A file that exists is never replaced. Where writing is wrong
(a folder that cannot be written, `--no-init`, `ARCHKEEL_NO_INIT=1`), nothing is written and the
run stops with the draft in words, because the core reads files and cannot take a draft from memory.
The draft step gives one `InitOutcome` (AD-735): its state, what it wrote and the stop text.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from .core_arguments import Options
from .core_frame import CoreCommand as Command
from .core_frame import RefusalKind
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

_OPT_OUT: Final = "ARCHKEEL_NO_INIT"
# A value of the variable that keeps the draft on. Each other value opts out: writing is the step
# that must not happen by mistake.
_KEEP_ON: Final = frozenset({"", "0", "false", "no", "off"})


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
            "state": _InitState.CREATED,
            "written": list(self.files),
            "components": list(self.result.components),
            "language": self.result.language,
            "parts": list(self.result.parts),
            "interfaces": list(self.result.interfaces),
            "note": self.result.note,
            "message": " ".join(self.lines()),
        }


class _InitState(StrEnum):
    """What the draft step of `validate` and `report` came to."""

    # A configuration other than the default, a file that exists, or no Git work tree.
    NOT_FIRST_RUN = "not_first_run"
    # No `archkeel.toml`, and a system document of the repository is the configuration.
    SYSTEM_FOUND = "system_found"
    CREATED = "created"
    OPTED_OUT = "opted_out"
    CANNOT_WRITE = "cannot_write"
    NOTHING_TO_DRAFT = "nothing_to_draft"


@dataclass(frozen=True)
class InitOutcome:
    """The state of the draft step, what it wrote (`created`) and the stop text (`message`)."""

    state: _InitState
    created: Created | None = None
    message: str = ""

    def refusal(self) -> tuple[RefusalKind, str] | None:
        """The refusal kind and the fix of a stop, or `None` when the run goes on."""
        match self.state:
            case _InitState.NOT_FIRST_RUN | _InitState.SYSTEM_FOUND | _InitState.CREATED:
                return None
            case _InitState.OPTED_OUT:
                return RefusalKind.INVALID_INPUT, (
                    "run `archkeel init` to write the draft, or run again without --no-init and "
                    f"{_OPT_OUT}."
                )
            case _InitState.CANNOT_WRITE:
                return RefusalKind.IO_ERROR, "allow writing in the project folder, then run again."
            case _InitState.NOTHING_TO_DRAFT:
                return RefusalKind.INVALID_INPUT, (
                    f"write {CONFIG} and a contract by hand (the guide shows how), or name a "
                    "configuration with --config PATH."
                )


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


def _project_root(path: Path) -> Path | None:
    """The Git work tree at or above `path`, or `None` outside a repository."""
    return next((folder for folder in (path, *path.parents) if (folder / ".git").exists()), None)


def _opted_out(options: Options) -> str | None:
    """The words for the way the user opted out of writing, or `None`."""
    if options.no_init:
        return "--no-init"
    if os.environ.get(_OPT_OUT, "").strip().lower() not in _KEEP_ON:
        return f"{_OPT_OUT}={os.environ[_OPT_OUT]}"
    return None


def _declined(result: Draft, why: str, root: Path) -> str:
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


def _prepare(options: Options, root: Path) -> tuple[Options, InitOutcome]:
    """Make the files for a project without a configuration, and find the configuration.

    Without `archkeel.toml` a system document of the repository is the configuration. Gives the
    options (with that configuration) and the outcome. When this is not a first run (a
    configuration other than the default, or no Git work tree), the core gives its own refusal.
    """
    # An explicit `--root` is the project; without it the project is the work tree above.
    base = root if options.root is not None and (root / ".git").exists() else None
    base = base or (_project_root(root) if options.root is None else None)
    if options.config != CONFIG or base is None or (base / options.config).exists():
        return options, InitOutcome(_InitState.NOT_FIRST_RUN)
    if (base / SYSTEM).is_file():
        return _with(options, SYSTEM), InitOutcome(_InitState.SYSTEM_FOUND)
    try:
        result = draft(base)
    except NothingToDraft as error:
        return options, InitOutcome(_InitState.NOTHING_TO_DRAFT, message=str(error))
    if (reason := _opted_out(options)) is not None:
        stop = _declined(result, f"switched off by {reason}", base)
        return options, InitOutcome(_InitState.OPTED_OUT, message=stop)
    try:
        written = tuple(write_missing(base, result))
    except OSError as error:
        stop = _declined(result, f"cannot write: {error}", base)
        return options, InitOutcome(_InitState.CANNOT_WRITE, message=stop)
    created = Created(written, result)
    return _with(options, result.entry), InitOutcome(_InitState.CREATED, created)


def _run_init(as_json: bool, root: Path) -> int:
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
