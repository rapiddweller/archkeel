# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Deterministic graph operations used by the architecture graphs."""

from __future__ import annotations

from collections.abc import Iterable


def strongly_connected_components(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> list[list[str]]:
    node_list = sorted(set(nodes))
    adjacency: dict[str, set[str]] = {node: set() for node in node_list}
    reverse: dict[str, set[str]] = {node: set() for node in node_list}
    for source, target in sorted(set(edges)):
        if source not in adjacency or target not in adjacency:
            continue
        adjacency[source].add(target)
        reverse[target].add(source)

    seen: set[str] = set()
    order: list[str] = []

    def visit(node: str) -> None:
        seen.add(node)
        for target in sorted(adjacency[node]):
            if target not in seen:
                visit(target)
        order.append(node)

    for node in node_list:
        if node not in seen:
            visit(node)

    seen.clear()
    components: list[list[str]] = []

    def collect(node: str, component: list[str]) -> None:
        seen.add(node)
        component.append(node)
        for source in sorted(reverse[node]):
            if source not in seen:
                collect(source, component)

    for node in reversed(order):
        if node in seen:
            continue
        component: list[str] = []
        collect(node, component)
        components.append(sorted(component))
    return sorted(components, key=lambda component: (component[0], len(component)))


def _bfs_parents(ordered: dict[str, list[str]], source: str) -> dict[str, str | None]:
    """Walk once from the source. The first node to reach a target is its parent, so the path
    from the parents is the lexicographically first shortest path."""
    parent: dict[str, str | None] = {source: None}
    order = [source]  # first in, first out: the loop also visits what it appends
    for current in order:
        for neighbor in ordered[current]:
            if neighbor not in parent:
                parent[neighbor] = current
                order.append(neighbor)
    return parent


def transitive_targets(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> dict[str, list[str]]:
    """Each node's sorted targets that it reaches only through another node (AD-361).

    A shortest path of one pair comes from `_bfs_parents` of the same ordered graph.
    """
    node_list = sorted(set(nodes))
    adjacency: dict[str, set[str]] = {node: set() for node in node_list}
    for source, target in sorted(set(edges)):
        if source in adjacency and target in adjacency and source != target:
            adjacency[source].add(target)
    ordered = {node: sorted(targets) for node, targets in adjacency.items()}
    reach: dict[str, list[str]] = {}
    for source in node_list:
        parent = _bfs_parents(ordered, source)
        if targets := [t for t in parent if t != source and t not in adjacency[source]]:
            reach[source] = sorted(targets)
    return reach


def condensation_ranks(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Assign deterministic DAG ranks; members of one SCC share a rank."""
    node_list = sorted(set(nodes))
    edge_list = sorted(set(edges))
    components = strongly_connected_components(node_list, edge_list)
    component_index = {
        node: index for index, component in enumerate(components) for node in component
    }
    dag_edges = {
        (component_index[source], component_index[target])
        for source, target in edge_list
        if source in component_index
        and target in component_index
        and component_index[source] != component_index[target]
    }
    predecessors: dict[int, set[int]] = {index: set() for index in range(len(components))}
    successors: dict[int, set[int]] = {index: set() for index in range(len(components))}
    for source, target in dag_edges:
        successors[source].add(target)
        predecessors[target].add(source)
    ready = sorted(index for index, values in predecessors.items() if not values)
    ranks = {index: 0 for index in ready}
    while ready:
        current = ready.pop(0)
        for target in sorted(successors[current]):
            ranks[target] = max(ranks.get(target, 0), ranks[current] + 1)
            predecessors[target].discard(current)
            if not predecessors[target] and target not in ready:
                ready.append(target)
                ready.sort()
    return {node: ranks.get(component_index[node], 0) for node in node_list}
