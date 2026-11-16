# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small checked JSON readers shared by the frame and its evidence metadata."""

from dataclasses import dataclass
from enum import StrEnum


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
    SCOPE_PROOF = "scope_proof"
    CONTRACT_REFUSED = "contract_refused"
    SECTION = "section"
    REPORT = "report"
    OTHER = "other"
    PYTHON_INCOMPLETE = "python_incomplete"
    REPLIES = "replies"
    EXTERNAL_COLLECTOR = "external_collector"
    NO_DECIDED_RULE = "no_decided_rule"
    COLLECT = "collect"
    REQUEST_DIFFERS = "request_differs"
    PARSE_WORK_LIMIT = "parse_work_limit"
    # AD-466: a contract hygiene defect has the code of release 4.0.1 as its kind.
    REFERENCE_PROVENANCE = "reference.provenance"
    REFERENCE_NAMESPACE = "reference.namespace"
    REFERENCE_PUBLIC_OWNER = "reference.public_owner"
    REFERENCE_PUBLIC_UNDERSCORE = "reference.public_underscore"
    REFERENCE_PACKAGE_UNSCANNED = "reference.package_unscanned"
    GRAPH_COUNT = "graph.count"
    GRAPH_DRIFT = "graph.drift"
    CLOSED_WORLD_OBSERVED_FORBIDDEN = "closed_world.observed_forbidden"
    CLOSED_WORLD_DUPLICATE = "closed_world.duplicate"
    DECISION_CONFLICT = "decision.conflict"
    DECISION_OPEN = "decision.open"
    RATIONALE_PLACEHOLDER = "rationale.placeholder"
    RATIONALE_REPEATED = "rationale.repeated"
    RESPONSIBILITY_MISSING = "responsibility.missing"
    API_SURFACE_MISSING = "api_surface.missing"
    # AD-514: the core proves a use from the imports and reads no declared facade signature.
    INTERFACE_UNDECLARED = "interface.undeclared"
    INTERFACE_USAGE_UNKNOWN = "interface.usage_unknown"
    INTERFACE_PLANNED_BUILT = "interface.planned_built"
    # AD-550: a position of a public signature that syntax does not decide, and an exception of a
    # `boundary_types` rule that no position uses.
    BOUNDARY_TYPE_POSITION = "boundary_type_position"
    BOUNDARY_TYPE_ALLOWANCE_STALE = "boundary_type_allowance_stale"
    HYGIENE_NOT_PORTED = "contract_hygiene_not_ported"
    HYGIENE_NOT_READ = "contract_hygiene_not_read"


@dataclass(frozen=True, slots=True)
class Gap:
    """One part that the core names and does not decide."""

    kind: GapKind
    subject: str
    reason: str


class CoreError(Exception):
    """The core failed or its frame was refused. The command has no verdict (exit 2)."""

    def __init__(self, message: str, *, gap: Gap | None = None) -> None:
        Exception.__init__(self, message)
        self.gap = gap

    def __str__(self) -> str:
        if self.gap is not None:
            return f"core refusal [{self.gap.kind}]: {self.gap.subject}: {self.gap.reason}"
        return Exception.__str__(self)


class RequestMismatch(CoreError):
    """The frame does not bind to the request or its current contract bytes."""


def as_object(value: object, where: str) -> dict[str, object]:
    """An object with string keys, else `CoreError`."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CoreError(f"the core frame field {where} is not an object")
    return {str(key): item for key, item in value.items()}


def as_text(value: object, where: str) -> str:
    """A text, else `CoreError`."""
    if not isinstance(value, str):
        raise CoreError(f"the core frame field {where} is not a text")
    return value


def as_texts(value: object, where: str) -> dict[str, str]:
    """An object whose values are all texts."""
    return {key: as_text(item, f"{where}.{key}") for key, item in as_object(value, where).items()}


def as_count(value: object, where: str) -> int:
    """A non-negative integer that is no boolean, else `CoreError`."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoreError(f"the core frame field {where} is not a count")
    return value


_CALL_CLASSES = "calls_resolved calls_partial calls_builtin calls_external calls_unresolved".split()
_CALL_CAUSES = "unresolved_self unresolved_attribute unresolved_name unresolved_dynamic".split()
_MEASURE_FIELDS = frozenset(
    (*_CALL_CLASSES, *_CALL_CAUSES, "calls_total", "typing_positions", "untyped_private_accesses")
)


def check_measures(value: object) -> None:
    """Refuse call measures that do not add up; `None` is no measures."""
    if value is None:
        return
    fields = as_fields(value, "measures", _MEASURE_FIELDS)
    counts = {name: as_count(item, f"measures.{name}") for name, item in fields.items()}
    if counts["calls_total"] != sum(counts[name] for name in _CALL_CLASSES) or counts[
        "calls_unresolved"
    ] != sum(counts[name] for name in _CALL_CAUSES):
        raise CoreError("the core frame has inconsistent call measures")


def as_fields(value: object, where: str, names: frozenset[str]) -> dict[str, object]:
    """An object with exactly these fields."""
    found = as_object(value, where)
    if missing := sorted(names - found.keys()):
        raise CoreError(f"the core frame field {where} has no field {', '.join(missing)}")
    if extra := sorted(found.keys() - names):
        raise CoreError(f"the core frame field {where} has an unknown field {', '.join(extra)}")
    return found
