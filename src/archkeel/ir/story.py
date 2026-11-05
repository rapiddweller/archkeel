# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Candidate paths for a story: the call graph proposes them, the author chooses."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Final, Literal

from archkeel.ir.flow_graph import (
    MAX_HOPS,
    CallEdge,
    CallGraph,
    ExternalSystem,
    Seam,
    Site,
    build_call_graph,
    find_paths,
    function_label,
    module_lanes,
    touchpoints,
)
from archkeel.ir.model import Observation
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.view_spec import (
    CandidateEvidence,
    ExternalCheck,
    ViewEvidence,
    ViewSnapshot,
    ViewStatus,
    call_evidence,
    call_status,
    external_checks,
    snapshot_identity,
)

TRACE_LIMITS: Final = (
    "A proven hop is one resolved call between two functions: structure, not runtime order.",
    "A claim hop is a partial call: the analysis lists candidates and does not prove the target.",
    "An unresolved call is a seam of its function, not a hop. A process boundary is not detected.",
    "The search lists some paths, not the best path. Author text is not part of this result.",
    "Node names are stable IDs; labels use the observed source path and symbol name for display.",
)


@dataclass(frozen=True, slots=True)
class TraceNode:
    name: str
    label: str
    lane: str | None
    defined_at: Site | None
    external: tuple[ExternalCheck, ...]


@dataclass(frozen=True, slots=True)
class TraceHop:
    node: TraceNode
    status: ViewStatus
    reason: str
    seam: Seam | None
    evidence: tuple[ViewEvidence | CandidateEvidence, ...]


@dataclass(frozen=True, slots=True)
class TracePath:
    start: TraceNode
    hops: tuple[TraceHop, ...]
    seams: tuple[Seam, ...]
    systems: tuple[ExternalSystem, ...]


@dataclass(frozen=True, slots=True)
class TraceResult:
    schema_version: Literal["1.1.0"]
    snapshot: ViewSnapshot
    source: str
    target: str | None
    max_paths: int
    max_hops: int
    complete: bool
    paths: tuple[TracePath, ...]
    limits: tuple[str, ...] = TRACE_LIMITS


def _node(calls: CallGraph, lanes: dict[str, str], name: str) -> TraceNode:
    function = calls.functions[name]
    return TraceNode(
        name,
        function_label(function),
        lanes.get(function.module),
        function.defined_at,
        external_checks(touchpoints(calls, name)),
    )


def _path(
    calls: CallGraph, lanes: dict[str, str], source: str, edges: tuple[CallEdge, ...]
) -> TracePath:
    start = _node(calls, lanes, source)
    hops = []
    for edge in edges:
        status, reason = call_status(edge)
        hops.append(
            TraceHop(
                _node(calls, lanes, edge.target), status, reason, edge.seam, call_evidence(edge)
            )
        )
    nodes = (start, *(hop.node for hop in hops))
    seams: list[Seam] = []
    for index, node in enumerate(nodes):
        into = hops[index - 1].seam if index else None
        unresolved = calls.unresolved.get(node.name)
        seams.extend(seam for seam in (into, unresolved) if seam is not None)
    systems = sorted({item.system for node in nodes for item in node.external})
    return TracePath(start, tuple(hops), tuple(seams), tuple(systems))


def trace_flow(
    observation: Observation,
    source: str,
    target: str | None,
    *,
    max_paths: int,
    max_hops: int,
) -> TraceResult:
    """Candidate paths from `source`, to `target` when given; a bad name or limit is an error."""
    if max_paths < 1 or not 1 <= max_hops <= MAX_HOPS:
        raise ValueError(f"--max-paths must be at least 1 and --max-hops from 1 to {MAX_HOPS}")
    calls = build_call_graph(observed_graph(observation), observation.records("imports") or ())
    for option, name in (("--from", source), ("--to", target)):
        if name is not None and name not in calls.functions:
            raise ValueError(f"{option} {name!r} is not a function or method of the snapshot")
    if source == target:
        raise ValueError("--from and --to name the same function")
    lanes = module_lanes(observation, {item.module for item in calls.functions.values()})
    search = find_paths(calls, source, target, max_paths=max_paths, max_hops=max_hops)
    return TraceResult(
        "1.1.0",
        snapshot_identity(observation),
        source,
        target,
        max_paths,
        max_hops,
        search.complete,
        tuple(_path(calls, lanes, source, edges) for edges in search.paths),
    )


def trace_json(result: TraceResult) -> str:
    """The same trace gives the same text."""
    return json.dumps(asdict(result), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def trace_summary(result: TraceResult) -> str:
    where = f"to {result.target}" if result.target else "to the farthest functions"
    lines = [f"Story trace from {result.source} {where}: {len(result.paths)} paths."]
    if not result.complete:
        lines.append("The search stopped at its work limit: the list can be incomplete.")
    for number, path in enumerate(result.paths, 1):
        names = " -> ".join((path.start.label, *(hop.node.label for hop in path.hops)))
        seams = f", {len(path.seams)} seams" if path.seams else ""
        lines.append(f"{number}. {names} ({len(path.hops)} hops{seams})")
    lines.append(result.limits[0])
    return "\n".join(lines)
