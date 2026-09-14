# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run repository observations and declaration checks."""

import argparse
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from ..accept import unavailable
from ..check.report import render_result, run_report, unknown_result
from ..check.run import run_check
from .config import load_check_config, load_config


def _sha(value: str) -> str:
    if re.fullmatch("[0-9a-f]{40}", value) is None:
        raise argparse.ArgumentTypeError("must be a full lowercase Git SHA")
    return value


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(prog="codekeel")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("report", "check"):
        subparser = commands.add_parser(name)
        subparser.add_argument("--root", type=Path, default=Path.cwd())
        subparser.add_argument("--output", type=Path)
        if name == "check":
            subparser.add_argument("--baseline", type=_sha, required=True)
            subparser.add_argument("--expectation-commit", type=_sha, required=True)
            subparser.add_argument("--head", type=_sha, required=True)
            subparser.add_argument("--expected", required=True)
            subparser.add_argument("--expected-digest", required=True)
            subparser.add_argument(
                "--branch", required=True, help="Fetched origin branch containing the expectation"
            )
            subparser.add_argument(
                "--accepted-branch",
                required=True,
                help="Fetched protected origin branch containing the accepted lock",
            )
            subparser.add_argument(
                "--host-records",
                type=Path,
                help="Replay CI host records; the caller must authenticate this file",
            )
    commands.add_parser("accept")
    command = "arguments"
    subject = "command-line arguments"
    try:
        args = parser.parse_args(argv)
        command = args.command
        if command == "accept":
            result = unavailable()
        else:
            root = args.root.resolve()
            subject = str(root / "codekeel.toml")
            if command == "report":
                config = load_config(root)
                subject = str(root)
                result = run_report(root, config=config, output=args.output)
            else:
                config = load_check_config(root, args.baseline, args.head)
                subject = "check inputs"
                result = run_check(
                    root,
                    config=config,
                    baseline=args.baseline,
                    expectation_commit=args.expectation_commit,
                    head=args.head,
                    expected_path=args.expected,
                    expected_digest=args.expected_digest,
                    branch=args.branch,
                    accepted_branch=args.accepted_branch,
                    host_records_path=args.host_records,
                    environ=os.environ,
                )
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_bytes(render_result(result))
    except Exception as error:
        result = unknown_result(command, subject, error)
    print(render_result(result).decode(), end="")
    return result.exit_code
