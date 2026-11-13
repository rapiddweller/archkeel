# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390: read the frame of `archkeel-core check` into typed values, and fail closed.

The reader accepts exactly one JSON object with each field of the frame and no other field. It
refuses a missing field, an unknown field, an unknown status word, a status PASS with zero rules,
a rule status without its explaining row, a second document after the frame, and an exit code
that does not fit the frame (0 only without a named part, 3 only with one). A refused frame is a
`CoreError`: the run then has no verdict, never a verdict of one side.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeVar


class Status(StrEnum):
    """The status of a run."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RuleStatus(StrEnum):
    """The status of a rule: a permission declaration has no verdict."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DECLARATION = "DECLARATION"


class GapKind(StrEnum):
    """Why a part of a run has no decision of the core."""

    PRODUCER_NOT_VERIFIED = "producer_not_verified"
    REPLY_REFUSED = "reply_refused"
    REPLY_ABSENT = "reply_absent"
    RULE_KIND_NOT_PORTED = "rule_kind_not_ported"
    BASE = "base"
    INSIDE_CONTRACT_MISSING = "inside_contract_missing"
    INSIDE_RULE = "inside_rule"
    TREE_SCOPE = "tree_scope"
    UML_TARGET = "uml_target"
    SCOPE_PROOF = "scope_proof"
    CONTRACT_REFUSED = "contract_refused"
    SECTION = "section"
    REPORT = "report"
    OTHER = "other"
    # The reasons of the shell: the core did not run on this run.
    PYTHON_INCOMPLETE = "python_incomplete"
    REPLIES = "replies"
    EXTERNAL_COLLECTOR = "external_collector"
    # AD-406: the scan request: the core did not run the collector, or it derived another
    # request than the shell sent to its collector.
    COLLECT = "collect"
    REQUEST_DIFFERS = "request_differs"


class Switch(StrEnum):
    """The values of the switch variable: unset, off and on."""

    UNSET = ""
    OFF = "0"
    ON = "1"


class _ContractRead(StrEnum):
    RULES = "rules"
    MISSING = "missing"
    REFUSED = "refused"


class _ReplyRead(StrEnum):
    FILES = "files"
    REFUSED = "refused"
    ABSENT = "absent"


class _CollectRead(StrEnum):
    REQUEST = "request"
    REFUSED = "refused"


_Word = TypeVar("_Word", bound=StrEnum)
# The exit codes of the core: a frame without a named part, and a frame that names one.
DECIDED_EXIT: Final = 0
NAMES_A_GAP_EXIT: Final = 3
_FIELDS: Final = frozenset(
    {
        "engine",
        "status",
        "rules",
        "explained",
        "violations",
        "beyond",
        "scope",
        "sections",
        "unsupported",
        "self_test",
    }
)
_UNSUPPORTED: Final = frozenset({"rules", "sections", "report"})
_SELF_TEST: Final = frozenset({"contract", "reply"})
# AD-406: the self-test of a scan frame has the `collect` part too.
_SCAN: Final = frozenset({"collect"})
# The first words of each reason of the core (`native/model/src/reason.rs`, `core/src/check.rs`,
# `core/src/base.rs`).
# They classify a gap for the fall-back note and the measurement; they decide nothing.
_GAP_PREFIXES: Final[tuple[tuple[str, GapKind], ...]] = (
    ("producer not verified", GapKind.PRODUCER_NOT_VERIFIED),
    ("unsupported: rule kind ", GapKind.RULE_KIND_NOT_PORTED),
    ("the base reply", GapKind.BASE),
    ("unsupported: the contract mounts inside contracts", GapKind.INSIDE_CONTRACT_MISSING),
    ("unsupported: a rule of an inside contract", GapKind.INSIDE_RULE),
    ("unsupported: the scope proof of a contract tree", GapKind.TREE_SCOPE),
    ("unsupported: the UML target", GapKind.UML_TARGET),
    ("unsupported: the scope proof: ", GapKind.SCOPE_PROOF),
    ("refused: ", GapKind.CONTRACT_REFUSED),
    # A rule of a ported kind without a model: the store refused the reply.
    ("missing input: ", GapKind.REPLY_REFUSED),
)


class CoreError(Exception):
    """The core binary is missing or not verified, failed, or wrote a frame that the shell
    refuses, or the two engines differ. The run then gives no verdict (exit 2)."""


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    kind: str
    status: RuleStatus


@dataclass(frozen=True, slots=True)
class Gap:
    """One part that the core names and does not decide."""

    kind: GapKind
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class CoreFrame:
    engine: str
    status: Status
    scope: str
    rules: Mapping[str, RuleVerdict]
    violations: Mapping[str, int]
    explained: Mapping[str, str]
    beyond: Mapping[str, str]
    gaps: tuple[Gap, ...]
    # The inside contracts that the core asks the shell to send (AD-379).
    missing: tuple[str, ...]
    # AD-406: the JSON text of the collection request that the core derived for a scan request.
    derived: str | None = None

    @property
    def decided(self) -> bool:
        """True when the frame names no part: the core decides every rule of the run."""
        return not self.gaps and not self.missing


def gap_kind(reason: str) -> GapKind:
    for prefix, kind in _GAP_PREFIXES:
        if reason.startswith(prefix):
            return kind
    return GapKind.OTHER


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CoreError(f"the core frame field {where} is not an object")
    return {str(key): item for key, item in value.items()}


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise CoreError(f"the core frame field {where} is not a text")
    return value


def _texts(value: object, where: str) -> dict[str, str]:
    return {key: _text(item, f"{where}.{key}") for key, item in _object(value, where).items()}


def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoreError(f"the core frame field {where} is not a count")
    return value


def _word(kind: type[_Word], value: object, where: str) -> _Word:
    """The member of a closed vocabulary, or `CoreError` for another word."""
    try:
        return kind(_text(value, where))
    except ValueError as error:
        raise CoreError(f"the core frame field {where} has the unknown word {value!r}") from error


def _one(value: object, where: str, tags: type[_Word]) -> tuple[_Word, object]:
    """The one tag of a tagged object and its value."""
    found = _object(value, where)
    if len(found) != 1:
        raise CoreError(f"the core frame field {where} must hold exactly one tag")
    [(tag, item)] = found.items()
    return _word(tags, tag, where), item


def _fields(value: object, where: str, names: frozenset[str]) -> dict[str, object]:
    """An object with exactly these fields."""
    found = _object(value, where)
    if missing := sorted(names - found.keys()):
        raise CoreError(f"the core frame field {where} has no field {', '.join(missing)}")
    if extra := sorted(found.keys() - names):
        raise CoreError(f"the core frame field {where} has an unknown field {', '.join(extra)}")
    return found


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """One JSON object without a repeated key (#1099): a repeated rule id must not let the last
    status win, so the frame is hostile."""
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise CoreError(f"the core frame repeats the key {key!r}")
        found[key] = value
    return found


def _document(stdout: bytes) -> dict[str, object]:
    """The one JSON object of the output. A second document, trailing text and a repeated key are
    refused."""
    try:
        text = stdout.decode("utf-8").strip()
        value, end = json.JSONDecoder(object_pairs_hook=_unique).raw_decode(text)
    except (UnicodeDecodeError, ValueError) as error:
        raise CoreError(f"the core frame is not JSON: {error}") from error
    if text[end:].strip():
        raise CoreError("the core wrote more than one frame")
    return _fields(value, "frame", _FIELDS)


def _rules(frame: Mapping[str, object]) -> dict[str, RuleVerdict]:
    rules: dict[str, RuleVerdict] = {}
    for rule, pair in _object(frame["rules"], "rules").items():
        if not isinstance(pair, list) or len(pair) != 2:
            raise CoreError(f"the core frame rule {rule} is not a kind and a status")
        kind = _text(pair[0], f"rules.{rule}")
        rules[rule] = RuleVerdict(kind, _word(RuleStatus, pair[1], f"rules.{rule}"))
    return rules


def _contract_gaps(value: object) -> tuple[list[Gap], tuple[str, ...]]:
    tag, found = _one(value, "self_test.contract", _ContractRead)
    if tag is _ContractRead.MISSING:
        if not isinstance(found, list) or not found:
            raise CoreError("the core frame field self_test.contract.missing is not a path list")
        return [], tuple(_text(path, "self_test.contract.missing") for path in found)
    if tag is _ContractRead.REFUSED:
        refused = _text(found, "self_test.contract")
        return [Gap(GapKind.CONTRACT_REFUSED, "contract", refused)], ()
    _texts(found, "self_test.contract.rules")
    return [], ()


def _reply_gaps(value: object) -> list[Gap]:
    tag, found = _one(value, "self_test.reply", _ReplyRead)
    if tag is _ReplyRead.FILES:
        _count(found, "self_test.reply.files")
        return []
    kind = GapKind.REPLY_REFUSED if tag is _ReplyRead.REFUSED else GapKind.REPLY_ABSENT
    return [Gap(kind, "reply", _text(found, f"self_test.reply.{tag}"))]


def _gaps(
    frame: Mapping[str, object], scan: bool
) -> tuple[tuple[Gap, ...], tuple[str, ...], str | None]:
    unsupported = _fields(frame["unsupported"], "unsupported", _UNSUPPORTED)
    gaps: list[Gap] = []
    named = unsupported["rules"]
    if isinstance(named, str):
        gaps.append(Gap(gap_kind(named), "the whole contract", named))
    else:
        rules = _texts(named, "unsupported.rules")
        gaps += [Gap(gap_kind(why), rule, why) for rule, why in rules.items()]
    sections = _texts(unsupported["sections"], "unsupported.sections")
    gaps += [Gap(GapKind.SECTION, name, why) for name, why in sections.items()]
    if unsupported["report"] is not None:
        report = _text(unsupported["report"], "unsupported.report")
        gaps.append(Gap(GapKind.REPORT, "report", report))
    test = _fields(frame["self_test"], "self_test", _SELF_TEST | _SCAN if scan else _SELF_TEST)
    contract, missing = _contract_gaps(test["contract"])
    # AD-406: the `collect` part of a scan frame: the derived request, or the refusal.
    collected: list[Gap] = []
    derived: str | None = None
    if scan:
        tag, found = _one(test["collect"], "self_test.collect", _CollectRead)
        if tag is _CollectRead.REQUEST:
            derived = json.dumps(_object(found, "self_test.collect.request"))
        else:
            reason = _text(found, "self_test.collect.refused")
            collected = [Gap(GapKind.COLLECT, "collect", reason)]
    return (*collected, *gaps, *contract, *_reply_gaps(test["reply"])), missing, derived


def _explained(
    rules: Mapping[str, RuleVerdict], violations: Mapping[str, int], explained: Mapping[str, str]
) -> None:
    """Each status has its explaining row and each row its rule (AD-361 point 5)."""
    for rule in (*violations, *explained):
        if rule not in rules:
            raise CoreError(f"the core frame explains the rule {rule}, which has no status")
    for rule, verdict in rules.items():
        count = violations.get(rule, 0)
        reason = bool(explained.get(rule))
        fits = {
            RuleStatus.FAIL: count > 0 and not reason,
            RuleStatus.UNKNOWN: count == 0 and reason,
            RuleStatus.PASS: count == 0 and not reason,
            RuleStatus.DECLARATION: count == 0 and not reason,
        }[verdict.status]
        if not fits:
            raise CoreError(f"the core frame rule {rule} is {verdict.status} without its row")


def read_frame(stdout: bytes, exit_code: int, *, scan: bool = False) -> CoreFrame:
    """The typed frame of one run of the core, or `CoreError`. `scan` reads the frame of a scan
    request, whose self-test has the `collect` part (AD-406)."""
    if exit_code not in (DECIDED_EXIT, NAMES_A_GAP_EXIT):
        raise CoreError(f"the core exits with {exit_code}")
    frame = _document(stdout)
    status = _word(Status, frame["status"], "status")
    rules = _rules(frame)
    counts = _object(frame["violations"], "violations")
    violations = {rule: _count(count, f"violations.{rule}") for rule, count in counts.items()}
    explained = _texts(frame["explained"], "explained")
    _explained(rules, violations, explained)
    _object(frame["sections"], "sections")
    gaps, missing, derived = _gaps(frame, scan)
    beyond = _texts(frame["beyond"], "beyond")
    passing = {rule for rule, verdict in rules.items() if verdict.status is RuleStatus.PASS}
    if not passing.issuperset(beyond):
        raise CoreError("the core frame names a rule beyond the reference that is not PASS")
    engine = _text(frame["engine"], "engine")
    if status is Status.PASS and not rules:
        raise CoreError("the core frame is PASS with zero rules")
    # A run PASS needs each row PASS or a declaration, and one PASS row (AD-390, review S1).
    verdicts = {verdict.status for verdict in rules.values()}
    if status is Status.PASS and not verdicts <= {RuleStatus.PASS, RuleStatus.DECLARATION}:
        raise CoreError("the core frame is PASS with a rule that is not PASS")
    if status is Status.PASS and RuleStatus.PASS not in verdicts:
        raise CoreError("the core frame is PASS without a PASS rule")
    named = bool(gaps or missing)
    if status is Status.PASS and named:
        raise CoreError("the core frame is PASS and names a part that it does not decide")
    if named != (exit_code == NAMES_A_GAP_EXIT):
        raise CoreError(f"the core exits with {exit_code} for a frame that names {len(gaps)} parts")
    return CoreFrame(
        engine=engine,
        status=status,
        scope=_text(frame["scope"], "scope"),
        rules=rules,
        violations=violations,
        explained=explained,
        beyond=beyond,
        gaps=gaps,
        missing=missing,
        derived=derived,
    )
