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

from .core_binding import bind_request
from .core_evidence import (
    CollectionGap,
    Location,
    ViolationDetail,
    _collection_gaps,
    _details,
    _locations,
)
from .core_explain import Explain, read_explain
from .core_json import CoreError as CoreError
from .core_json import Gap as Gap
from .core_json import GapKind as GapKind
from .core_json import _count, _fields, _object, _text, _texts
from .core_output import read_html
from .core_topology import Topology, frame_topology, require_topology


class Status(StrEnum):
    """The status of a run."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class RefusalKind(StrEnum):
    CORE_ERROR = "core_error"
    COLLECTION_REFUSED = "collection_refused"
    REQUEST_MISMATCH = "request_mismatch"
    INVALID_INPUT = "invalid_input"
    # AD-432: this development line does not serve the command or option; nothing ran.
    NOT_ON_THIS_LINE = "not_on_this_development_line"
    CORE_BINARY_NOT_FOUND = "core_binary_not_found"
    IO_ERROR = "io_error"
    INTERNAL_ERROR = "internal_error"


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


class UnknownKind(StrEnum):
    SCOPE_INCOMPLETE = "scope_incomplete"
    NO_RECEIPT = "no_receipt"
    UNDECIDED = "undecided"
    OWNERSHIP_BLOCKER = "ownership_blocker"
    NO_DECIDED_RULE = "no_decided_rule"


class _ScopeWord(StrEnum):
    COMPLETE = "complete"


class FrameProtocol(StrEnum):
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


class _RefusalProtocol(StrEnum):
    V1 = "archkeel-core-refusal-1"


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
FRAME_PROTOCOL: Final = FrameProtocol.FRAME
_EVIDENCE_FIELDS: Final = frozenset(
    {
        "protocol",
        "details",
        "locations",
        "unknown_kinds",
        "collection_gaps",
        "contract_digest",
        "topology",
        "explain",
        "html",
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
    ("unsupported: contract has no decided rule", GapKind.NO_DECIDED_RULE),
    ("producer not verified", GapKind.PRODUCER_NOT_VERIFIED),
    ("unsupported: rule kind ", GapKind.RULE_KIND_NOT_PORTED),
    ("the base reply", GapKind.BASE),
    ("unsupported: the contract mounts inside contracts", GapKind.INSIDE_CONTRACT_MISSING),
    ("unsupported: a rule of an inside contract", GapKind.INSIDE_RULE),
    ("unsupported: the scope proof of a contract tree", GapKind.TREE_SCOPE),
    ("unsupported: the scope proof: ", GapKind.SCOPE_PROOF),
    ("refused: ", GapKind.CONTRACT_REFUSED),
    ("unsupported: the contract hygiene checks ", GapKind.HYGIENE_NOT_PORTED),
    ("unsupported: the contract hygiene of the request", GapKind.HYGIENE_NOT_READ),
    # A rule of a ported kind without a model: the store refused the reply.
    ("missing input: ", GapKind.REPLY_REFUSED),
)


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    kind: str
    status: RuleStatus


def read_refusal(stderr: bytes) -> Gap | None:
    """The closed refusal message on stderr, never a verdict frame or a text-prefix inference."""
    try:
        value = json.loads(stderr, object_pairs_hook=_unique)
    except (UnicodeDecodeError, ValueError):
        return None
    fields = _fields(value, "refusal", frozenset({"protocol", "kind", "subject", "reason"}))
    _word(_RefusalProtocol, fields["protocol"], "refusal.protocol")
    kind = _word(GapKind, fields["kind"], "refusal.kind")
    if kind is not GapKind.PARSE_WORK_LIMIT:
        raise CoreError(f"the core refusal has an unsupported kind {kind}")
    return Gap(kind, _text(fields["subject"], "subject"), _text(fields["reason"], "reason"))


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
    details: Mapping[str, tuple[ViolationDetail, ...]] = field(default_factory=dict)
    locations: Mapping[str, Location] = field(default_factory=dict)
    unknown_kinds: Mapping[str, UnknownKind] = field(default_factory=dict)
    collection_gaps: tuple[CollectionGap, ...] = ()
    topology: Topology | None = None
    explain: Explain | None = None
    html: str | None = None

    @property
    def complete_scope(self) -> bool:
        return self.scope == _ScopeWord.COMPLETE

    @property
    def code_digest(self) -> str:
        return self.engine.removeprefix("archkeel-core ")


_HYGIENE: Final = "contract hygiene "


def gap_kind(reason: str) -> GapKind:
    for prefix, kind in _GAP_PREFIXES:
        if reason.startswith(prefix):
            return kind
    if reason.startswith(_HYGIENE):
        # AD-466: `Reason::Hygiene` writes the code of release 4.0.1 first; the code is the kind.
        return _word(GapKind, reason.removeprefix(_HYGIENE).partition(":")[0], "hygiene code")
    return GapKind.OTHER


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
    found = _object(value, "frame")
    return _fields(found, "frame", _FIELDS | (_EVIDENCE_FIELDS & found.keys()))


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
    if tag is _ContractRead.NOT_READ:
        _text(found, "self_test.contract.not_read")
        return [], ()
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
        collect = _object(test["collect"], "self_test.collect")
        tag, found = _one(
            {key: value for key, value in collect.items() if key != "contract_files"},
            "self_test.collect",
            _CollectRead,
        )
        if "contract_files" in collect:
            _texts(collect["contract_files"], "self_test.collect.contract_files")
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
    if exit_code not in (DECIDED_EXIT, NAMES_A_GAP_EXIT):
        signal = f" (signal {-exit_code})" if exit_code < 0 else ""
        raise CoreError(f"the core exits with {exit_code}{signal}")
    frame = _document(stdout)
    require_topology(frame, request)
    _word(
        FrameProtocol,
        frame.get("protocol", None if require_protocol else FRAME_PROTOCOL),
        "protocol",
    )
    status = _word(Status, frame["status"], "status")
    rules = _rules(frame)
    counts = _object(frame["violations"], "violations")
    violations = {rule: _count(count, f"violations.{rule}") for rule, count in counts.items()}
    explained = _texts(frame["explained"], "explained")
    _explained(rules, violations, explained)
    details = _details(frame.get("details", {}))
    locations = _locations(frame.get("locations", {}))
    unknown_kinds = {
        rule: _word(UnknownKind, kind, "unknown_kinds")
        for rule, kind in _object(frame.get("unknown_kinds", {}), "unknown_kinds").items()
    }
    _check_rows(require_protocol, unknown_kinds, explained, violations, details)
    _object(frame["sections"], "sections")
    gaps, missing, derived = _gaps(frame, scan)
    if request is not None and derived is not None:
        bind_request(frame, request, derived, started_ns)
    beyond = _texts(frame["beyond"], "beyond")
    passing = {rule for rule, verdict in rules.items() if verdict.status is RuleStatus.PASS}
    if not passing.issuperset(beyond):
        raise CoreError("the core frame names a rule beyond the reference that is not PASS")
    engine = _text(frame["engine"], "engine")
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
        details=details,
        locations=locations,
        unknown_kinds=unknown_kinds,
        collection_gaps=_collection_gaps(frame.get("collection_gaps", [])),
        topology=frame_topology(frame, rules),
        explain=(read_explain(frame["explain"], rules, violations) if "explain" in frame else None),
        html=read_html(frame, status, request),
    )
