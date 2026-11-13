# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

"""The existing tools command grammar and help."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from ..ir.facts_codec import DEFAULT_RESPONSE_LIMIT_BYTES
from .arguments import (
    Command,
    SkillAction,
    installation_agent,
    skill_action,
)
from .legacy_parser_base import (
    _DOCS,
    _SNAPSHOT_PATH,
    _collector_output_limit,
    _observing,
    _Parser,
    _positive_bytes,
)
from .skill import InstallationAgent


def add_tools(
    commands: argparse._SubParsersAction[_Parser], configured: _Parser, scoped: _Parser
) -> None:
    init = commands.add_parser(
        Command.INIT.value,
        parents=[scoped],
        help="Draft archkeel.toml, a closed contract and its architecture page.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Observes the configured source roots and proposes components from their layout.\n"
            "Python can detect its top-level package from pyproject.toml or package markers.\n"
            "It writes no dependency rule: every undecided ordered component pair remains open.\n"
            "The default JSON lists observed crossings and reports the exact total; --full\n"
            "includes unobserved pairs too.\n\n"
            "Examples:\n"
            "  archkeel init\n"
            "  archkeel init --source lib/shop --namespace shop --json\n"
            "  archkeel init --language dart --source lib --namespace my_app\n"
            "  archkeel init --language typescript --source src --namespace app "
            "--tsconfig tsconfig.json\n\n"
            "Exit codes:\n"
            "  0  draft written\n"
            "  2  not checked: no single package, existing files or incomplete observation\n\n"
            f"Start here: {_DOCS}/getting-started.md\n"
            f"Onboarding: {_DOCS}/onboarding.md"
        ),
    )
    _observing(init, None)
    init.add_argument(
        "--full",
        action="store_true",
        help="Include every open component pair in JSON, including unobserved pairs.",
    )
    init.add_argument(
        "--collector-output-limit-bytes",
        type=_positive_bytes,
        metavar="BYTES",
        help="Finite collector stdout limit in bytes, saved in archkeel.toml. "
        f"Default: {DEFAULT_RESPONSE_LIMIT_BYTES} (64 MiB). Higher values need more memory.",
    )
    init.add_argument(
        "--collector-timeout-seconds",
        type=int,
        metavar="SECONDS",
        help="Positive collector deadline in seconds, saved in archkeel.toml. Default: 300.",
    )
    init.add_argument(
        "--collector-argv",
        nargs="+",
        metavar="ARG",
        help="Collector command and arguments. Every language defaults to its own collector "
        "inside this package. On Windows, pass an executable and its script, not a .cmd shim.",
    )
    for flag, help_text in (
        ("--force", "Replace existing onboarding files."),
        (
            "--adopt",
            "Record each observed crossing as an agent requires entry, forbid the other pairs, "
            "and write architecture-baseline.json with today's violations.",
        ),
    ):
        init.add_argument(flag, action="store_true", help=help_text)

    skill = commands.add_parser(
        Command.SKILL.value,
        help="Install the Archkeel instructions for a coding agent.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Writes .claude/skills/archkeel/SKILL.md for Claude Code or\n"
            ".agents/skills/archkeel/SKILL.md for Codex. Reinstalling updates the skill.\n"
            "Codex also removes a legacy managed AGENTS.md section, preserving user text.\n\n"
            "Examples:\n"
            "  archkeel skill install claude\n"
            "  archkeel skill install codex --root ../service\n\n"
            "Exit codes:\n"
            "  0  instructions written\n"
            "  2  the target file could not be updated\n\n"
            f"Onboarding: {_DOCS}/onboarding.md"
        ),
    )
    skill.add_argument(
        "action", choices=list(SkillAction), type=skill_action, help="The only supported action."
    )
    skill.add_argument(
        "agent",
        choices=list(InstallationAgent),
        type=installation_agent,
        help="Coding agent to instruct.",
    )
    _observing(skill, None)

    guide: argparse.ArgumentParser = commands.add_parser(
        Command.GUIDE.value,
        parents=[configured],
        help="Write a Markdown guide that explains the architecture contract.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Reads the architecture contract and writes docs/architecture/contract-guide.md.\n"
            "The guide needs no source scan and never changes the contract. The same contract\n"
            "gives the same bytes, so --check can keep the file fresh in CI.\n\n"
            "Examples:\n"
            "  archkeel guide\n"
            "  archkeel guide --check\n\n"
            "Exit codes:\n"
            "  0  guide written, or --check finds the file up to date\n"
            "  1  --check finds the file missing or different\n"
            "  2  no contract, or the contract cannot be read\n\n"
            f"Reference: {_DOCS}/reference.md"
        ),
    )
    guide.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Default: the current directory.",
    )
    guide.add_argument(
        "--output",
        type=Path,
        help="Guide file, relative to --root. Default: docs/architecture/contract-guide.md.",
    )
    guide.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; exit 1 when the guide file is missing or differs from the contract.",
    )

    view = commands.add_parser(
        Command.VIEW.value,
        help="Check a view spec against a saved architecture.json, or draw it in the Explorer.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Checks each node, edge and step of a view spec against one saved snapshot. Each\n"
            "reference is proven (observed, with evidence), declared (contract), claim (author\n"
            "text, not checked), unknown (the snapshot cannot decide) or missing. A proven step\n"
            "is one direct edge of its kind: structure, not runtime order. The spec\n"
            "names the digests of the snapshot it was written for (AD-284).\n\n"
            "show prints the same result and writes the Explorer report of the snapshot with\n"
            "the checked view drawn in it, to --output or a cache folder (AD-287). It writes\n"
            "nothing when the check did not run (exit 2). Stderr names the written page.\n\n"
            "Examples:\n"
            "  archkeel view check flow.json\n"
            "  archkeel view check flow.json --snapshot build/architecture.json --json\n"
            "  archkeel view check flow.json --strict\n"
            "  archkeel view show flow.json --output build/flow\n\n"
            "Exit codes:\n"
            "  0  no reference is missing (with --strict: and none is unknown)\n"
            "  1  a reference is missing, or unknown with --strict\n"
            "  2  not checked: invalid spec or snapshot, or the spec names another snapshot\n\n"
            f"Reference: {_DOCS}/reference.md#checked-views"
        ),
    )
    # The checked options are shared; only show writes files, so only show takes --output.
    viewed = _Parser(add_help=False)
    viewed.add_argument("spec", type=Path, help="View spec JSON (schema/view-spec.schema.json).")
    viewed.add_argument(
        "--snapshot",
        type=Path,
        default=_SNAPSHOT_PATH,
        help=f"Saved architecture.json. Default: {_SNAPSHOT_PATH}.",
    )
    for option, help_text in (
        ("--strict", "Also reject each unknown reference."),
        ("--json", "Print the JSON result even in an interactive terminal."),
    ):
        viewed.add_argument(option, action="store_true", help=help_text)
    actions = view.add_subparsers(dest="view_action", required=True, metavar="action")
    actions.add_parser("check", parents=[viewed], help="Print the check result.")
    show = actions.add_parser(
        "show", parents=[viewed], help="Print the check result and draw it in the Explorer."
    )
    show.add_argument(
        "--output",
        type=Path,
        help="Folder for the report pages and a copy of the snapshot. Default: "
        "$XDG_CACHE_HOME/archkeel/view/<source digest>/.",
    )
    show.set_defaults(show=True)

    story = commands.add_parser(
        Command.STORY.value,
        help="Propose the path of a story from a saved architecture.json.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "trace lists candidate paths over the call graph of a saved snapshot, from one\n"
            "function or method to another (--to), or to the farthest functions. A hop is\n"
            "proven (a resolved call) or a claim (a partial call, marked as a seam). Unresolved\n"
            "calls are listed as seams of their function. Each function has its lane and the\n"
            "external systems whose client library its module imports. The result is one JSON\n"
            "document. You choose a path and write the words; view check proves the story\n"
            "(AD-291).\n\n"
            "Examples:\n"
            "  archkeel story trace --from shop.cli.main.main --to shop.render.text._indent\n"
            "  archkeel story trace --from shop.cli.main.main --snapshot build/arch.json\n\n"
            "Exit codes:\n"
            "  0  the trace ran; no path is an empty list\n"
            "  2  invalid input: a name not in the snapshot, a bad option, an invalid snapshot\n\n"
            f"Reference: {_DOCS}/reference.md#stories"
        ),
    )
    story_actions = story.add_subparsers(dest="story_action", required=True, metavar="action")
    trace = story_actions.add_parser("trace", help="Print the candidate paths as JSON.")
    trace.add_argument(
        "--from",
        dest="source",
        required=True,
        metavar="NAME",
        help="Qualified name of the first function or method.",
    )
    trace.add_argument(
        "--to", dest="target", metavar="NAME", help="Qualified name of the last function or method."
    )
    trace.add_argument(
        "--snapshot",
        type=Path,
        default=_SNAPSHOT_PATH,
        help=f"Saved architecture.json. Default: {_SNAPSHOT_PATH}.",
    )
    trace.add_argument("--max-paths", type=int, default=5, help="Paths to list. Default: 5.")
    trace.add_argument("--max-hops", type=int, default=12, help="Longest path. Default: 12.")
    trace.add_argument(
        "--json", action="store_true", help="Print the JSON result even in an interactive terminal."
    )

    studio = commands.add_parser(
        Command.STUDIO.value,
        parents=[scoped],
        help="Open ArchKeel Studio: the local web app for the code as it is.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Serves the Studio on 127.0.0.1 and opens it in the browser. The printed URL carries\n"
            "a token for this run; without it each request gets 403. Studio runs explore, with\n"
            "the scope options of explore, into a private cache folder of this run and writes\n"
            "nothing into the repository. The static report stays the CI and Pages artifact\n"
            "(AD-290).\n\n"
            "A running server writes studio.json (pid, URL, port) into the explore cache folder\n"
            "of the root, readable by you only. A second start for the same root prints the same\n"
            "URL and starts no second server. The scope options of the first start stay in force.\n"
            "An agent starts it in the background with --no-open and --idle-exit.\n\n"
            "Examples:\n"
            "  archkeel studio\n"
            "  archkeel studio --root ../service --no-open --idle-exit 60\n"
            "  archkeel studio --stop --root ../service\n"
            "  archkeel studio --language typescript --source src --namespace shop \\\n"
            "    --tsconfig tsconfig.json\n\n"
            "Exit codes:\n"
            "  0  stopped by Ctrl-C, SIGTERM or --idle-exit; --stop done; or server reused\n"
            "  1  --stop: the server still runs after 15 seconds\n"
            "  2  the server could not start"
        ),
    )
    _collector_output_limit(studio)
    studio.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Repository root. Default: this folder."
    )
    studio.add_argument(
        "--no-open", action="store_true", help="Print the URL; do not open a browser."
    )
    studio.add_argument(
        "--stop",
        action="store_true",
        help="Stop the running Studio of --root (SIGTERM) and exit. It checks first that the "
        "server answers as a Studio.",
    )
    studio.add_argument(
        "--idle-exit",
        type=float,
        default=0.0,
        metavar="MINUTES",
        help="Stop when no request came for MINUTES. Default: 0 (never).",
    )
    studio.add_argument(
        "--agent",
        dest="chat_agent",
        choices=list(InstallationAgent),
        type=installation_agent,
        default=InstallationAgent.CLAUDE,
        help="Coding agent that answers the chat. Default: claude (read and search tools only). "
        "codex also runs shell commands in its read-only sandbox, so it is an opt-in. The agent "
        "runs on your own sign-in.",
    )
