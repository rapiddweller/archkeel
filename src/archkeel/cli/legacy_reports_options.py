# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The existing reports command grammar and help."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from .arguments import (
    Command,
    ReportMode,
    report_mode,
)
from .core_only import add_switch as add_core_only
from .legacy_parser_base import (
    _DOCS,
    _SNAPSHOT_PATH,
    _collector_output_limit,
    _observing,
    _Parser,
)
from .native_core import add_switch


def add_reports(
    commands: argparse._SubParsersAction[_Parser], configured: _Parser, scoped: _Parser
) -> None:
    report = commands.add_parser(
        Command.REPORT.value,
        parents=[configured],
        help="Observe the repository and write architecture evidence.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Scans the configured Python sources, evaluates the declared rules and writes the\n"
            "canonical architecture.json with an HTML report next to it. Report never rejects:\n"
            "a rule violation is a FAIL verdict with exit code 0. architecture.json always\n"
            "carries every violation; --only, --rule and --component narrow what the HTML page\n"
            "and --json's own filtered_violations show, never what was judged (AD-60).\n"
            "--input queries a saved snapshot without scanning or writing files. Its source\n"
            "identity describes recorded evidence, not the current working tree.\n\n"
            "Examples:\n"
            "  archkeel report\n"
            "  archkeel report --output build/architecture.json --json\n"
            "  archkeel report --only violations --rule DEP-STORE-NO-MONEY --json\n"
            "  archkeel report --component store\n"
            "  archkeel report --input build/architecture.json --only architecture \\\n"
            "    --component COMP-STORE --json\n"
            "  archkeel report --config archkeel-tests.toml \\\n"
            "    --output test-artifacts/tests/architecture.json\n"
            "  archkeel report --timings build/timings.json\n\n"
            "Exit codes:\n"
            "  0  the observation is complete\n"
            "  2  not checked: configuration, tool or source evidence is missing, or --rule or\n"
            "     --component names a rule or component this contract does not declare\n\n"
            f"Rules: {_DOCS}/rules.md"
        ),
    )
    _observing(
        report,
        "Path of architecture.json; the HTML report is written next to it. "
        f"Default: {_SNAPSHOT_PATH}.",
    )
    report.set_defaults(root=None, config=None, timings=None)
    add_switch(report)
    add_core_only(report)
    report.add_argument(
        "--input",
        type=Path,
        help="Query a saved snapshot of architecture.json; no scan or file output. Recorded "
        "source identity does not verify the current working tree. Conflicts with --root, "
        "--config, --baseline, --output and --timings.",
    )
    report.add_argument(
        "--timings",
        type=Path,
        help="Write phase seconds and work counters as JSON after a successful live report. "
        "Nothing is measured without this flag. Conflicts with --input.",
    )
    report.add_argument(
        "--baseline",
        type=Path,
        help="Compare findings with this read-only validation baseline, relative to --root.",
    )
    report.add_argument(
        "--only",
        choices=list(ReportMode),
        type=report_mode,
        help="violations: show only the declared-rule violations table, hiding component flow, "
        "component communication, review claims and size and coupling, for a small review "
        "surface on a large repository (AD-60). calls: list every unresolved and partially "
        "resolved call with its status, caller, path, line, expression, reason and component, "
        "as --json's filtered_calls and one HTML table; combines with --component, not --rule "
        "(AD-100). architecture: project authenticated ownership, permissions, use and "
        "required relationships; combines with --component, not --rule.",
    )
    report.add_argument(
        "--full",
        action="store_true",
        help="With --only architecture, include projection, violations and UNKNOWN records.",
    )
    report.add_argument(
        "--rule",
        help="Show only violations naming this rule id - top-level, or <component>:<rule id> "
        "for one an inside declares (AD-36). Unknown to this contract: exit 2.",
    )
    report.add_argument(
        "--component",
        help="Narrow the violations, or with --only calls the calls, by top-level label. "
        "With --only architecture or violations, use an exact component id or scoped "
        "label from architecture_projection.components; violations include local findings "
        "and descendants. With violations, top-level labels take precedence. Otherwise, "
        "use a top-level label for crossing endpoints or --only calls. "
        "Unknown to this contract: exit 2.",
    )

    explore = commands.add_parser(
        Command.EXPLORE.value,
        parents=[scoped],
        help="See the code as it is: an observed overview that needs no contract.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Observes the one top-level Python package, or the --source and --namespace you pass,\n"
            "and groups its modules by layout. It needs no archkeel.toml and no contract, and it\n"
            "writes nothing into the repository. No rule is declared, so the result says target:\n"
            "unavailable and gives no rule verdict. TypeScript and Dart need the scope options\n"
            "because they are not detected (AD-285).\n\n"
            "Examples:\n"
            "  archkeel explore\n"
            "  archkeel explore --root ../service --output ../service-explore\n"
            "  archkeel explore --language dart --source lib --namespace my_app\n\n"
            "Exit codes:\n"
            "  0  the observation is complete\n"
            "  2  not checked: no single Python package, no Git commit, an output inside the\n"
            "     repository, or incomplete coverage\n\n"
            f"Start here: {_DOCS}/getting-started.md"
        ),
    )
    _observing(
        explore,
        "Folder for architecture.json and the report pages, outside the repository. "
        "Default: $XDG_CACHE_HOME/archkeel/explore/<root hash> (~/.cache by default).",
    )
    _collector_output_limit(explore)
