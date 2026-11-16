# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the command line of the shell into typed options (AD-596).

The shell serves `validate`, `report` and `skill`. This part owns the help text, the options and
the refusal of each command or option of the deleted Python shell by name. It reads the arguments
only: it starts no process, finds no binary and reads no frame.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn

from .core_frame import CheckKind, CoreError
from .core_frame import CoreCommand as Command

# Accepted and ignored: the core is the only path, so the switch selects nothing.
VARIABLE: Final = "ARCHKEEL_CORE_ONLY"
RELEASE: Final = "4.0.1"
_LINE: Final = "not available on this development line"
SERVED: Final = frozenset({Command.VALIDATE, Command.REPORT})
# Release 4.0.1 has `check` and `init`. No release has the other refused commands.
RELEASED: Final = frozenset({Command.CHECK, Command.INIT})
# The options of the deleted Python shell that release 4.0.1 does not have.
UNRELEASED_OPTIONS: Final = frozenset(
    {"--collector-timeout-seconds", "--html", "--native-core", "--strict", "--timings"}
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
        "--timings",
        "--tsconfig",
        "--write-amendment",
        "--write-graph",
    }
)
HELP: Final = f"""\
usage: archkeel <command> [--root PATH] [--config PATH] [--json | --text]

The Rust core (archkeel-core) decides each run. This shell prints its frame.

commands:
  validate   Check the contract. PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
             With --baseline, a difference from the file exits 1 and an accepted UNKNOWN exits 2.
  report     Print the same frame of the core as a report. The exit codes are the same.
  skill      Install the agent skill: archkeel skill install {{claude,codex}} [--root PATH]

{_LINE} (#880), exit 2:
  check, init                           Use release {RELEASE}.
  explore, guide, story, view, studio   No release has them.

options:
  --root PATH     Repository root. Default: the Git work tree of the current directory.
  --config PATH   Configuration file below the root. Default: archkeel.toml.
  --json          Print JSON also in a terminal.
  --text          Print text also without a terminal.
  --topology      Include the bounded topology in report only. Default: no topology work.
  --output PATH   Report only: write one file. No file is written by default.
  --format FORMAT Report only, with --output: html (default) or json. No sidecar files.
  --baseline PATH Validate only: compare with this baseline file below the root, in both
                  directions. A new gap or violation, and an accepted item that is gone, exit 1.
  --write-baseline PATH
                  Validate only: write the baseline of this run (schema 1.4.0) to this file.
  --core-only     Accepted and ignored: the core is the only path.
  --version       Print the version.
"""


class NotOnThisLine(CoreError):
    """A command or option of the deleted Python shell that this development line does not serve."""


def _remedy(released: bool) -> str:
    """The true way to get the refused part: a release that has it, or the fact that none has."""
    return (
        f"use release {RELEASE}" if released else f"no release has it; release {RELEASE} is older"
    )


class Options(argparse.Namespace):
    """The options of one command line, as read by the parser."""

    command: Command
    root: Path | None = None
    config: str = "archkeel.toml"
    json: bool = False
    text: bool = False
    core_only: bool = False
    topology: bool = False
    action: str = ""
    agent: str = ""
    output: Path | None = None
    format: str = "html"
    baseline: str | None = None
    write_baseline: str | None = None


class Parser(argparse.ArgumentParser):
    """An argument parser that raises `ValueError` and never exits or prints."""

    def error(self, message: str) -> NoReturn:
        """Refuse the arguments with a `ValueError`."""
        raise ValueError(message)


def active_checks() -> tuple[CheckKind, ...]:
    """Every existing check authenticates a lock and evaluates an expectation (AD-399, #1103).

    Ratchets and selected changes are inside authenticated bytes, not command-line choices.
    There is no verdict-only form of the shipped check command.
    """
    return tuple(CheckKind)


def command_of(argv: Sequence[str]) -> Command:
    """The registered command, or the refusal of a command that this line does not serve."""
    try:
        command = Command(argv[0])
    except ValueError as error:
        raise ValueError(f"unknown command {argv[0]!r}; run archkeel --help") from error
    if command is Command.CHECK:
        names = "; ".join(active_checks())
        raise NotOnThisLine(
            f"check is {_LINE}; {_remedy(True)} (#880); not ported: {names} (#1103)"
        )
    if command not in SERVED and command is not Command.SKILL:
        raise NotOnThisLine(f"{command} is {_LINE}; {_remedy(command in RELEASED)} (#880)")
    return command


def _output_path(value: str) -> Path:
    if value == "-":
        raise argparse.ArgumentTypeError("standard output is not a file target; omit --output")
    path = Path(value)
    if not value or not path.name:
        raise argparse.ArgumentTypeError(
            "--output must name a file, not an empty path or directory"
        )
    return path


def _baseline_path(value: str) -> str:
    """A baseline path below the root, in the form that the core reads (AD-546)."""
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or path.name in {"", "."}:
        raise argparse.ArgumentTypeError(
            "a baseline path must name a file below the root, not an absolute or parent path"
        )
    return path.as_posix()


def parse(argv: Sequence[str]) -> Options:
    """The options of a served command. Each other argument is refused by name."""
    command = command_of(argv)
    parser = Parser(prog=f"archkeel {command}", add_help=False, allow_abbrev=False)
    parser.add_argument("--root", type=Path)
    form = parser.add_mutually_exclusive_group()
    for flag in ("json", "text"):
        form.add_argument(f"--{flag}", action="store_true")
    if command is Command.SKILL:
        parser.add_argument("action", choices=["install"])
        parser.add_argument("agent", choices=["claude", "codex"])
    else:
        parser.add_argument("--core-only", action="store_true")
        parser.add_argument("--config", default="archkeel.toml")
        if command is Command.VALIDATE:
            parser.add_argument("--baseline", type=_baseline_path)
            parser.add_argument("--write-baseline", type=_baseline_path)
        if command is Command.REPORT:
            parser.add_argument("--topology", action="store_true")
            parser.add_argument("--output", type=_output_path)
            parser.add_argument("--format", choices=["html", "json"], default="html")
    options, extra = parser.parse_known_args(argv[1:], Options(command=command))
    for argument in extra:
        if (name := argument.split("=", 1)[0]) in REMOVED_OPTIONS:
            remedy = _remedy(name not in UNRELEASED_OPTIONS)
            raise NotOnThisLine(f"{command} {name} is {_LINE}; {remedy} (#880)")
    if extra:
        raise ValueError(f"unknown arguments: {' '.join(extra)}; run archkeel --help")
    if options.baseline is not None and options.baseline == options.write_baseline:
        raise ValueError(
            "--baseline and --write-baseline name the same file; "
            "compare with one file and write another, or use --write-baseline alone"
        )
    if any(arg == "--format" or arg.startswith("--format=") for arg in argv) and not options.output:
        raise ValueError("--format needs --output; no report file was written")
    return options
