# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate, read and rewrite marked Mermaid graphs."""

from __future__ import annotations

import re

from archkeel.ir.model import ArchitectureContract, Diagnostic, Observation

from .closed_world import observed_component_edges, target_component_edges
from .diagnostics import _diagnostic

COMPONENT_GRAPH_MARKER = "<!-- archkeel-component-graph -->"
# AD-57: a second, independent marker for the graph the contract permits, beside the one
# above for the graph the code observes. A page may carry either, both or neither.
TARGET_GRAPH_MARKER = "<!-- archkeel-target-graph -->"
_GRAPH_EDGE = re.compile(r"\s*([a-z_][a-z0-9_]*)\s*-->\s*([a-z_][a-z0-9_]*)\s*")
_MERMAID_FENCE = "```mermaid\n"
_GRAPH_DECLARATION = re.compile(r"\s*(?:graph|flowchart)\b.*")
_GRAPH_COMMENT = re.compile(r"\s*%%.*")


def _marked_bodies(content: str, marker: str) -> list[tuple[int, int]]:
    """Start and end of each Mermaid body that follows `marker`, before the next one.

    AD-57: the marker is a parameter, not a hardcoded constant, so `graph_diagnostics` and
    `rewrite_component_graph` read `COMPONENT_GRAPH_MARKER` and `TARGET_GRAPH_MARKER` through
    the one reader and can never disagree about where either marker's block starts and ends.
    """
    spans: list[tuple[int, int]] = []
    position = content.find(marker)
    while position != -1:
        following = content.find(marker, position + len(marker))
        limit = len(content) if following == -1 else following
        fence = content.find(_MERMAID_FENCE, position, limit)
        if fence != -1:
            start = fence + len(_MERMAID_FENCE)
            end = content.find("```", start, limit)
            spans.append((start, limit if end == -1 else end))
        position = following
    return spans


def _unwritable_line(body: str) -> str | None:
    """The first line of a marked block that is not a declaration, a `%%` comment or an edge.

    AD-46: a subgraph, a labeled edge or a style can depend on where an edge sits, so a rewrite
    that reorders the edges could change what the graph says; such a block is left to a human.
    """
    return next(
        (
            line.strip()
            for line in body.splitlines()
            if line.strip()
            and not _GRAPH_EDGE.fullmatch(line)
            and not _GRAPH_DECLARATION.fullmatch(line)
            and not _GRAPH_COMMENT.fullmatch(line)
        ),
        None,
    )


def mermaid_edges(edges: frozenset[tuple[str, str]]) -> str:
    """One sorted Mermaid line per component edge: what `init` and `--write-graph` write."""
    return "".join(f"    {source} --> {target}\n" for source, target in sorted(edges))


def rewrite_component_graph(
    documents: tuple[tuple[str, str], ...],
    observed_edges: frozenset[tuple[str, str]],
    target_edges: frozenset[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Every marked graph's document with its edges replaced; empty if nothing is written.

    AD-46/AD-57: the two markers are rewritten independently, each only when the documents
    carry exactly one block for it; a marker absent everywhere is left alone, the way a page
    may carry either, both or neither, and one repeated is as ambiguous to rewrite as before -
    `graph.count` says so and this writes nothing for it either. The declaration and `%%`
    comments stay ahead of the edges, so a page's own `flowchart LR` survives, and a block
    without a declaration gets `init`'s; a block with any other line is not rewritten at all.
    Both markers may sit in the same document, which then comes back once with both edits.
    """
    edited: dict[str, str] = {}
    for marker, edges in (
        (COMPONENT_GRAPH_MARKER, observed_edges),
        (TARGET_GRAPH_MARKER, target_edges),
    ):
        current = {path: edited.get(path, content) for path, content in documents}
        blocks = [
            (path, span)
            for path, content in current.items()
            for span in _marked_bodies(content, marker)
        ]
        if len(blocks) != 1:
            continue
        path, (start, end) = blocks[0]
        content = current[path]
        body = content[start:end]
        if _unwritable_line(body) is not None:
            continue
        kept = [
            line for line in body.splitlines() if line.strip() and not _GRAPH_EDGE.fullmatch(line)
        ]
        if not any(_GRAPH_DECLARATION.fullmatch(line) for line in kept):
            kept.insert(0, "graph TD")
        written = (
            content[:start]
            + "".join(f"{line}\n" for line in kept)
            + mermaid_edges(edges)
            + content[end:]
        )
        if written != content:
            edited[path] = written
    return tuple(edited.items())


# Each marker compares its own source: observed code or the declared contract.
_GRAPH_MARKERS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        COMPONENT_GRAPH_MARKER,
        "component",
        "observed imports",
        "the observed component edges",
        "edges gone from code (drawn, not observed)",
        "edges new in code (observed, not drawn)",
    ),
    (
        TARGET_GRAPH_MARKER,
        "target",
        "the edges the contract permits",
        "the edges the contract permits",
        "edges gone from contract (drawn, not permitted)",
        "edges new in contract (permitted, not drawn)",
    ),
)


def _marker_diagnostics(
    marker: str,
    noun: str,
    claim_source: str,
    remedy_source: str,
    gone_label: str,
    new_label: str,
    edges: frozenset[tuple[str, str]],
    documents: tuple[tuple[str, str], ...],
    *,
    required: bool,
) -> tuple[Diagnostic, ...]:
    """One marker's graph.count/graph.drift findings; the subject always names the marker.

    AD-57: `required` is false for the target marker, so a page that draws none is silent -
    the target is optional, the way a page may carry either, both or neither - while the
    observed marker keeps AD-12's original rule, always exactly one.
    """
    graphs = [
        (path, content[start:end])
        for path, content in documents
        for start, end in _marked_bodies(content, marker)
    ]
    if not graphs and not required:
        return ()
    if len(graphs) != 1:
        return (
            _diagnostic(
                "graph.count",
                "/components",
                f"architecture {noun} graph",
                f"Expected one marked Mermaid {noun} graph, found {len(graphs)}.",
                f"Keep one graph after the archkeel-{noun}-graph marker in contract provenance.",
            ),
        )
    path, body = graphs[0]
    declared = frozenset(
        (match.group(1), match.group(2))
        for line in body.splitlines()
        if (match := _GRAPH_EDGE.fullmatch(line))
    )
    if declared == edges:
        return ()
    new_edges = ", ".join(f"{a}->{b}" for a, b in sorted(edges - declared)) or "none"
    gone_edges = ", ".join(f"{a}->{b}" for a, b in sorted(declared - edges)) or "none"
    unwritable = _unwritable_line(body)
    return (
        _diagnostic(
            "graph.drift",
            "/components",
            f"{path} ({noun} graph)",
            f"The marked {noun} graph differs from {claim_source}; "
            f"{gone_label}: {gone_edges}; {new_label}: {new_edges}.",
            "Run archkeel validate --write-graph to regenerate the marked Mermaid graph "
            f"from {remedy_source}."
            if unwritable is None
            else f"Edit the marked graph's edges by hand: it holds `{unwritable}`, structure "
            "archkeel validate --write-graph does not rewrite.",
        ),
    )


def graph_diagnostics(
    contract: ArchitectureContract,
    observation: Observation,
    documents: tuple[tuple[str, str], ...],
) -> tuple[Diagnostic, ...]:
    """Require the observed marker always, and the target marker whenever a page draws one.

    AD-57: `<!-- archkeel-target-graph -->` is compared against `target_component_edges`, the
    pairs the contract permits, beside `<!-- archkeel-component-graph -->`'s unchanged
    comparison against observed imports; the two are independent, so one may drift while the
    other passes, and each diagnostic's subject names its own marker.
    """
    (
        observed_marker,
        observed_noun,
        observed_claim,
        observed_remedy,
        observed_gone,
        observed_new,
    ) = _GRAPH_MARKERS[0]
    target_marker, target_noun, target_claim, target_remedy, target_gone, target_new = (
        _GRAPH_MARKERS[1]
    )
    return (
        *_marker_diagnostics(
            observed_marker,
            observed_noun,
            observed_claim,
            observed_remedy,
            observed_gone,
            observed_new,
            observed_component_edges(contract, observation),
            documents,
            required=True,
        ),
        *_marker_diagnostics(
            target_marker,
            target_noun,
            target_claim,
            target_remedy,
            target_gone,
            target_new,
            target_component_edges(contract),
            documents,
            required=False,
        ),
    )
