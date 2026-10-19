# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Usage ownership depends on frozen modules and scopes, not edge multiplicity."""

from dataclasses import replace
from random import Random

import pytest

from archkeel.ir import report_projection as projection
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    ComponentRole,
    Entity,
    EntityKind,
    OriginKind,
    Relationship,
    RelationshipKind,
)


def _graphs():
    intents = (
        ComponentIntent("app", ComponentRole.COMPONENT, packages=("app",)),
        ComponentIntent("other", ComponentRole.COMPONENT, packages=("other",)),
        ComponentIntent(
            "nested", ComponentRole.COMPONENT, packages=("app.inner",), parent_id="app"
        ),
        ComponentIntent(
            "leaf", ComponentRole.COMPONENT, exact_modules=("app.inner.leaf",), parent_id="nested"
        ),
        ComponentIntent(
            "overlap", ComponentRole.COMPONENT, packages=("app.overlap",), parent_id="app"
        ),
        ComponentIntent(
            "overlap2", ComponentRole.COMPONENT, packages=("app.overlap",), parent_id="app"
        ),
        ComponentIntent(
            "outside-child", ComponentRole.COMPONENT, packages=("outside",), parent_id="app"
        ),
    )
    names = (
        "app.base",
        "app.inner.leaf",
        "app.inner.empty",
        "app.overlap.x",
        "other.x",
        "outside.x",
    )
    target = ArchitectureGraph(OriginKind.DECLARED, component_intents=intents)
    observed = ArchitectureGraph(
        OriginKind.OBSERVED,
        entities=tuple(
            Entity(str(i), EntityKind.MODULE, name, "python") for i, name in enumerate(names)
        ),
    )
    return target, observed


def _reference(target, observed):
    entities = {item.id: item for item in observed.entities}
    counts, levels = {}, {}
    for edge in observed.relationships:
        if edge.kind != RelationshipKind.IMPORTS or edge.target_id is None:
            continue
        source, endpoint = entities[edge.source_id], entities[edge.target_id]
        a = projection._deepest_owners(target, source.qualified_name)
        b = projection._deepest_owners(target, endpoint.qualified_name)
        pairs = {(a[0], b[0])} if len(a) == len(b) == 1 and a != b else set()
        for parent in {item.parent_id for item in target.component_intents}:
            a = projection._scope_owners(target, source.qualified_name, parent)
            b = projection._scope_owners(target, endpoint.qualified_name, parent)
            if len(a) == len(b) == 1 and a != b:
                key = (parent, a[0], b[0])
                levels[key] = levels.get(key, 0) + 1
                pairs.add((a[0], b[0]))
        for pair in pairs:
            counts[pair] = counts.get(pair, 0) + 1
    return counts, levels


@pytest.mark.parametrize("seed", range(8))
def test_usage_matches_previous_algorithm_for_nested_ambiguous_and_missing_owners(seed):
    target, observed = _graphs()
    random = Random(seed)
    edges = tuple(
        Relationship(
            str(i), RelationshipKind.IMPORTS, str(random.randrange(6)), str(random.randrange(6))
        )
        for i in range(120)
    )
    edges += (
        Relationship("unresolved", RelationshipKind.IMPORTS, "0"),
        Relationship("ignored", RelationshipKind.CALLS, "0", "4"),
    )
    observed = replace(observed, relationships=edges)
    assert projection._usage_counts(target, observed) == _reference(target, observed)
    assert projection._deepest_owners(target, "app.inner.empty") == ("nested",)
    assert projection._deepest_owners(target, "app.overlap.x") == ("overlap", "overlap2")
    assert projection._deepest_owners(target, "outside.x") == ()
    changed = replace(target, component_intents=target.component_intents[:2])
    assert projection._usage_counts(changed, observed) == _reference(changed, observed)
    assert projection._usage_counts(target, replace(observed, relationships=())) == ({}, {})


def test_repeated_edges_do_not_repeat_module_ownership_work(monkeypatch):
    target, observed = _graphs()
    original = projection.module_in_ownership
    visits = 0

    def counted(module, packages, exact_modules):
        nonlocal visits
        visits += 1
        return original(module, packages, exact_modules)

    monkeypatch.setattr(projection, "module_in_ownership", counted)
    edge = Relationship("edge", RelationshipKind.IMPORTS, "1", "4")
    once = projection._usage_counts(target, replace(observed, relationships=(edge,)))
    once_visits = visits
    visits = 0
    many = projection._usage_counts(
        target,
        replace(observed, relationships=tuple(replace(edge, id=f"edge-{i}") for i in range(100))),
    )
    assert many == tuple({key: value * 100 for key, value in counts.items()} for counts in once)
    assert visits == once_visits


def test_ambiguous_ancestor_blocks_nested_ownership_and_empty_target_stays_unowned():
    target, observed = _graphs()
    target = replace(
        target,
        component_intents=target.component_intents
        + (ComponentIntent("ambiguous-app", ComponentRole.COMPONENT, packages=("app",)),),
    )
    observed = replace(
        observed,
        relationships=(Relationship("edge", RelationshipKind.IMPORTS, "1", "4"),),
    )
    assert projection._deepest_owners(target, "app.inner.leaf") == ("ambiguous-app", "app")
    assert projection._scope_owners(target, "app.inner.leaf", "nested") == ()
    assert projection._usage_counts(target, observed) == ({}, {})
    empty = replace(target, component_intents=())
    assert projection._usage_counts(empty, observed) == ({}, {})
