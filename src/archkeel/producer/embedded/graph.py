# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Deterministic graph operations used by the architecture analyzer."""

from __future__ import annotations

from collections import deque
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


def shortest_path(adjacency: dict[str, set[str]], source: str, target: str) -> list[str] | None:
    """Return the lexicographically deterministic shortest directed path."""
    queue: deque[list[str]] = deque([[source]])
    seen = {source}
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == target:
            return path
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append([*path, neighbor])
    return None


def transitive_paths(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    node_list = sorted(set(nodes))
    adjacency: dict[str, set[str]] = {node: set() for node in node_list}
    for source, target in sorted(set(edges)):
        if source in adjacency and target in adjacency and source != target:
            adjacency[source].add(target)
    paths: list[list[str]] = []
    for source in node_list:
        for target in node_list:
            if source == target or target in adjacency[source]:
                continue
            path = shortest_path(adjacency, source, target)
            if path is not None:
                paths.append(path)
    return paths


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
