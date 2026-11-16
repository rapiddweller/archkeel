# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The text of a run for a person: the verdict and its reason first, then what to do (AD-432).

Order: the header (verdict word, exit code and reason), the problems of the command, the next
action, the violations, the rules that wait and the gaps grouped by cause with a count and a few
examples. `--all` lists everything. The text never prints a machine code; the JSON keeps them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from .core_baseline import BaselineResult, BaselineState
from .core_baseline import lines as baseline_lines
from .core_evidence import call_lines
from .core_exit import word_of
from .core_frame import CoreCommand as Command
from .core_frame import CoreFrame, GapKind, RuleStatus, Status
from .core_json import Gap
from .core_words import CAUSE_FIXES, contract_fix, kind_label, plain

SHOWN = 3
#: A named part that is an error of the input, not a limit of the scan: it is printed first.
PROBLEM_KINDS = frozenset(
    {
        GapKind.CONTRACT_REFUSED,
        GapKind.INSIDE_CONTRACT_MISSING,
        GapKind.REPLY_REFUSED,
        GapKind.REPLY_ABSENT,
        GapKind.REQUEST_DIFFERS,
    }
)
VIOLATIONS_SHOWN = 10
MAX_JOBS = 3
SUMMARY_LINES = 15
SUMMARY_VIOLATIONS = 5


def _more(total: int, shown: int, show_all: bool) -> str:
    return "" if show_all or total <= shown else f" and {total - shown} more (--all lists them)"


def _places(frame: CoreFrame, evidence: Sequence[str], limit: int) -> list[str]:
    return [
        f"{location.path}:{location.line}" if location.line else location.path
        for key in evidence
        if (location := frame.locations.get(key))
    ][:limit]


def _invalid(baseline: BaselineResult) -> str:
    """`FILE is not valid: why`, from the one gap that the core names for an invalid file."""
    gap = baseline.gaps[0]
    why = plain(gap.reason).removeprefix(f"{gap.subject}: ")
    return f"{gap.subject} is not valid: {why}"


def reason_of(frame: CoreFrame, code: int) -> str:
    """Why the run exits with `code`: one sentence for the header."""
    counts = Counter(verdict.status for verdict in frame.rules.values())
    total = len(frame.rules)
    refused = any(gap.kind is GapKind.COLLECT for gap in frame.gaps)
    if (baseline := frame.baseline) is not None:
        if baseline.new or baseline.gone:
            return (
                f"the run differs from the baseline: {len(baseline.new)} new, "
                f"{len(baseline.gone)} no longer present"
            )
        if baseline.state == "invalid":
            return f"baseline {_invalid(baseline)}"
        if baseline.state == "not_compared":
            return "the baseline cannot be compared: a part of the run is refused"
        if code == 0 and frame.status is Status.FAIL:
            return f"{sum(frame.violations.values())} violations are accepted by the baseline"
        if code == 2:
            return (
                f"{baseline.accepted_unknowns} accepted items stay UNKNOWN: "
                "a baseline records them and does not decide them"
            )
        return "nothing differs from the baseline"
    if refused:
        return "the scan did not run"
    if not frame.rules and any(gap.kind in PROBLEM_KINDS for gap in frame.gaps):
        return "no rule could be read: see the problem below"
    if word_of(code) != frame.status:
        return f"the run is {frame.status}; the exit is {code} because a file could not be written"
    if frame.status is Status.PASS:
        return f"all {total} rules pass"
    if frame.status is Status.FAIL:
        return f"{sum(frame.violations.values())} violations in {counts[RuleStatus.FAIL]} rules"
    return f"{counts[RuleStatus.UNKNOWN]} of {total} rules cannot be decided"


def header(command: Command, frame: CoreFrame, code: int) -> str:
    """The first line: the word of the exit code, the code and the reason."""
    invalid = frame.baseline is not None and frame.baseline.state is BaselineState.INVALID
    word = "REFUSED" if invalid else word_of(code)
    return f"{command}: {word} -> exit {code} ({reason_of(frame, code)})"


def _next_action(frame: CoreFrame, groups: Sequence[tuple[str, int]]) -> str | None:
    """The top jobs, in the order to do them, each with its count (at most three)."""
    jobs = []
    if frame.details:
        count = sum(len(rows) for rows in frame.details.values())
        jobs.append(f"remove the {count} violations, or review the declared restriction")
    for label, count in groups:
        jobs.append(
            "fix the problem above" if label == "the problem above" else f"{count} x {label}"
        )
    if not jobs and (frame.explained or any(gap.kind is not GapKind.COLLECT for gap in frame.gaps)):
        jobs.append("resolve the named parts below")
    if not jobs:
        return None
    top = jobs[:MAX_JOBS]
    listed = top[0] if len(top) == 1 else "; ".join(f"{n}. {job}" for n, job in enumerate(top, 1))
    more = f" ({len(jobs) - MAX_JOBS} more below)" if len(jobs) > MAX_JOBS else ""
    return f"{listed}{more}. Then run again."


def _violation_lines(frame: CoreFrame, show_all: bool) -> list[str]:
    rows = [(rule, row) for rule, found in frame.details.items() for row in found]
    if not rows:
        return []
    lines = [f"Violations ({len(rows)}):"]
    for rule, row in rows if show_all else rows[:VIOLATIONS_SHOWN]:
        edge = row.source if row.target is None else f"{row.source} -> {row.target}"
        where = ", ".join(_places(frame, row.evidence, SHOWN))
        lines.append(f"  {rule}: {row.cause}: {edge}" + (f" ({where})" if where else ""))
    if more := _more(len(rows), VIOLATIONS_SHOWN, show_all):
        lines.append(f"  {more.strip()}")
    causes = dict.fromkeys(row.cause for _, row in rows)
    lines.extend(
        f"  Fix for '{cause}': {CAUSE_FIXES[cause]}" for cause in causes if cause in CAUSE_FIXES
    )
    return lines


def _group_lines(frame: CoreFrame, show_all: bool) -> tuple[list[str], list[tuple[str, int]]]:
    """The source gaps grouped by cause, the largest group first, and the ranking."""
    groups: dict[str, list[int]] = {}
    for index, gap in enumerate(frame.collection_gaps):
        groups.setdefault(gap.kind, []).append(index)
    ranked = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    lines: list[str] = []
    for kind, members in ranked:
        first = frame.collection_gaps[members[0]]
        lines.append(f"  {len(members)} x {kind_label(kind)}: {plain(first.reason)}")
        shown = members if show_all else members[:SHOWN]
        for index in shown:
            gap = frame.collection_gaps[index]
            where = ", ".join(_places(frame, gap.evidence, 1)) or ", ".join(gap.subjects[:1])
            lines.append(f"      {where}" + (f" ({plain(gap.detail)})" if gap.detail else ""))
        if more := _more(len(members), SHOWN, show_all):
            lines.append(f"      {more.strip()}")
    return lines, [(kind_label(kind), len(members)) for kind, members in ranked]


def _waiting_lines(frame: CoreFrame, show_all: bool) -> list[str]:
    """The UNKNOWN rules grouped by the reason that holds them."""
    groups: dict[str, list[str]] = {}
    for rule, reason in frame.explained.items():
        groups.setdefault(plain(reason), []).append(rule)
    if not groups:
        return []
    lines = [f"Rules that wait ({len(frame.explained)}):"]
    for reason, rules in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        shown = rules if show_all else rules[:SHOWN]
        more = _more(len(rules), SHOWN, show_all)
        lines.append(f"  {len(rules)} rules: {reason}")
        lines.append(f"      {', '.join(shown)}{more}")
    return lines


def _named_lines(frame: CoreFrame, show_all: bool) -> tuple[list[str], list[tuple[str, int]]]:
    """The parts that the core names and does not decide, one group for each kind."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for gap in frame.gaps:
        if gap.kind is not GapKind.COLLECT and gap.kind not in PROBLEM_KINDS:
            groups.setdefault(gap.kind, []).append((gap.subject, plain(gap.reason)))
    ranked = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    lines = (
        [f"Parts that are not decided ({sum(len(rows) for _, rows in ranked)}):"] if ranked else []
    )
    for kind, rows in ranked:
        lines.append(f"  {len(rows)} x {kind_label(kind)}")
        for subject, reason in rows if show_all else rows[:SHOWN]:
            lines.append(
                f"      {reason if subject.startswith('hygiene:') else f'{subject}: {reason}'}"
            )
        if more := _more(len(rows), SHOWN, show_all):
            lines.append(f"      {more.strip()}")
    return lines, [(kind_label(kind), len(rows)) for kind, rows in ranked]


def _problem(gap: Gap, files: Sequence[str]) -> list[str]:
    """One error of the input: the file, what the core read, and what to write instead."""
    reason = plain(gap.reason).removeprefix("refused: ")
    if gap.kind is not GapKind.CONTRACT_REFUSED:
        return [f"Problem: {kind_label(gap.kind)}: {reason}"]
    where = files[0] if len(files) == 1 else "the contract"
    return [f"Problem: {where}: {reason}", f"Fix: {contract_fix(reason)}"]


def _errors(frame: CoreFrame, contract_files: Sequence[str]) -> list[str]:
    """The errors of the input and of the baseline file, each printed once."""
    errors = list(
        dict.fromkeys(
            line
            for gap in frame.gaps
            if gap.kind in PROBLEM_KINDS
            for line in _problem(gap, contract_files)
        )
    )
    baseline = frame.baseline
    if baseline is not None and baseline.state is BaselineState.INVALID:
        errors += [
            f"Problem: baseline {_invalid(baseline)}",
            "Fix: write the file again with --write-baseline FILE. A baseline of release 4.0.1, "
            "or one that was edited, does not fit schema 1.4.0; the run is not compared with it.",
        ]
    return errors


def render(
    command: Command,
    frame: CoreFrame,
    code: int,
    *,
    problems: Sequence[str] = (),
    show_all: bool = False,
    system: Mapping[str, object] | None = None,
    contract_files: Sequence[str] = (),
) -> list[str]:
    """The text of one run, in reading order. `problems` are the errors of the command."""
    gap_lines, ranking = _group_lines(frame, show_all)
    named_lines, named_ranking = _named_lines(frame, show_all)
    ranking = sorted([*ranking, *named_ranking], key=lambda item: -item[1])
    errors = _errors(frame, contract_files)
    refused_file = frame.baseline is not None and frame.baseline.state is BaselineState.INVALID
    out = [header(command, frame, code), *errors, *problems]
    if errors:
        ranking = [("the problem above", len(errors)), *ranking]
    if (action := _next_action(frame, ranking)) is not None:
        out.append(f"Next: {action}")
    if frame.premise is not None:
        out.append(f"Assumption: {frame.premise}")
    if system:
        out.extend(_system(system))
    out.extend(_violation_lines(frame, show_all))
    out.extend(_waiting_lines(frame, show_all))
    if gap_lines:
        out.append(f"Gaps in the scan ({len(frame.collection_gaps)}):")
        out.extend(gap_lines)
    out.extend(named_lines)
    if frame.baseline is not None and not refused_file:
        out.extend(baseline_lines(frame.baseline))
    if (topology := frame.topology) is not None:
        out.append(
            f"Topology: {len(topology.modules)}/{topology.total['modules']} modules, "
            f"{len(topology.edges)}/{topology.total['edges']} edges; "
            f"complete: {topology.complete}; truncated: {topology.truncated}"
        )
    out.extend(call_lines(frame.measures))
    return out


def _system(system: Mapping[str, object]) -> list[str]:
    """The title of a system run, then one line for each part, as the core named it."""
    out = [f"System {system.get('title')}:"]
    for part in system.get("parts", []):  # type: ignore[attr-defined]
        if isinstance(part, dict):
            named = f"{part.get('title')} ({part.get('profile')})"
            out.append(f"  {named}: {part.get('status')}, {len(part.get('rules', []))} rules")
    return out


def refusal(command: Command | None, code: int, message: str, fix: str | None) -> list[str]:
    """The text of a command that could not run: the problem, then the fix."""
    head = f"{command}: " if command is not None else ""
    out = [f"{head}REFUSED -> exit {code}", f"Problem: {message}"]
    if fix:
        out.append(f"Fix: {fix}")
    return out


def summary(
    command: Command,
    frame: CoreFrame,
    code: int,
    contract_files: Sequence[str] = (),
    problems: Sequence[str] = (),
) -> list[str]:
    """The text for a CI log: the header, the errors, the top jobs and a few violations.

    It prints about fifteen lines at most, whatever the size of the run.
    """
    _, ranking = _group_lines(frame, False)
    _, named = _named_lines(frame, False)
    errors = _errors(frame, contract_files)
    ranking = sorted([*ranking, *named], key=lambda item: -item[1])
    if errors:
        ranking = [("the problem above", len(errors)), *ranking]
    out = [header(command, frame, code), *errors, *problems]
    if (action := _next_action(frame, ranking)) is not None:
        out.append(f"Next: {action}")
    rows = [(rule, row) for rule, found in frame.details.items() for row in found]
    for rule, row in rows[:SUMMARY_VIOLATIONS]:
        edge = row.source if row.target is None else f"{row.source} -> {row.target}"
        out.append(f"  {rule}: {row.cause}: {edge}")
    if len(rows) > SUMMARY_VIOLATIONS:
        out.append(f"  and {len(rows) - SUMMARY_VIOLATIONS} more violations")
    out.append("Details: archkeel validate --text (all: --all); machine output: --json")
    return out[:SUMMARY_LINES]
