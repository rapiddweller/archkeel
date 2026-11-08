# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""transitive_paths walks once per source and returns what one search per pair returned."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable

import pytest

from archkeel.ir.graph import transitive_paths


def _shortest_path(adjacency: dict[str, set[str]], source: str, target: str) -> list[str] | None:
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


def _one_search_per_pair(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    """The earlier definition: one shortest_path call for each ordered pair of nodes."""
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
            path = _shortest_path(adjacency, source, target)
            if path is not None:
                paths.append(path)
    return paths


def _random_graph(seed: int) -> tuple[list[str], list[tuple[str, str]]]:
    rng = random.Random(seed)
    names = [f"n{index:02d}" for index in range(rng.randint(0, 14))]
    nodes = [*names, *rng.sample(names, k=len(names) // 3)]  # repeated nodes
    edges: list[tuple[str, str]] = []
    if names:
        for _ in range(rng.randint(0, 3 * len(names))):
            edges.append((rng.choice(names), rng.choice(names)))  # cycles and self loops
        edges.extend(edges[: len(edges) // 4])  # parallel edges
        edges.append((rng.choice(names), "outside"))  # an end that is no node
        edges.append(("outside", rng.choice(names)))
    return nodes, edges


@pytest.mark.parametrize("seed", range(300))
def test_transitive_paths_equal_one_search_per_pair(seed: int) -> None:
    nodes, edges = _random_graph(seed)
    assert transitive_paths(nodes, edges) == _one_search_per_pair(nodes, edges)


def test_transitive_paths_cover_cycles_self_loops_parallel_edges_and_islands() -> None:
    nodes = ["a", "b", "c", "d", "e", "island"]
    edges = [("a", "b"), ("a", "b"), ("b", "c"), ("c", "a"), ("c", "c"), ("c", "d"), ("d", "e")]
    paths = transitive_paths(nodes, edges)
    assert paths == _one_search_per_pair(nodes, edges)
    assert ["a", "b", "c"] in paths
    assert ["a", "b", "c", "d", "e"] in paths
    assert not any("island" in path for path in paths)
    assert not any(len(path) == 2 for path in paths)  # a direct edge is no transitive path
