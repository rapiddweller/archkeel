# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run repository observations and declaration checks."""

import argparse
import os
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from ..accept import unavailable
from ..analyzer import observe
from ..check.report import render_result, run_report, unknown_result
from ..check.run import run_check
from ..check.validation import invalid_result, run_validate
from ..host.gitlab import load_gitlab_records
from ..render.html import render_architecture_html, render_check_html
from .config import load_check_config, load_config


def _sha(value: str) -> str:
    if re.fullmatch("[0-9a-f]{40}", value) is None:
        raise argparse.ArgumentTypeError("must be a full lowercase Git SHA")
    return value


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def html_path(output: Path, command: str) -> Path:
    """Name an HTML sidecar by JSON stem and command."""
    return output.parent / f"{output.stem}.{command}.html"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(prog="archkeel")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("report", "check", "validate"):
        subparser = commands.add_parser(name)
        subparser.add_argument("--root", type=Path, default=Path.cwd())
        if name == "validate":
            subparser.add_argument("--json", action="store_true")
        else:
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
            subject = str(root / "archkeel.toml")
            if command == "report":
                config = load_config(root)
                subject = str(root)
                result, architecture = run_report(root, config=config, analyzer=observe)
                if architecture is not None:
                    artifact = args.output or root / "test-artifacts/architecture/architecture.json"
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    artifact.write_bytes(architecture)
                    resolved = artifact.resolve()
                    result = replace(
                        result,
                        artifact=(
                            str(resolved.relative_to(root))
                            if resolved.is_relative_to(root)
                            else str(resolved)
                        ),
                    )
                    html_path(artifact, "report").write_bytes(
                        render_architecture_html(
                            result,
                            architecture,
                            repository=root.name,
                            architecture_href=artifact.name,
                        )
                    )
            elif command == "validate":
                config = load_config(root)
                result = run_validate(root, config, observe)
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
                    host=load_gitlab_records,
                    analyzer=observe,
                )
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_bytes(render_result(result))
                    html_path(args.output, "check").write_bytes(
                        render_check_html(
                            result,
                            repository=root.name,
                            result_href=args.output.name,
                        )
                    )
    except Exception as error:
        result = (
            invalid_result(subject, error)
            if command == "validate"
            else unknown_result(command, subject, error)
        )
    print(render_result(result).decode(), end="")
    return result.exit_code
