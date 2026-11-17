# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read one core frame into typed values and fail closed (AD-390, AD-422).

Reject unknown fields or words, inconsistent rows, repeated keys, extra frames and wrong exits.
A PASS needs a complete scope and a deciding rule. Refuse a frame with `CoreError`, never fallback.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, TypeVar

from .core_baseline import BaselineResult, read_baseline
from .core_binding import bind_request
from .core_doors import DoorRow, pass_qualifiers, read_doors
from .core_evidence import (
    CollectionGap,
    Location,
    ViolationDetail,
    read_collection_gaps,
    read_details,
    read_locations,
)
from .core_explain import Explain, read_explain
from .core_json import CoreError as CoreError
from .core_json import CoreExit, as_count, as_object, as_text, as_texts, check_measures
from .core_json import Gap as Gap
from .core_json import GapKind as GapKind
from .core_output import read_html
from .core_schema import check_frame, check_refusal
from .core_topology import Topology, frame_topology, require_topology


class Status(StrEnum):
    """The status of a run."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RefusalKind(StrEnum):
    """The closed set of reasons for which the shell refuses to give a verdict."""

    CORE_ERROR = "core_error"
    COLLECTION_REFUSED = "collection_refused"
    REQUEST_MISMATCH = "request_mismatch"
    INVALID_INPUT = "invalid_input"
    # AD-432: ArchKeel 5.0 does not serve the command or option yet; nothing ran.
    NOT_ON_THIS_LINE = "not_on_this_development_line"
    CORE_BINARY_NOT_FOUND = "core_binary_not_found"
    IO_ERROR = "io_error"
    INTERNAL_ERROR = "internal_error"
    # AD-731: `--write-baseline` on a run with a refused part; the frame is kept.
    BASELINE_NOT_WRITTEN = "baseline_not_written"
    # AD-735: the typed refusal of the core for an input over its parse work limit.
    PARSE_WORK_LIMIT = "parse_work_limit"


class CoreCommand(StrEnum):
    """Each registered command. Only `validate`, `report` and `skill` run (AD-432)."""

    VALIDATE = "validate"
    REPORT = "report"
    SKILL = "skill"
    CHECK = "check"
    EXPLORE = "explore"
    INIT = "init"
    GUIDE = "guide"
    STORY = "story"
    VIEW = "view"
    STUDIO = "studio"


class CheckKind(StrEnum):
    """The kinds of check that a run states as active."""

    LOCK = "accepted lock authentication"
    RATCHETS = "measurement ratchets"
    GUARDRAILS = "architecture guardrails"
    SELECTED_CHANGES = "selected changes and empty declaration"
    GIT = "Git order and accepted policy checks"
    HOST = "host publication order"


class RuleStatus(StrEnum):
    """The status of a rule: a permission declaration has no verdict."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    DECLARATION = "DECLARATION"


class _UnknownKind(StrEnum):
    """The closed set of causes of an UNKNOWN rule."""

    SCOPE_INCOMPLETE = "scope_incomplete"
    NO_RECEIPT = "no_receipt"
    UNDECIDED = "undecided"
    OWNERSHIP_BLOCKER = "ownership_blocker"
    NO_DECIDED_RULE = "no_decided_rule"


class _ScopeWord(StrEnum):
    COMPLETE = "complete"


class _FrameProtocol(StrEnum):
    """The one protocol word of a core frame that this shell reads."""

    FRAME = "archkeel-core-frame-1"


class _ContractRead(StrEnum):
    RULES = "rules"
    MISSING = "missing"
    REFUSED = "refused"
    NOT_READ = "not_read"


class _ReplyRead(StrEnum):
    FILES = "files"
    REFUSED = "refused"
    ABSENT = "absent"


class _CollectRead(StrEnum):
    REQUEST = "request"
    REFUSED = "refused"


_Word = TypeVar("_Word", bound=StrEnum)


FRAME_PROTOCOL: Final = _FrameProtocol.FRAME


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    """The kind and the status of one rule row."""

    kind: str
    status: RuleStatus


def read_refusal(stderr: bytes) -> Gap | None:
    """The closed refusal message on stderr, never a verdict frame or a text-prefix inference."""
    try:
        value = json.loads(stderr, object_pairs_hook=_unique)
    except (UnicodeDecodeError, ValueError):
        return None
    check_refusal(value)
    fields = as_object(value, "refusal")
    kind = _word(GapKind, fields["kind"], "refusal.kind")
    if kind is not GapKind.PARSE_WORK_LIMIT:
        raise CoreError(f"the core refusal has an unsupported kind {kind}")
    return Gap(kind, as_text(fields["subject"], "subject"), as_text(fields["reason"], "reason"))


def _premise(frame: Mapping[str, object], scan: bool, status: Status) -> str | None:
    """The assumption text of the frame: absent, or a non-empty string. Anything else is refused.
    A PASS of a TypeScript or a Python scan always states it (AD-530, AD-540): a PASS without one
    is refused."""
    if "premise" not in frame:
        collect = as_object(
            as_object(frame.get("self_test", {}), "self_test").get("collect", {}), "collect"
        )
        request = as_object(collect.get("request", {}), "request")
        resolver = as_object(request.get("resolver", {}), "resolver")
        if scan and status is Status.PASS and resolver.get("language") in {"typescript", "python"}:
            raise CoreError("the core frame of a TypeScript or Python scan states no premise")
        return None
    value = frame["premise"]
    if not isinstance(value, str) or not value.strip():
        raise CoreError("the core frame has a premise that is not a non-empty text")
    return value


@dataclass(frozen=True, slots=True)
class CoreFrame:
    """One core frame as typed values: the status, the rule rows and the evidence."""

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
    details: Mapping[str, tuple[ViolationDetail, ...]] = field(default_factory=dict)
    locations: Mapping[str, Location] = field(default_factory=dict)
    unknown_kinds: Mapping[str, _UnknownKind] = field(default_factory=dict)
    collection_gaps: tuple[CollectionGap, ...] = ()
    topology: Topology | None = None
    explain: Explain | None = None
    html: str | None = None
    baseline: BaselineResult | None = None
    # The call-resolution counts of the core, or `None` when it did not measure (#1327).
    measures: Mapping[str, int] | None = None
    # AD-540: the one assumption that the collector states for its proofs, when it states one.
    premise: str | None = None
    # AD-664: the door sites of each PASS under a declared reach, and the applied declarations.
    assumed: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    doors: tuple[DoorRow, ...] = ()

    @property
    def complete_scope(self) -> bool:
        """Whether the core states that the scope of the run is complete."""

        return self.scope == _ScopeWord.COMPLETE

    @property
    def code_digest(self) -> str:
        """The code digest of the core that wrote the frame."""

        return self.engine.removeprefix("archkeel-core ")


def _word(kind: type[_Word], value: object, where: str) -> _Word:
    """The member of a closed vocabulary, or `CoreError` for another word."""
    try:
        return kind(as_text(value, where))
    except ValueError as error:
        raise CoreError(f"the core frame field {where} has the unknown word {value!r}") from error


def _one(value: object, where: str, tags: type[_Word]) -> tuple[_Word, object]:
    """The one tag of a tagged object and its value."""
    found = as_object(value, where)
    if len(found) != 1:
        raise CoreError(f"the core frame field {where} must hold exactly one tag")
    [(tag, item)] = found.items()
    return _word(tags, tag, where), item


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
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise CoreError(f"the core frame is not JSON: {error}") from error
    if text[end:].strip():
        raise CoreError("the core wrote more than one frame")
    found = as_object(value, "frame")
    check_frame(found)
    return found


def _rules(frame: Mapping[str, object]) -> dict[str, RuleVerdict]:
    rules: dict[str, RuleVerdict] = {}
    for rule, pair in as_object(frame["rules"], "rules").items():
        if not isinstance(pair, list) or len(pair) != 2:
            raise CoreError(f"the core frame rule {rule} is not a kind and a status")
        kind = as_text(pair[0], f"rules.{rule}")
        rules[rule] = RuleVerdict(kind, _word(RuleStatus, pair[1], f"rules.{rule}"))
    return rules


def _contract_gaps(value: object) -> tuple[list[Gap], tuple[str, ...]]:
    tag, found = _one(value, "self_test.contract", _ContractRead)
    if tag is _ContractRead.NOT_READ:
        as_text(found, "self_test.contract.not_read")
        return [], ()
    if tag is _ContractRead.MISSING:
        if not isinstance(found, list) or not found:
            raise CoreError("the core frame field self_test.contract.missing is not a path list")
        return [], tuple(as_text(path, "self_test.contract.missing") for path in found)
    if tag is _ContractRead.REFUSED:
        refused = as_text(found, "self_test.contract")
        return [Gap(GapKind.CONTRACT_REFUSED, "contract", refused)], ()
    as_texts(found, "self_test.contract.rules")
    return [], ()


def _reply_gaps(value: object) -> list[Gap]:
    tag, found = _one(value, "self_test.reply", _ReplyRead)
    if tag is _ReplyRead.FILES:
        as_count(found, "self_test.reply.files")
        return []
    kind = GapKind.REPLY_REFUSED if tag is _ReplyRead.REFUSED else GapKind.REPLY_ABSENT
    return [Gap(kind, "reply", as_text(found, f"self_test.reply.{tag}"))]


def _core_gaps(frame: Mapping[str, object], named: object) -> list[Gap]:
    """The gaps of the rules without a decision, with the kind that the core wrote (AD-546).

    The shell does not infer a kind from the text. Each row must restate one reason of
    `unsupported.rules`, so the list cannot hide or invent a gap.
    """
    rows = frame.get("gaps")
    if not isinstance(rows, list):
        raise CoreError("the core frame has no gaps list")
    found = [as_object(row, "gaps") for row in rows]
    gaps = [
        Gap(
            _word(GapKind, row["kind"], "gaps.kind"),
            as_text(row["subject"], "gaps.subject"),
            as_text(row["reason"], "gaps.reason"),
        )
        for row in found
    ]
    expected = (
        {("the whole contract", named)}
        if isinstance(named, str)
        else set(as_texts(named, "unsupported.rules").items())
    )
    if {(gap.subject, gap.reason) for gap in gaps} != expected or len(gaps) != len(expected):
        raise CoreError("the core frame gaps list differs from its unsupported rules")
    return gaps


def _gaps(
    frame: Mapping[str, object], scan: bool
) -> tuple[tuple[Gap, ...], tuple[str, ...], str | None]:
    unsupported = as_object(frame["unsupported"], "unsupported")
    named = unsupported["rules"]
    gaps = _core_gaps(frame, named)
    sections = as_texts(unsupported["sections"], "unsupported.sections")
    gaps += [Gap(GapKind.SECTION, name, why) for name, why in sections.items()]
    if unsupported["report"] is not None:
        report = as_text(unsupported["report"], "unsupported.report")
        gaps.append(Gap(GapKind.REPORT, "report", report))
    test = as_object(frame["self_test"], "self_test")
    contract, missing = _contract_gaps(test["contract"])
    # AD-406: the `collect` part of a scan frame: the derived request, or the refusal.
    collected: list[Gap] = []
    derived: str | None = None
    if scan == ("collect" not in test):
        raise CoreError("the core frame has self_test.collect only for a scan, and always for it")
    if scan:
        if "collect" not in test:
            raise CoreError("the core frame of a scan has no self_test.collect")
        collect = as_object(test["collect"], "self_test.collect")
        tag, found = _one(
            {
                key: value
                for key, value in collect.items()
                if key not in ("contract_files", "target")
            },
            "self_test.collect",
            _CollectRead,
        )
        if "contract_files" in collect:
            as_texts(collect["contract_files"], "self_test.collect.contract_files")
        if "target" in collect:
            as_text(collect["target"], "self_test.collect.target")
        if tag is _CollectRead.REQUEST:
            derived = json.dumps(as_object(found, "self_test.collect.request"))
        else:
            reason = as_text(found, "self_test.collect.refused")
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


def _check_rows(
    require_protocol: bool,
    unknown_kinds: Mapping[str, object],
    explained: Mapping[str, object],
    violations: Mapping[str, int],
    details: Mapping[str, Sequence[object]],
) -> None:
    """The typed causes and the violation details agree with the rule rows."""
    if require_protocol:
        if unknown_kinds.keys() != explained.keys():
            raise CoreError("the core frame UNKNOWN rules lack their typed cause kinds")
        for rule, count in violations.items():
            if len(details.get(rule, ())) != count:
                raise CoreError(f"the core frame FAIL rule {rule} lacks its violation details")
    if not details.keys() <= violations.keys():
        raise CoreError("the core frame gives violation details to a rule without violations")


def read_frame(
    stdout: bytes,
    exit_code: int,
    *,
    scan: bool = False,
    require_protocol: bool = False,
    request: Mapping[str, object] | None = None,
    started_ns: int | None = None,
) -> CoreFrame:
    """Read one bound frame; scan frames also carry the collection self-test (AD-406)."""
    if exit_code not in (CoreExit.DECIDED, CoreExit.NAMES_A_GAP):
        signal = f" (signal {-exit_code})" if exit_code < 0 else ""
        raise CoreError(f"the core exits with {exit_code}{signal}")
    frame = _document(stdout)
    require_topology(frame, request)
    _word(
        _FrameProtocol,
        frame.get("protocol", None if require_protocol else FRAME_PROTOCOL),
        "protocol",
    )
    status = _word(Status, frame["status"], "status")
    rules = _rules(frame)
    counts = as_object(frame["violations"], "violations")
    violations = {rule: as_count(count, f"violations.{rule}") for rule, count in counts.items()}
    explained = as_texts(frame["explained"], "explained")
    _explained(rules, violations, explained)
    details = read_details(frame.get("details", {}))
    locations = read_locations(frame.get("locations", {}))
    unknown_kinds = {
        rule: _word(_UnknownKind, kind, "unknown_kinds")
        for rule, kind in as_object(frame.get("unknown_kinds", {}), "unknown_kinds").items()
    }
    _check_rows(require_protocol, unknown_kinds, explained, violations, details)
    as_object(frame["sections"], "sections")
    measures = check_measures(frame.get("measures"))
    gaps, missing, derived = _gaps(frame, scan)
    if request is not None and derived is not None:
        bind_request(frame, request, derived, started_ns)
    passing = {rule for rule, verdict in rules.items() if verdict.status is RuleStatus.PASS}
    beyond, assumed = pass_qualifiers(frame, passing)
    engine = as_text(frame["engine"], "engine")
    if status is Status.PASS and not rules:
        raise CoreError("the core frame is PASS with zero rules")
    if status is Status.PASS and frame["scope"] != _ScopeWord.COMPLETE:
        raise CoreError("the core frame is PASS without a complete scope")
    # A run PASS needs each row PASS or a declaration, and one PASS row (AD-390, review S1).
    verdicts = {verdict.status for verdict in rules.values()}
    if status is Status.PASS and not verdicts <= {RuleStatus.PASS, RuleStatus.DECLARATION}:
        raise CoreError("the core frame is PASS with a rule that is not PASS")
    if status is Status.PASS and RuleStatus.PASS not in verdicts:
        raise CoreError("the core frame is PASS without a PASS rule")
    named = bool(gaps or missing)
    if status is Status.PASS and named:
        raise CoreError("the core frame is PASS and names a part that it does not decide")
    if named != (exit_code == CoreExit.NAMES_A_GAP):
        raise CoreError(f"the core exits with {exit_code} for a frame that names {len(gaps)} parts")
    return CoreFrame(
        engine=engine,
        status=status,
        scope=as_text(frame["scope"], "scope"),
        rules=rules,
        violations=violations,
        explained=explained,
        beyond=beyond,
        gaps=gaps,
        missing=missing,
        derived=derived,
        details=details,
        locations=locations,
        unknown_kinds=unknown_kinds,
        collection_gaps=read_collection_gaps(frame.get("collection_gaps", [])),
        topology=frame_topology(frame, rules),
        explain=read_explain(frame["explain"], violations) if "explain" in frame else None,
        html=read_html(frame, status, request),
        baseline=read_baseline(frame["baseline"], status) if "baseline" in frame else None,
        measures=measures,
        premise=_premise(frame, scan, status),
        assumed=assumed,
        doors=read_doors(frame),
    )
