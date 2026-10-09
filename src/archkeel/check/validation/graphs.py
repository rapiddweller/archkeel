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
_GRAPH_EDGE = r"\s*([a-z_][a-z0-9_]*)\s*-->\s*([a-z_][a-z0-9_]*)\s*"
_GRAPH_NODE = r'\s*([a-z_][a-z0-9_]*)\s*\["([^"\r\n]*)"\]\s*'
_GRAPH_ID = r"[a-z_][a-z0-9_]*\Z"
_GRAPH_ENTITY = r"#([0-9]+);"
_MERMAID_FENCE = "```mermaid\n"
_GRAPH_DECLARATION = r"\s*(?:graph|flowchart)\b.*"
_GRAPH_COMMENT = r"\s*%%.*"


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


def _unwritable_line(body: str, *, allow_isolated_nodes: bool = False) -> str | None:
    """Find graph content the rewrite cannot preserve, optionally allowing isolated nodes.

    AD-46: a subgraph, a labeled edge or a style can depend on where an edge sits, so a rewrite
    that reorders the edges could change what the graph says; such a block is left to a human.
    """
    labels, conflict = _node_labels(body)
    if conflict is not None:
        return conflict
    referenced: set[str] = set()
    declared = set(labels)
    for line in body.splitlines():
        stripped = line.strip()
        if re.fullmatch(_GRAPH_ID, stripped):
            declared.add(stripped)
        match = re.fullmatch(_GRAPH_EDGE, line)
        if match is not None:
            referenced.update(match.groups())
    orphaned = declared.difference(referenced)
    if orphaned and not allow_isolated_nodes:
        return f"isolated node {min(orphaned)}"
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            re.fullmatch(pattern, stripped)
            for pattern in (_GRAPH_EDGE, _GRAPH_NODE, _GRAPH_ID, _GRAPH_DECLARATION, _GRAPH_COMMENT)
        ):
            continue
        return stripped
    return None


def _node_labels(body: str) -> tuple[dict[str, str], str | None]:
    """Read quoted node declarations; conflicting identities make the block ambiguous."""
    labels: dict[str, str] = {}
    aliases_by_label: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        match = re.fullmatch(_GRAPH_NODE, stripped)
        if match is None:
            continue
        alias, encoded_label = match.groups()
        label = _unescape_label(encoded_label)
        if label is None:
            return labels, stripped
        previous = labels.get(alias)
        if previous is not None and previous != label:
            return labels, stripped
        previous_alias = aliases_by_label.get(label)
        if previous_alias is not None and previous_alias != alias:
            return labels, stripped
        labels[alias] = label
        aliases_by_label[label] = alias
    return labels, None


def _unescape_label(value: str) -> str | None:
    """Decode the numeric entities emitted by `_escape_label`, without recursive decoding."""

    def decode(match: re.Match[str]) -> str:
        (digits,) = match.groups()
        return chr(int(digits))

    try:
        return re.sub(_GRAPH_ENTITY, decode, value)
    except (ValueError, OverflowError):
        return None


def _escape_label(value: str) -> str:
    """Keep declarations on one line and preserve literal Mermaid control markup."""
    return "".join(
        f"#{ord(character)};"
        if character in '#"&<>' or ord(character) < 32 or ord(character) == 127
        else character
        for character in value
    )


def _node_aliases(edges: frozenset[tuple[str, str]]) -> dict[str, str] | None:
    labels = sorted({label for edge in edges for label in edge})
    if all(re.fullmatch(_GRAPH_ID, label) for label in labels):
        return None
    return {label: f"n_{index}" for index, label in enumerate(labels)}


def _declared_edges(body: str) -> frozenset[tuple[str, str]]:
    labels, _ = _node_labels(body)
    edges: set[tuple[str, str]] = set()
    for line in body.splitlines():
        match = re.fullmatch(_GRAPH_EDGE, line)
        if match is None:
            continue
        source, target = match.groups()
        edges.add((labels.get(source, source), labels.get(target, target)))
    return frozenset(edges)


def mermaid_edges(edges: frozenset[tuple[str, str]]) -> str:
    """Write sorted graph edges, preserving human labels through quoted alias declarations."""
    aliases = _node_aliases(edges)
    if aliases is None:
        return "".join(f"    {source} --> {target}\n" for source, target in sorted(edges))
    declarations = "".join(
        f'    {alias}["{_escape_label(label)}"]\n' for label, alias in sorted(aliases.items())
    )
    projected = frozenset((aliases[source], aliases[target]) for source, target in edges)
    return declarations + "".join(
        f"    {source} --> {target}\n" for source, target in sorted(projected)
    )


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
        kept: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or re.fullmatch(_GRAPH_EDGE, line) or re.fullmatch(_GRAPH_NODE, line):
                continue
            kept.append(line)
        if not any(re.fullmatch(_GRAPH_DECLARATION, line) for line in kept):
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
    declared = _declared_edges(body)
    unwritable = _unwritable_line(body, allow_isolated_nodes=True)
    if declared == edges and unwritable is None:
        return ()
    unwritable = unwritable or _unwritable_line(body)
    new_edges = ", ".join(f"{a}->{b}" for a, b in sorted(edges - declared)) or "none"
    gone_edges = ", ".join(f"{a}->{b}" for a, b in sorted(declared - edges)) or "none"
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
