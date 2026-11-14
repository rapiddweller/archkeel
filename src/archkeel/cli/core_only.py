# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command shell: the Rust core decides each run and the shell prints its frame (AD-432).

The shell parses the arguments, finds the core binary, sends the scan identity, reads one frame
with `read_frame`, prints it as text or JSON, and maps the status to the exit code. It holds no
rule, fact or contract logic. A command that the core does not serve stays registered and gives a
typed refusal with exit 2; it never falls back and never reports success.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NoReturn

from .core_binary import CoreBinaryNotFound, locate_core
from .core_frame import (
    CheckKind,
    CoreError,
    CoreFrame,
    GapKind,
    RefusalKind,
    Status,
    read_frame,
    resolve_root,
)
from .core_frame import CoreCommand as Command
from .core_json import RequestMismatch
from .native_scan import SCAN_PROTOCOL, exchange, identity

# Accepted and ignored: the core is the only path, so the switch selects nothing.
VARIABLE: Final = "ARCHKEEL_CORE_ONLY"
RELEASE: Final = "4.0.1"
_LINE: Final = "not available on this development line"
# The process exit of the core is not a command verdict (0 and 3 describe frame completeness).
EXIT_CODES: Final[Mapping[Status, int]] = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}
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
        "--baseline",
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
        "--write-baseline",
        "--write-graph",
    }
)
HELP: Final = f"""\
usage: archkeel <command> [--root PATH] [--config PATH] [--json | --text]

The Rust core (archkeel-core) decides each run. This shell prints its frame.

commands:
  validate   Check the contract. PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
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
    command: Command
    root: Path | None = None
    config: str = "archkeel.toml"
    json: bool = False
    text: bool = False
    core_only: bool = False
    action: str = ""
    agent: str = ""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def active_checks() -> tuple[CheckKind, ...]:
    """Every existing check authenticates a lock and evaluates an expectation (AD-399, #1103).

    Ratchets and selected changes are inside authenticated bytes, not command-line choices.
    There is no verdict-only form of the shipped check command.
    """
    return tuple(CheckKind)


def _command(argv: Sequence[str]) -> Command:
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


def parse(argv: Sequence[str]) -> Options:
    """The options of a served command. Each other argument is refused by name."""
    command = _command(argv)
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
    options, extra = parser.parse_known_args(argv[1:], Options(command=command))
    for argument in extra:
        if (name := argument.split("=", 1)[0]) in REMOVED_OPTIONS:
            remedy = _remedy(name not in UNRELEASED_OPTIONS)
            raise NotOnThisLine(f"{command} {name} is {_LINE}; {remedy} (#880)")
    if extra:
        raise ValueError(f"unknown arguments: {' '.join(extra)}; run archkeel --help")
    return options


def _wants_json(argv: Sequence[str]) -> bool:
    return "--json" in argv or (not sys.stdout.isatty() and "--text" not in argv)


def run(argv: Sequence[str]) -> int:
    as_json = _wants_json(argv)
    try:
        if not argv or argv[0] in {"-h", "--help"}:
            print(HELP, end="")
            return 0
        if argv[0] == "--version":
            print(f"archkeel {_version()}")
            return 0
        _command(argv)
        if {"-h", "--help"} & set(argv):
            print(HELP, end="")
            return 0
        options = parse(argv)
        if options.command is Command.SKILL:
            return _install_skill(options, as_json)
        return _decide(options, as_json)
    except (CoreError, OSError, ValueError) as error:
        return _refused(_refusal_kind(error), str(error), as_json)
    except Exception as error:
        traceback.print_exc()
        return _refused(RefusalKind.INTERNAL_ERROR, f"{type(error).__name__}: {error}", as_json)


def _refusal_kind(error: Exception) -> RefusalKind:
    kinds: tuple[tuple[type[Exception], RefusalKind], ...] = (
        (RequestMismatch, RefusalKind.REQUEST_MISMATCH),
        (NotOnThisLine, RefusalKind.NOT_ON_THIS_LINE),
        (CoreBinaryNotFound, RefusalKind.CORE_BINARY_NOT_FOUND),
        (CoreError, RefusalKind.CORE_ERROR),
        (OSError, RefusalKind.IO_ERROR),
    )
    return next(
        (kind for form, kind in kinds if isinstance(error, form)), RefusalKind.INVALID_INPUT
    )


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("archkeel")
    except PackageNotFoundError:
        return "unknown"


def _install_skill(options: Options, as_json: bool) -> int:
    from .skill import InstallationAgent, install_skill

    path = install_skill((options.root or Path.cwd()).resolve(), options.agent)
    if as_json:
        print(json.dumps({"command": Command.SKILL, "exit_code": 0, "path": str(path)}))
    else:
        name = "$archkeel" if options.agent == InstallationAgent.CODEX else "/archkeel"
        print(f"Installed Archkeel instructions: {path}")
        print(f"Use {name} in your agent session; start a new session if needed.")
    return 0


def _decide(options: Options, as_json: bool) -> int:
    """Send the scan identity to the core and print the one frame that it gives."""
    root = resolve_root(options.root or Path.cwd())
    request: dict[str, object] = {
        "protocol": SCAN_PROTOCOL,
        "root": str(root),
        "config": options.config,
        "root_only": True,
        "discover_root": options.root is None,
    }
    if (claim := identity(root)) is not None:
        request["git_head"], request["dirty"] = claim
    binary = locate_core()
    stdout, code = exchange(str(binary), "scan", json.dumps(request).encode())
    frame = read_frame(stdout, code, scan=True, require_protocol=True, request=request)
    result: dict[str, object] = {
        "command": options.command,
        "status": frame.status,
        "exit_code": EXIT_CODES[frame.status],
        "frame": json.loads(stdout),
        "core": {"path": str(binary), "engine": frame.engine, "code_digest": frame.code_digest},
        "gaps": [
            {"kind": gap.kind, "subject": gap.subject, "reason": gap.reason} for gap in frame.gaps
        ],
    }
    collected = next((gap for gap in frame.gaps if gap.kind is GapKind.COLLECT), None)
    if collected is not None:
        result["refusal"] = {"kind": RefusalKind.COLLECTION_REFUSED, "message": collected.reason}
    if as_json:
        print(json.dumps(result))
    else:
        if collected is None:
            render_text(options.command, frame)
        else:
            _refused(RefusalKind.COLLECTION_REFUSED, collected.reason, False)
        print(f"Core: {binary}; engine: {frame.engine}; code digest: {frame.code_digest}")
    return EXIT_CODES[frame.status]


def _refused(kind: RefusalKind, message: str, as_json: bool) -> int:
    refusal = {
        "status": Status.UNKNOWN,
        "exit_code": 2,
        "refusal": {"kind": kind, "message": message},
    }
    print(json.dumps(refusal) if as_json else f"REFUSED: {kind}: {message}")
    return 2


def _places(frame: CoreFrame, evidence: Sequence[str]) -> str:
    places = [
        f"{location.path}:{location.line}" if location.line else location.path
        for key in evidence
        if (location := frame.locations.get(key))
    ]
    return f" ({', '.join(places)})" if places else ""


def render_text(command: Command, frame: CoreFrame) -> None:
    print(f"{command}: {frame.status}")
    if not frame.complete_scope:
        print(f"Scope: {frame.scope}")
        print("Action: Resolve the named scope gap and run again.")
    for source_gap in frame.collection_gaps:
        print(
            f"Source gap: {source_gap.kind}: {', '.join(source_gap.subjects)}: "
            f"{source_gap.reason}{_places(frame, source_gap.evidence)}"
        )
        print("Action: Resolve the collector cause and run again.")
    for rule, rows in frame.details.items():
        for row in rows:
            edge = row.source if row.target is None else f"{row.source} -> {row.target}"
            print(f"{rule}: FAIL: {row.cause}: {edge}{_places(frame, row.evidence)}")
            print("Action: Remove the violation or review the declared restriction.")
    for rule, reason in frame.explained.items():
        print(f"{rule}: UNKNOWN: {frame.unknown_kinds[rule]}: {reason}")
        print("Action: Resolve the named gap and run again.")
    for gap in frame.gaps:
        if gap.kind is GapKind.RULE_KIND_NOT_PORTED:
            print(f"{gap.subject}: UNKNOWN: rule kind not decided by the core: {gap.reason}")
            print(
                "Action: Do not treat this rule as passed. The core has no port of its kind (#880)."
            )
        else:
            print(f"{gap.subject}: UNKNOWN: {gap.kind}: {gap.reason}")
            print("Action: Resolve the named part and run again (#880).")
