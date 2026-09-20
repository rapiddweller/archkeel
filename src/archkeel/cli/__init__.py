# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run repository observations and declaration checks."""

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, NoReturn

from rich_argparse import RawDescriptionRichHelpFormatter

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
from .skill import install_skill

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
        help="Repository root. Default: the current directory.",
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
            "a rule violation is a FAIL verdict with exit code 0. architecture.json always\n"
            "carries every violation; --only, --rule and --component narrow what the HTML page\n"
            "and --json's own filtered_violations show, never what was judged (AD-60).\n\n"
            "Examples:\n"
            "  archkeel report\n"
            "  archkeel report --output build/architecture.json --json\n"
            "  archkeel report --only violations --rule DEP-STORE-NO-MONEY --json\n"
            "  archkeel report --component store\n\n"
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
        "Default: test-artifacts/architecture/architecture.json.",
    )
    report.add_argument(
        "--only",
        choices=["violations"],
        help="Show only the declared-rule violations table: hide component flow, component "
        "communication, review claims and size and coupling, for a small review surface on a "
        "large repository. --json also stops here, without those sections' data (AD-60).",
    )
    report.add_argument(
        "--rule",
        help="Show only violations naming this rule id - top-level, or <component>:<rule id> "
        "for one an inside declares (AD-36). Unknown to this contract: exit 2.",
    )
    report.add_argument(
        "--component",
        help="Show only violations whose crossing touches this component, as source or "
        "target. Unknown to this contract: exit 2.",
    )

    validate = commands.add_parser(
        "validate",
        help="Validate the architecture contract for this repository.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Checks the contract structure, package and provenance references, that every\n"
            "component pair is decided by one allowed_dependency or forbidden_dependency\n"
            "rule, rule rationales, the marked component graph against observed imports and,\n"
            "where a page draws one, the marked target graph against the edges the contract\n"
            "permits. Run it after every contract edit; --write-graph first rewrites each\n"
            "marked graph's edges, leaving the rest of the page untouched.\n\n"
            "A contract that states the target architecture is violated by the code that\n"
            "has yet to reach it. --baseline names a file of those known violations: the\n"
            "run then fails only on a violation the file does not state, and on one it\n"
            "states that nobody violates any more, so the budget only shrinks. Write the\n"
            "file with --write-baseline, review it, and commit it.\n\n"
            "--against <ref> classifies every difference from the contract at that Git\n"
            "revision (and, with --baseline, the baseline file there too) as a widening -\n"
            "a new permission or a dropped restriction, including a padded baseline entry -\n"
            "or a narrowing, its harmless reverse. A widening fails unless --amendment names\n"
            "a file recording who decided it and why, bound to this exact before/after pair;\n"
            "write it with --write-amendment, --decided-by and --rationale.\n\n"
            "Examples:\n"
            "  archkeel validate\n"
            "  archkeel validate --json\n"
            "  archkeel validate --write-graph\n"
            "  archkeel validate --baseline known-violations.json --write-baseline\n"
            "  archkeel validate --baseline known-violations.json\n"
            "  archkeel validate --against main --amendment widening.json \\\n"
            '    --write-amendment --decided-by "Jordan (architect)" --rationale "..."\n'
            "  archkeel validate --against main --amendment widening.json\n\n"
            "Exit codes:\n"
            "  0  the contract is valid for this repository\n"
            "  1  with --baseline: a violation is new, or a known one is resolved; with\n"
            "     --against: an unamended widening\n"
            "  2  invalid: each diagnostic names the JSON Pointer to fix\n\n"
            f"Rules: {_DOCS}/rules.md"
        ),
    )
    _observing(validate, None)
    validate.add_argument(
        "--write-graph",
        action="store_true",
        help="Rewrite the edges of each marked graph - the component graph from observed "
        "imports, the target graph from the edges the contract permits - then validate.",
    )
    validate.add_argument(
        "--baseline",
        type=Path,
        help="File of known violations. Fail only on a violation it does not state, or on "
        "one it states that nobody violates any more.",
    )
    validate.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write today's violations to --baseline instead of comparing them.",
    )
    validate.add_argument(
        "--against",
        help="Git revision to compare the contract against; fail on an unamended widening.",
    )
    validate.add_argument(
        "--amendment",
        type=Path,
        help="File recording who decided a widening from --against, and why. Needs --against.",
    )
    validate.add_argument(
        "--write-amendment",
        action="store_true",
        help="Write --amendment for this --against comparison instead of checking it.",
    )
    validate.add_argument("--decided-by", help="Free text for --write-amendment: who decided.")
    validate.add_argument("--rationale", help="Free text for --write-amendment: why.")

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

    init = commands.add_parser(
        "init",
        help="Draft archkeel.toml, a closed contract and its architecture page.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Observes the only top-level package, or the one pyproject.toml's [project] name\n"
            "names when several sit side by side, and proposes one component per subpackage.\n"
            "It writes no dependency rule: every ordered component pair is an open decision,\n"
            "reported by import weight for the architect to allow or forbid.\n\n"
            "Examples:\n"
            "  archkeel init\n"
            "  archkeel init --source lib/shop --namespace shop --json\n\n"
            "Exit codes:\n"
            "  0  draft written\n"
            "  2  not checked: no single package, existing files or incomplete observation\n\n"
            f"Onboarding: {_DOCS}/onboarding.md"
        ),
    )
    _observing(init, None)
    init.add_argument("--source", help="Package directory to scan, relative to --root.")
    init.add_argument("--namespace", help="Dotted Python package name of --source.")
    init.add_argument("--force", action="store_true", help="Replace existing onboarding files.")

    skill = commands.add_parser(
        "skill",
        help="Install the Archkeel instructions for a coding agent.",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=(
            "Writes .claude/skills/archkeel/SKILL.md for Claude Code or a marked section in\n"
            "AGENTS.md for Codex. Running it again replaces the section in place.\n\n"
            "Examples:\n"
            "  archkeel skill install claude\n"
            "  archkeel skill install codex --root ../service\n\n"
            "Exit codes:\n"
            "  0  instructions written\n"
            "  2  the target file could not be updated\n\n"
            f"Onboarding: {_DOCS}/onboarding.md"
        ),
    )
    skill.add_argument("action", choices=["install"], help="The only supported action.")
    skill.add_argument("agent", choices=["claude", "codex"], help="Coding agent to instruct.")
    _observing(skill, None)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    command = "arguments"
    subject = "command-line arguments"
    interactive = sys.stdout.isatty()
    artifacts: list[Path] = []
    files: dict[str, bytes] = {}
    try:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return 0
        command = args.command
        interactive = interactive and not args.json
        if command == "skill":
            path = install_skill(args.root.resolve(), args.agent)
            print(
                f"Installed Archkeel instructions: {path}"
                if interactive
                else json.dumps({"command": "skill", "exit_code": 0, "path": str(path)})
            )
            return 0
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
            elif command == "report":
                config = load_config(root)
                subject = str(root)
                result, architecture = run_report(
                    root,
                    config=config,
                    analyzer=observe,
                    only_violations=args.only == "violations",
                    rule=args.rule,
                    component=args.component,
                )
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
                if args.write_baseline and args.baseline is None:
                    parser.error("--write-baseline needs --baseline to name the file to write")
                if args.amendment is not None and args.against is None:
                    parser.error("--amendment needs --against to name the compared revision")
                if args.write_amendment and args.against is None:
                    parser.error("--write-amendment needs --against to name the compared revision")
                if args.write_amendment and args.amendment is None:
                    parser.error("--write-amendment needs --amendment to name the file to write")
                if args.write_amendment and (not args.decided_by or not args.rationale):
                    parser.error("--write-amendment needs --decided-by and --rationale")
                result, files = run_validate(
                    root,
                    config,
                    observe,
                    write_graph=args.write_graph,
                    # Resolved here so the file is read and written at one path, whatever
                    # --root says; the result then names the path the user will open.
                    baseline=None if args.baseline is None else args.baseline.resolve(),
                    write_baseline=args.write_baseline,
                    against=args.against,
                    amendment=None if args.amendment is None else args.amendment.resolve(),
                    write_amendment=args.write_amendment,
                    decided_by=args.decided_by,
                    rationale=args.rationale,
                )
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
            for relative, payload in files.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                artifacts.append(target)
    # The CLI contract is a JSON result with exit 2, never a bare traceback, for any failure.
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
