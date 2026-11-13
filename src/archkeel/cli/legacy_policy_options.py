# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The existing policy command grammar and help."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from .arguments import (
    Command,
)
from .core_only import add_switch as add_core_only
from .legacy_parser_base import (
    _DOCS,
    _observing,
    _Parser,
    _sha,
)
from .native_core import add_switch


def add_policy(commands: argparse._SubParsersAction[_Parser], configured: _Parser) -> None:
    validate = commands.add_parser(
        Command.VALIDATE.value,
        parents=[configured],
        help="Validate the architecture contract for this repository.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Checks the contract structure, package and provenance references, that every\n"
            "component pair is decided by one allowed_dependency or forbidden_dependency\n"
            "rule, rule rationales, the marked component graph against observed imports and,\n"
            "where a page draws one, the marked target graph against the edges the contract\n"
            "permits. Run it after every contract edit; --write-graph first rewrites each\n"
            "marked graph's edges, leaving the rest of the page untouched.\n\n"
            "JSON includes every open component pair by default. --compact-open-decisions\n"
            "lists observed undecided crossings and reports the exact total; omitted pairs\n"
            "remain undecided, and validation verdicts and diagnostics are unchanged.\n\n"
            "A contract that states the target architecture is violated by the code that\n"
            "has yet to reach it. --baseline names a file of those known violations and\n"
            "contract-selected measurement values. The run fails when either drifts.\n"
            "--write-baseline compares an existing file before updating it: reductions may\n"
            "be written, while new or increased debt requires --accept-new.\n\n"
            "--against <ref> classifies every difference from the contract at that Git\n"
            "revision (and, with --baseline, the baseline file there too) as a widening -\n"
            "a new permission or a dropped restriction, including a padded violation or\n"
            "raised or removed measurement budget -\n"
            "or a narrowing, its harmless reverse. A contract the revision does not hold yet\n"
            "is one widening, its introduction. A widening fails unless --amendment names\n"
            "a file binding both recursive contracts and, with v2, both baseline policies;\n"
            "write it with --write-amendment, --decided-by and --rationale.\n\n"
            "Examples:\n"
            "  archkeel validate\n"
            "  archkeel validate --json\n"
            "  archkeel validate --compact-open-decisions --json\n"
            "  archkeel validate --write-graph\n"
            "  archkeel validate --baseline known-violations.json --write-baseline\n"
            "  archkeel validate --baseline known-violations.json --write-baseline --accept-new\n"
            "  archkeel validate --baseline known-violations.json\n"
            "  archkeel validate --against main --amendment widening.json \\\n"
            '    --write-amendment --decided-by "Jordan (architect)" --rationale "..."\n'
            "  archkeel validate --against main --amendment widening.json\n"
            "  archkeel validate --config archkeel-tests.toml\n"
            "  archkeel validate --root mobile --baseline known-violations.json\n\n"
            "Exit codes:\n"
            "  0  the contract is valid for this repository\n"
            "  1  with --baseline: a violation or selected measurement changed; with\n"
            "     --against: an unamended widening\n"
            "  2  validation diagnostics; completed inspections retain their rule verdict\n\n"
            f"Rules: {_DOCS}/rules.md"
        ),
    )
    _observing(validate, None)
    add_core_only(validate)
    for option, help_text in (
        (
            "--compact-open-decisions",
            "List observed undecided crossings with the exact open-pair total and completeness. "
            "Omitted pairs remain undecided. Default: include every open pair.",
        ),
        (
            "--write-graph",
            "Rewrite the edges of each marked graph - the component graph from observed "
            "imports, the target graph from the edges the contract permits - then validate.",
        ),
    ):
        validate.add_argument(option, action="store_true", help=help_text)
    validate.add_argument(
        "--baseline",
        type=Path,
        help="File of known violations and contract-selected measurement values, relative to "
        "--root like the contract, or absolute inside it (AD-103). Fail when either differs "
        "from the current observation.",
    )
    validate.add_argument(
        "--write-baseline",
        action="store_true",
        help="Create or update --baseline after comparing an existing file.",
    )
    validate.add_argument(
        "--accept-new",
        action="store_true",
        help="Allow --write-baseline to accept new or increased debt.",
    )
    validate.add_argument(
        "--against",
        help="Git revision to compare the contract against; fail on an unamended widening.",
    )
    validate.add_argument(
        "--amendment",
        type=Path,
        help="File recording who decided a widening from --against, and why, relative to "
        "--root or absolute inside it. V2 binds contract and baseline policies. Needs --against.",
    )
    validate.add_argument(
        "--write-amendment",
        action="store_true",
        help="Write --amendment for this --against comparison instead of checking it.",
    )
    validate.add_argument("--decided-by", help="Free text for --write-amendment: who decided.")
    validate.add_argument("--rationale", help="Free text for --write-amendment: why.")

    check = commands.add_parser(
        Command.CHECK.value,
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
            "  2  not checked: required evidence is missing or invalid\n\n"
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
    add_switch(check)
    add_core_only(check)
