# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the command line of the shell into typed options (AD-596).

The shell serves `validate`, `report`, `explore`, `init` and `skill`. It owns the options and
the refusal of each command or option of the deleted Python shell. It reads the arguments
only: it starts no process, finds no binary and reads no frame.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from enum import StrEnum
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn

from .core_frame import CheckKind, CoreError
from .core_frame import CoreCommand as Command
from .init_preset import Preset, Shape

RELEASE: Final = "4.0.1"
_LINE: Final = "not available in ArchKeel 5.0 yet"
# The options of the deleted Python shell that release 4.0.1 does not have.
UNRELEASED_OPTIONS: Final = frozenset(
    {"--collector-timeout-seconds", "--html", "--native-core", "--strict"}
)
# Each option of the deleted Python shell. The shell refuses it by name.
REMOVED_OPTIONS: Final = frozenset(
    {
        "--accept-new",
        "--against",
        "--amendment",
        "--collector-argv",
        "--collector-output-limit-bytes",
        "--collector-timeout-seconds",
        "--compact-open-decisions",
        "--component",
        "--decided-by",
        "--full",
        "--html",
        "--input",
        "--language",
        "--namespace",
        "--native-core",
        "--only",
        "--output",
        "--rationale",
        "--rule",
        "--strict",
        "--tsconfig",
        "--write-amendment",
        "--write-graph",
    }
)


# The 5.0 command that replaces a removed option. Release 4.0.1 cannot read a 5.0 config, so it is
# no remedy. The tests parse each command here, so each refusal names a command that runs.
_REPLACEMENTS: Final[dict[str, tuple[str, ...]]] = {
    "--against": ("validate", "--baseline", "FILE"),
    "--full": ("report", "--json"),
    "--input": ("report", "--json"),
    "--only": ("report", "--json"),
}
_CHECK_REPLACEMENT: Final = ("validate", "--json")


class NotOnThisLine(CoreError):
    """A command or option of the deleted Python shell that ArchKeel 5.0 does not serve yet."""


def _remedy(released: bool) -> str:
    """The true way to get the refused part: a release that has it, or the fact that none has."""
    return (
        f"use release {RELEASE} for it"
        if released
        else f"no release has it; release {RELEASE} is older"
    )


def _use(argv: tuple[str, ...]) -> str:
    return f"use archkeel {' '.join(argv)}"


def _refused_remedy(name: str) -> str:
    """The 5.0 command of a removed option, else the release that has it, else no release."""
    if name in _REPLACEMENTS:
        return _use(_REPLACEMENTS[name])
    return _remedy(name not in UNRELEASED_OPTIONS)


class Options(argparse.Namespace):
    """The options of one command line, as read by the parser."""

    command: Command
    root: Path | None = None
    project: Path | None = None
    config: str = "archkeel.toml"
    # AD-776: the command line names `--config`; a relative path is read from the current folder.
    config_given: bool = False
    json: bool = False
    text: bool = False
    core_only: bool = False
    topology: bool = False
    all: bool = False
    verbose: bool = False
    summary: bool = False
    action: str = ""
    agent: str = ""
    output: Path | None = None
    timings: Path | None = None
    format: str = "html"
    baseline: str | None = None
    write_baseline: str | None = None
    no_init: bool = False
    part_of: str | None = None
    system_href: str | None = None
    port: int = 0
    no_open: bool = False
    scip_index: Path | None = None
    no_scip: bool = False
    explorer: bool = False
    preset: Preset | None = None
    layers: tuple[str, ...] = ()
    adapters: tuple[str, ...] = ()

    def shape(self) -> Shape | None:
        """The preset of `init` with the names of the user; `ValueError` when they do not fit."""
        if self.preset is None:
            if self.layers or self.adapters:
                raise ValueError("--layers and --adapters need --preset layered or hexagonal")
            return None
        return Shape(self.preset, self.layers, self.adapters)


class Parser(argparse.ArgumentParser):
    """An argument parser that raises `ValueError` and never exits or prints."""

    def error(self, message: str) -> NoReturn:
        """Refuse the arguments with a `ValueError`."""
        raise ValueError(message)


def _active_checks() -> tuple[CheckKind, ...]:
    """Every existing check authenticates a lock and evaluates an expectation (AD-399, #1103).

    Ratchets and selected changes are inside authenticated bytes, not command-line choices.
    There is no verdict-only form of the shipped check command.
    """
    return tuple(CheckKind)


class OutputMode(StrEnum):
    """How a command line prints its result: one mode for the result and each refusal (AD-735)."""

    JSON = "json"
    TEXT = "text"
    # A short text for a CI log.
    SUMMARY = "summary"


def output_mode(argv: Sequence[str]) -> OutputMode:
    """The output mode of a command line. A flag decides; else `init` and a report file print
    text, and each other command prints JSON when its output is not a terminal."""
    if "--summary" in argv:
        return OutputMode.SUMMARY
    if "--json" in argv:
        return OutputMode.JSON
    if "--text" in argv:
        return OutputMode.TEXT
    to_file = any(arg == "--output" or arg.startswith("--output=") for arg in argv)
    if (
        (argv and argv[0] in {Command.INIT, Command.EXPLORE, Command.STUDIO})
        or to_file
        or sys.stdout.isatty()
    ):
        return OutputMode.TEXT
    return OutputMode.JSON


def command_of(argv: Sequence[str]) -> Command:
    """The registered command, or the refusal of a command that this line does not serve."""
    try:
        command = Command(argv[0])
    except ValueError as error:
        raise ValueError(f"unknown command {argv[0]!r}; run archkeel --help") from error
    if command is Command.STUDIO:
        return Command.EXPLORE
    if command is Command.CHECK:
        names = "; ".join(_active_checks())
        raise NotOnThisLine(f"check is {_LINE}; {_use(_CHECK_REPLACEMENT)}; not ported: {names}")
    return command


def _file_path(flag: str, value: str) -> Path:
    if value == "-":
        raise argparse.ArgumentTypeError(f"standard output is not a file target; omit {flag}")
    path = Path(value)
    if not value or not path.name:
        raise argparse.ArgumentTypeError(f"{flag} must name a file, not an empty path or directory")
    return path


def _new_file_path(flag: str, value: str) -> Path:
    """A file that does not exist: the option creates it and never replaces a file (#659)."""
    path = _file_path(flag, value)
    if os.path.lexists(path):
        raise argparse.ArgumentTypeError(
            f"{flag} creates a new file and never replaces one, and {path} exists "
            "(a link counts); use a new name for each run"
        )
    if not path.resolve().parent.is_dir():
        raise argparse.ArgumentTypeError(f"{flag}: the folder of {path} does not exist")
    return path


def _baseline_path(value: str) -> str:
    """A baseline path below the root, in the form that the core reads (AD-546)."""
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or path.name in {"", "."}:
        raise argparse.ArgumentTypeError(
            "a baseline path must name a file below the root, not an absolute or parent path"
        )
    return path.as_posix()


def _document_path(value: str) -> str:
    """A system document below the root, in the form that the core reads (E4)."""
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or path.name in {"", "."}:
        raise argparse.ArgumentTypeError(
            "--part-of must name a system document below the root, not an absolute or parent path"
        )
    return path.as_posix()


def _port(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) > 5 or int(value) > 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 0 to 65535")
    return int(value)


def _preset(value: str) -> Preset:
    try:
        return Preset(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--preset is one of: {', '.join(Preset)}") from None


def _names(value: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in value.split(","))


def _add_preset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--preset", type=_preset)
    parser.add_argument("--layers", type=_names, default=())
    parser.add_argument("--adapters", type=_names, default=())


def parse(argv: Sequence[str]) -> Options:
    """The options of a served command. Each other argument is refused by name."""
    command = command_of(argv)
    parser = Parser(prog=f"archkeel {command}", add_help=False, allow_abbrev=False)
    parser.add_argument("--root", type=Path)
    form = parser.add_mutually_exclusive_group()
    for flag in (
        ("json", "text")
        if command in {Command.SKILL, Command.EXPLORE}
        else ("json", "text", "summary")
    ):
        form.add_argument(f"--{flag}", action="store_true")
    if command not in {Command.SKILL, Command.EXPLORE}:
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--verbose", action="store_true")
    if command is Command.SKILL:
        parser.add_argument("action", choices=["install"])
        parser.add_argument("agent", choices=["claude", "codex"])
    else:
        parser.add_argument("--core-only", action="store_true")
        if command is Command.INIT:
            _add_preset_arguments(parser)
        else:
            parser.add_argument("--config", default="archkeel.toml")
        if command is Command.EXPLORE:
            parser.add_argument("project", nargs="?", type=Path)
            parser.add_argument("--port", type=_port, default=0)
            parser.add_argument("--no-open", action="store_true")
            parser.add_argument("--scip", type=Path, dest="scip_index")
            parser.add_argument("--no-scip", action="store_true")
        if command in {Command.VALIDATE, Command.REPORT}:
            parser.add_argument("--no-init", action="store_true")
            parser.add_argument("--timings", type=partial(_new_file_path, "--timings"))
        if command is Command.VALIDATE:
            parser.add_argument("--baseline", type=_baseline_path)
            parser.add_argument("--write-baseline", type=_baseline_path)
        if command is Command.REPORT:
            parser.add_argument("--topology", action="store_true")
            parser.add_argument("--output", type=partial(_file_path, "--output"))
            parser.add_argument("--format", choices=["html", "json"], default="html")
            parser.add_argument("--part-of", type=_document_path)
            parser.add_argument("--system-href")
    try:
        options, extra = parser.parse_known_args(argv[1:], Options(command=command))
    except ValueError as error:
        if command is Command.SKILL:
            raise ValueError(
                f"{error}; use: archkeel skill install claude (or codex); run archkeel skill --help"
            ) from error
        raise
    for argument in extra:
        if (name := argument.split("=", 1)[0]) in REMOVED_OPTIONS:
            raise NotOnThisLine(f"{command} {name} is {_LINE}; {_refused_remedy(name)}")
    if extra:
        raise ValueError(f"unknown arguments: {' '.join(extra)}; run archkeel --help")
    if command is Command.EXPLORE and options.project is not None:
        if options.root is not None:
            raise ValueError("use either a project path or --root, not both")
        options.root = options.project
    if options.scip_index is not None and options.no_scip:
        raise ValueError("use either --scip or --no-scip, not both")
    if options.baseline is not None and options.baseline == options.write_baseline:
        raise ValueError(
            "--baseline and --write-baseline name the same file; "
            "compare with one file and write another, or use --write-baseline alone"
        )
    if any(arg == "--format" or arg.startswith("--format=") for arg in argv) and not options.output:
        raise ValueError("--format needs --output; no report file was written")
    if options.timings is not None and options.output is not None:
        if options.timings.resolve() == options.output.resolve():
            raise ValueError("--output and --timings name the same file; use two names")
    if options.system_href is not None and options.part_of is None:
        raise ValueError("--system-href needs --part-of: name the system document of this part")
    if options.part_of is not None and (options.output is None or options.format != "html"):
        raise ValueError("--part-of needs an HTML --output: only the page names its system")
    options.shape()
    options.config_given = any(arg == "--config" or arg.startswith("--config=") for arg in argv)
    return options
