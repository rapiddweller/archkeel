# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run repository observations and declaration checks."""

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, NoReturn

from rich_argparse import RawDescriptionRichHelpFormatter

from ..accept import unavailable
from ..analyzer import observe
from ..check.onboarding import run_init
from ..check.report import render_result, run_report, unknown_result
from ..check.run import run_check
from ..check.validation import invalid_result, run_validate
from ..host.gitlab import load_gitlab_records
from ..render.html import render_architecture_html, render_check_html
from ..render.summary import check_summary, init_summary, report_summary
from ..render.terminal import print_result, progress
from .config import load_check_config, load_config

_DOCS: Final = "https://github.com/rapiddweller/archkeel/blob/main/docs"


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


def _observing(parser: _Parser, output_help: str | None) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing archkeel.toml. Default: the current directory.",
    )
    if output_help is not None:
        parser.add_argument("--output", type=Path, help=output_help)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the JSON result even in an interactive terminal.",
    )


def build_parser() -> _Parser:
    parser = _Parser(
        prog="archkeel",
        description=(
            "Deterministic architecture checks for AI-assisted code.\n\n"
            "Declare the architecture once, let the agent change the code, and let Archkeel\n"
            "observe the result. A terminal shows a readable summary; pipes and --json get JSON."
        ),
        epilog=(
            "Start here:\n"
            "  archkeel init       draft the contract from the observed imports\n"
            "  archkeel validate   check the contract against this repository\n"
            "  archkeel report     observe the repository and write evidence\n\n"
            f"Rules: {_DOCS}/rules.md\nReference: {_DOCS}/reference.md"
        ),
        formatter_class=RawDescriptionRichHelpFormatter,
    )
    try:
        installed = version("archkeel")
    except PackageNotFoundError:
        # A source checkout on PYTHONPATH has no distribution metadata.
        installed = "from source without package metadata"
    parser.add_argument("--version", action="version", version=f"archkeel {installed}")
    parser.set_defaults(command=None, json=False)
    commands = parser.add_subparsers(dest="command", title="commands", metavar="<command>")

    report = commands.add_parser(
        "report",
        help="Observe the repository and write architecture evidence.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Scans the configured Python sources, evaluates the declared rules and writes the\n"
            "canonical architecture.json with an HTML report next to it. Report never rejects:\n"
            "a rule violation is a FAIL verdict with exit code 0.\n\n"
            "Examples:\n"
            "  archkeel report\n"
            "  archkeel report --output build/architecture.json --json\n\n"
            "Exit codes:\n"
            "  0  the observation is complete\n"
            "  2  unverifiable: configuration, tool or source evidence is missing\n\n"
            f"Rules: {_DOCS}/rules.md"
        ),
    )
    _observing(
        report,
        "Path of architecture.json; the HTML report is written next to it. "
        "Default: test-artifacts/architecture/architecture.json.",
    )

    validate = commands.add_parser(
        "validate",
        help="Validate the architecture contract for this repository.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Checks the contract structure, package and provenance references, that every\n"
            "component pair is observed or forbidden, rule rationales and the marked\n"
            "component graph. Run it after every contract edit.\n\n"
            "Examples:\n"
            "  archkeel validate\n"
            "  archkeel validate --json\n\n"
            "Exit codes:\n"
            "  0  the contract is valid for this repository\n"
            "  2  invalid: each diagnostic names the JSON Pointer to fix\n\n"
            f"Rules: {_DOCS}/rules.md"
        ),
    )
    _observing(validate, None)

    check = commands.add_parser(
        "check",
        help="Check a candidate against its published expectation.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Reobserves the accepted commit and the candidate, compares them with the\n"
            "digest-locked expectation and verifies Git and publication order (M → B → E → H).\n\n"
            "Example:\n"
            "  archkeel check --baseline <B> --expectation-commit <E> --head <H> \\\n"
            "    --expected expectation.json --expected-digest <sha256> \\\n"
            "    --branch origin/feature --accepted-branch origin/main --output result.json\n\n"
            "Exit codes:\n"
            "  0  merge: all five verdicts passed\n"
            "  1  reject: a rule, regression check or order predicate failed\n"
            "  2  unverifiable: required evidence is missing or invalid\n\n"
            f"Protocol: {_DOCS}/reference.md#git-predicate"
        ),
    )
    _observing(check, "Write the check result JSON here and the HTML report next to it.")
    check.add_argument("--baseline", type=_sha, required=True, help="Lock commit B (full SHA).")
    check.add_argument(
        "--expectation-commit",
        type=_sha,
        required=True,
        help="Commit E that publishes the expectation (full SHA).",
    )
    check.add_argument("--head", type=_sha, required=True, help="Candidate commit H (full SHA).")
    check.add_argument("--expected", required=True, help="Repository path of the expectation.")
    check.add_argument("--expected-digest", required=True, help="SHA-256 of the expectation.")
    check.add_argument(
        "--branch", required=True, help="Fetched origin branch containing the expectation."
    )
    check.add_argument(
        "--accepted-branch",
        required=True,
        help="Fetched protected origin branch containing the accepted lock.",
    )
    check.add_argument(
        "--host-records",
        type=Path,
        help="Replay CI host records; the caller must authenticate this file.",
    )

    init = commands.add_parser(
        "init",
        help="Draft archkeel.toml, a closed contract and its architecture page.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Observes the only top-level package, proposes one component per subpackage and\n"
            "forbids every component pair that is not imported today. Every rationale starts\n"
            "as a TODO, so archkeel validate lists the decisions that remain.\n\n"
            "Examples:\n"
            "  archkeel init\n"
            "  archkeel init --source lib/shop --namespace shop --json\n\n"
            "Exit codes:\n"
            "  0  draft written\n"
            "  2  unverifiable: no single package, existing files or incomplete observation\n\n"
            f"Onboarding: {_DOCS}/onboarding.md"
        ),
    )
    _observing(init, None)
    init.add_argument("--source", help="Package directory to scan, relative to --root.")
    init.add_argument("--namespace", help="Dotted Python package name of --source.")
    init.add_argument("--force", action="store_true", help="Replace existing onboarding files.")

    commands.add_parser(
        "accept",
        help="Accept a candidate (not available in this release).",
        formatter_class=RawDescriptionRichHelpFormatter,
        description="Always returns an unverifiable result.\n\nExit codes:\n  2  always",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    command = "arguments"
    subject = "command-line arguments"
    interactive = sys.stdout.isatty()
    artifacts: list[Path] = []
    try:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return 0
        command = args.command
        interactive = interactive and not args.json
        if command == "accept":
            result = unavailable()
        else:
            root = args.root.resolve()
            subject = str(root / "archkeel.toml")
            with progress(f"archkeel {command}: observing {root.name}"):
                if command == "init":
                    subject = str(root)
                    result, files = run_init(
                        root,
                        source=args.source,
                        namespace=args.namespace,
                        force=args.force,
                        analyzer=observe,
                    )
                    for relative, payload in files.items():
                        target = root / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(payload)
                        artifacts.append(target)
                elif command == "report":
                    config = load_config(root)
                    subject = str(root)
                    result, architecture = run_report(root, config=config, analyzer=observe)
                    if architecture is not None:
                        artifact = (
                            args.output or root / "test-artifacts/architecture/architecture.json"
                        )
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
                        report_html = html_path(artifact, "report")
                        report_html.write_bytes(
                            render_architecture_html(
                                result,
                                architecture,
                                repository=root.name,
                                architecture_href=artifact.name,
                            )
                        )
                        artifacts.extend((artifact, report_html))
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
                        check_html = html_path(args.output, "check")
                        check_html.write_bytes(
                            render_check_html(
                                result,
                                repository=root.name,
                                result_href=args.output.name,
                            )
                        )
                        artifacts.extend((args.output, check_html))
    except Exception as error:
        result = (
            invalid_result(subject, error)
            if command == "validate"
            else unknown_result(command, subject, error)
        )
    if interactive:
        summary = (
            check_summary(result)
            if command == "check"
            else init_summary(result)
            if command == "init"
            else report_summary(result)
        )
        print_result(result, summary, artifacts=tuple(str(path) for path in artifacts))
    else:
        print(render_result(result).decode(), end="")
    return result.exit_code
