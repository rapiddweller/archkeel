# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""Assemble the unchanged legacy command grammar after path dispatch."""

from __future__ import annotations

from .arguments import CLIArguments
from .legacy_parser_base import _DOCS, _Parser
from .legacy_policy_options import add_policy
from .legacy_reports_options import add_reports
from .legacy_tools_options import add_tools


def build_parser() -> _Parser:
    from importlib.metadata import PackageNotFoundError, version

    from rich_argparse import RawDescriptionRichHelpFormatter

    from ..check.ports import Language
    from .arguments import (
        source_language,
    )
    from .config import CONFIG_PATH

    parser = _Parser(
        prog="archkeel",
        description=(
            "Deterministic architecture checks for AI-assisted code.\n\n"
            "Declare the architecture once, let the agent change the code, and let Archkeel\n"
            "observe the result. A terminal shows a readable summary; pipes and --json get JSON."
        ),
        epilog=(
            "Start here:\n"
            "  archkeel explore    see the code as it is, with no contract\n"
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
    parser.set_defaults(command=None, json=False, config=CONFIG_PATH, show=False)
    commands = parser.add_subparsers(dest="command", title="commands", metavar="<command>")
    # The two commands that read a scan configuration from the working tree share one option.
    configured = _Parser(add_help=False)
    configured.add_argument(
        "--config",
        default=CONFIG_PATH,
        help="Scan configuration, relative to --root. Default: archkeel.toml. A second file "
        "scans a second namespace, such as tests, against its own contract (AD-101).",
    )
    # AD-285: init and explore read the same scope options; without them, Python is detected.
    scoped = _Parser(add_help=False)
    scoped.add_argument(
        "--source",
        action="append",
        help="Source directory or TypeScript file relative to --root; repeat for more roots.",
    )
    for option, help_text in (
        ("--namespace", "Dotted namespace for the observed source modules."),
        ("--tsconfig", "TypeScript project config relative to --root."),
    ):
        scoped.add_argument(option, help=help_text)
    scoped.add_argument(
        "--language",
        choices=list(Language),
        type=source_language,
        default=Language.PYTHON,
        help="Source language of --source. Dart needs --source and --namespace (the pubspec "
        "name). TypeScript also needs --tsconfig. Default: python.",
    )

    add_reports(commands, configured, scoped)
    add_policy(commands, configured)
    add_tools(commands, configured, scoped)
    return parser


def _report_option_error(args: CLIArguments) -> str | None:
    """The one priority for report option conflicts, live or saved, before any file is read."""
    from .arguments import ReportMode

    if args.full and args.only is not ReportMode.ARCHITECTURE:
        return "--full requires --only architecture"
    if args.only in {ReportMode.CALLS, ReportMode.ARCHITECTURE} and args.rule is not None:
        return "--rule narrows violations; --only calls or architecture cannot select a rule"
    return None
