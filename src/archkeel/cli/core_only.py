# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""L-121: dispatch to the scan frame without importing the Python engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NoReturn

from .core_binary import locate_core
from .core_frame import (
    STAGE_ONE_VARIABLE,
    CheckKind,
    CoreError,
    CoreFrame,
    GapKind,
    Status,
    Switch,
    read_frame,
)
from .core_frame import CoreCommand as Command
from .native_scan import SCAN_PROTOCOL, exchange

VARIABLE: Final = "ARCHKEEL_CORE_ONLY"


# The process exit of the core is not a command verdict (0 and 3 describe frame completeness).
EXIT_CODES: Final[Mapping[Status, int]] = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}


class Options(argparse.Namespace):
    command: Command
    root: Path | None = None
    config: str = "archkeel.toml"
    json: bool = False
    text: bool = False
    native_core: bool = False
    core_only: bool = False
    output: Path | None = None
    input: Path | None = None
    only: str | None = None
    full: bool = False
    html: bool = False


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CoreError(message)


def requested(argv: Sequence[str], environ: Mapping[str, str]) -> bool:
    return (
        "--core-only" in argv
        or any(argument.startswith("--core-only=") for argument in argv)
        or environ.get(VARIABLE, Switch.UNSET) not in {Switch.UNSET, Switch.OFF}
    )


def add_switch(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--core-only",
        action="store_true",
        help=f"Render only the core scan verdict, without the Python engine. Also {VARIABLE}=1. "
        "PASS exits 0, FAIL exits 1, UNKNOWN and refused forms exit 2 (AD-422).",
    )


def active_checks(_options: Options) -> tuple[CheckKind, ...]:
    """Every existing check authenticates a lock and evaluates an expectation (AD-399, #1103).

    Ratchets and selected changes are inside authenticated bytes, not command-line choices.
    There is no verdict-only form of the shipped check command.
    """
    return tuple(CheckKind)


def parse(argv: Sequence[str]) -> Options:
    parser = Parser(prog="archkeel --core-only", description=__doc__)
    parser.add_argument("command", type=Command, choices=list(Command))
    parser.add_argument("--core-only", action="store_true")
    parser.add_argument("--native-core", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--config", default="archkeel.toml")
    form = parser.add_mutually_exclusive_group()
    for flag in ("json", "text"):
        form.add_argument(f"--{flag}", action="store_true")
    for flag in ("full", "html"):
        parser.add_argument(f"--{flag}", action="store_true")
    for flag in ("output", "input"):
        parser.add_argument(f"--{flag}", type=Path)
    parser.add_argument("--only")
    # These inputs select checks or data that scan does not carry. Never ignore them.
    for flag in (
        "baseline",
        "expectation-commit",
        "head",
        "expected",
        "expected-digest",
        "branch",
        "accepted-branch",
        "host-records",
        "against",
        "amendment",
        "decided-by",
        "rationale",
        "timings",
        "rule",
        "component",
    ):
        parser.add_argument(f"--{flag}")
    for flag in (
        "write-graph",
        "write-baseline",
        "accept-new",
        "write-amendment",
        "compact-open-decisions",
    ):
        parser.add_argument(f"--{flag}", action="store_true")
    options, extra = parser.parse_known_args(argv, Options())
    if extra:
        raise CoreError(
            f"unsupported core-only arguments: {' '.join(extra)}; run without --core-only"
        )
    return options


def run(argv: Sequence[str]) -> int:
    as_json = "--json" in argv or (not sys.stdout.isatty() and "--text" not in argv)
    try:
        try:
            Switch(os.environ.get(VARIABLE, ""))
        except ValueError as error:
            raise CoreError(f"{VARIABLE} must be 0 or 1") from error
        options = parse(argv)
        if options.native_core or Switch(os.environ.get(STAGE_ONE_VARIABLE, "")) is Switch.ON:
            raise CoreError("--core-only and the stage-1 --native-core switch cannot be combined")
        if options.command is Command.CHECK:
            names = "; ".join(active_checks(options))
            raise CoreError(f"check requires {names}; not ported (#1103); run without --core-only")
        if options.command is Command.EXPLORE:
            raise CoreError("explore needs the full report payload; run without --core-only")
        if options.output is not None or options.html:
            raise CoreError(
                "the full HTML report and architecture.json are not carried; "
                "run without --core-only"
            )
        if options.input is not None or options.only is not None or options.full:
            raise CoreError(
                "saved reports and report projections are not carried; run without --core-only"
            )
        selected = {key: value for key, value in vars(options).items() if value}
        allowed = {"command", "core_only", "root", "config", "json", "text"}
        if unsupported := sorted(selected.keys() - allowed):
            raise CoreError(
                f"core-only scan does not carry {', '.join(unsupported)}; run without --core-only"
            )
        request = {
            "protocol": SCAN_PROTOCOL,
            "root": str((options.root or Path.cwd()).resolve()),
            "config": options.config,
            "root_only": True,
            "discover_root": options.root is None,
        }
        stdout, code = exchange(str(locate_core()), "scan", json.dumps(request).encode())
        frame = read_frame(stdout, code, scan=True, require_protocol=True)
        result: dict[str, object] = {
            "command": options.command,
            "status": frame.status,
            "exit_code": EXIT_CODES[frame.status],
            "frame": json.loads(stdout),
            "gaps": [
                {"kind": gap.kind, "subject": gap.subject, "reason": gap.reason}
                for gap in frame.gaps
            ],
        }
        if as_json:
            print(json.dumps(result))
        else:
            render_text(options.command, frame)
        return EXIT_CODES[frame.status]
    except (CoreError, OSError, ValueError) as error:
        refusal = {"status": Status.UNKNOWN, "exit_code": 2, "refusal": str(error)}
        print(
            json.dumps(refusal)
            if as_json
            else f"UNKNOWN: {error}\nAction: Correct the named cause and run again."
        )
        return 2


def render_text(command: Command, frame: CoreFrame) -> None:
    print(f"{command}: {frame.status}")
    if not frame.complete_scope:
        print(f"Scope: {frame.scope}")
        print("Action: Resolve the named scope gap and run again.")
    for rule, rows in frame.details.items():
        for row in rows:
            edge = row.source if row.target is None else f"{row.source} -> {row.target}"
            places = []
            for key in row.evidence:
                if location := frame.locations.get(key):
                    places.append(
                        f"{location.path}:{location.line}" if location.line else location.path
                    )
            where = f" ({', '.join(places)})" if places else ""
            print(f"{rule}: FAIL: {row.cause}: {edge}{where}")
            print("Action: Remove the violation or review the declared restriction.")
    for rule, reason in frame.explained.items():
        print(f"{rule}: UNKNOWN: {frame.unknown_kinds[rule]}: {reason}")
        print("Action: Resolve the named gap and run again.")
    for gap in frame.gaps:
        if gap.kind is GapKind.RULE_KIND_NOT_PORTED:
            print(f"{gap.subject}: UNKNOWN: rule kind not decided by the core: {gap.reason}")
            print("Action: Run without --core-only for this rule kind.")
        else:
            print(f"{gap.subject}: UNKNOWN: {gap.kind}: {gap.reason}")
            print("Action: Run without --core-only for this part.")
