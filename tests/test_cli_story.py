# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-291: a story is a checked view; the trace proposes its path from the call graph."""

from dataclasses import replace

import pytest
from test_cli_view import ROOT, _observation, _snapshot

from archkeel.ir import flow_graph
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Entity,
    EntityKind,
    OriginKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ResolutionKind,
)
from archkeel.ir.flow_graph import (
    MAX_HOPS,
    CallEdge,
    CallGraph,
    Function,
    Seam,
    SeamKind,
    Site,
    build_call_graph,
    touchpoints,
)
from archkeel.ir.model import EvidenceClass, Observation, Record, RecordData, Section
from archkeel.ir.story import trace_flow
from archkeel.ir.view_spec import (
    call_evidence,
    check_view,
    parse_view_spec,
    snapshot_identity,
)

EXAMPLE = ROOT / "fixtures/F-architecture-view/place-order.json"
TOUR = ROOT / "fixtures/F-architecture-view/first-contact-tour.json"
MAIN = "shop.cli.main.main"
PLACE = "shop.app.orders.place_order"
SAVE = "shop.store.repository.OrderRepository.save"
ENCODE = "shop.store.codec.encode"
RENDER = "shop.render.text.render_order"
TOTAL = "shop.model.entities.Order.total"
INDENT = "shop.render.text._indent"
START, LEFT, RIGHT, FINISH, AGAIN = (
    f"shop.app.flow.{name}" for name in ("start", "left", "right", "finish", "again")
)
DYNAMIC, FETCH = "shop.app.flow.dynamic", "shop.store.cache.fetch"
ONE, TWO, THREE = (f"shop.app.pure.{name}" for name in ("one", "two", "three"))
_HEADER = (ROOT / "fixtures/F-architecture/shop/render/text.py").read_text().split('"""')[0]
# A diamond (start-left-finish, start-right-finish), a cycle (again calls start) and one call
# whose target the analysis cannot name (dynamic).
_FLOW = '''"""Calls that form a diamond and a cycle."""

from __future__ import annotations

from shop.store.cache import fetch


def start(box: object) -> int:
    return left() + right() + dynamic(box) + fetch("k")


def left() -> int:
    return finish()


def right() -> int:
    return finish()


def finish() -> int:
    return again()


def again() -> int:
    return start(object())


def dynamic(box: object) -> int:
    return box.go()
'''
# Client libraries: a dotted prefix, a type-only import, and names that only look like a library.
_CACHE = '''"""Fetch a value through external clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis
import redis_tools
from azure.storage.blob import BlobClient
from shop.store.redis_cache import ping
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    import kafka


def fetch(key: str) -> str:
    return key + str(ping()) + redis.__name__ + redis_tools.__name__ + BlobClient.__name__ + (
        Session.__name__
    )
'''
_PURE = '''"""Functions that call no builtin, so the module has no call gap."""

from __future__ import annotations


def one() -> int:
    return two()


def two() -> int:
    return 1


def three() -> int:
    return 3
'''
_LOOKALIKE = '''"""A module that is named like a library and imports none."""

from __future__ import annotations


def ping() -> int:
    return 1
'''


@pytest.fixture(scope="module")
def shop(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    return _observation(_snapshot(tmp_path_factory.mktemp("story-clean")))


@pytest.fixture(scope="module")
def flows_packet(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    overlay = {
        "shop/app/flow.py": _HEADER + _FLOW,
        "shop/app/pure.py": _HEADER + _PURE,
        "shop/store/cache.py": _HEADER + _CACHE,
        "shop/store/redis_cache.py": _HEADER + _LOOKALIKE,
    }
    return _snapshot(tmp_path_factory.mktemp("story-flows"), overlay)


@pytest.fixture(scope="module")
def flows(flows_packet: bytes) -> Observation:
    return _observation(flows_packet)


@pytest.fixture(scope="module")
def limitless(flows: Observation) -> Observation:
    """No call limit and no call from a scope without a module (a comprehension).

    Both set a snapshot-wide call gap (`everywhere`); without them an absent call can be missing.
    """
    kept = {
        "unknowns": lambda r: r.kind != "dynamic_call_limit",
        "calls": lambda r: "<" not in str(r.data.get("source_scope")),
    }
    sections = tuple(
        Section(item.name, tuple(r for r in item.records if kept[item.name](r)))
        if item.name in kept
        else item
        for item in flows.sections
    )
    return replace(flows, sections=sections)


def _spec(
    observation: Observation, steps: list[dict], story: dict | None = None, **fields: object
) -> dict:
    identity = snapshot_identity(observation)
    spec: dict = {
        "schema_version": "1.2.0",
        "title": "A story",
        "snapshot": {
            "source_digest": identity.source_digest,
            "contract_digest": identity.contract_digest,
        },
        "nodes": list(dict.fromkeys(step["node"] for step in steps)),
        "steps": steps,
        "story": story or {"id": "s1", "title": "Story one"},
    }
    spec.update(fields)
    return spec


def _check(observation: Observation, steps: list[dict], story: dict | None = None, **fields):
    return check_view(
        parse_view_spec(_spec(observation, steps, story, **fields)), observation, strict=False
    )


def _trace(observation: Observation, source: str, target: str | None = None, **limits: int):
    return trace_flow(observation, source, target, **{"max_paths": 5, "max_hops": 12, **limits})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.update(schema_version="1.1.0"), "1.2.0"),
        (lambda s: (s.pop("story"), s["steps"][0].update(title="T")), "need a story"),
        (lambda s: s["story"].update(chapters=[{"id": "a", "title": "A"}] * 2), "unique"),
        (lambda s: s["story"].update(id=""), "story.id"),
        (lambda s: s["story"].update(status="proven"), "allows only"),
        (lambda s: s["steps"][0].update(chapter="nowhere"), "names no chapter"),
        (
            lambda s: s["steps"][0].update(external=[{"system": "ldap", "direction": "reads"}]),
            "one of",
        ),
        (
            lambda s: s["steps"][0].update(external=[{"system": "redis", "direction": "sends"}]),
            "one of",
        ),
        (
            lambda s: s["steps"][0].update(
                external=[{"system": "redis", "direction": "reads"}] * 2
            ),
            "twice",
        ),
        (
            lambda s: s["steps"][0].update(
                external=[{"system": "redis", "direction": "reads", "status": "proven"}]
            ),
            "allows only",
        ),
    ],
)
def test_story_fields_are_closed_and_need_version_1_2_0(shop: Observation, change, message) -> None:
    raw = _spec(shop, [{"node": MAIN}, {"node": PLACE}])
    change(raw)
    with pytest.raises(ValueError, match=message):
        parse_view_spec(raw)


def test_a_wide_dispatch_is_searched_in_bounded_work_and_proven_paths_come_first() -> None:
    """58 candidates at two levels (the EE shape), and a longer path of resolved calls only."""
    width = 58
    chain = ("root", "p1", "p2", "p3", "sink")
    functions = {
        name: Function(name, EntityKind.FUNCTION, "m", name, Site(name))
        for name in (*chain, *(f"a{i}" for i in range(width)), *(f"b{i}" for i in range(width)))
    }
    seam = Seam(SeamKind.PARTIAL_CALL, "root", None, candidates=width)
    edges: dict[str, dict[str, CallEdge]] = {
        "root": {f"a{i}": CallEdge("root", f"a{i}", (), (seam,)) for i in range(width)}
    }
    edges["root"]["p1"] = CallEdge("root", "p1", ())
    edges["p1"] = {"p2": CallEdge("p1", "p2", ())}
    edges["p2"] = {"p3": CallEdge("p2", "p3", ())}
    edges["p3"] = {"sink": CallEdge("p3", "sink", ())}
    for i in range(width):
        edges[f"a{i}"] = {f"b{j}": CallEdge(f"a{i}", f"b{j}", (), (seam,)) for j in range(width)}
        edges[f"b{i}"] = {"sink": CallEdge(f"b{i}", "sink", ())}
    edges["root"] = dict(sorted(edges["root"].items()))
    search = flow_graph.find_paths(
        CallGraph(functions, edges, {}, {}), "root", "sink", max_paths=5, max_hops=12
    )
    assert search.complete and len(search.paths) == 5
    named = [[edge.target for edge in path] for path in search.paths]
    # The proven path has 4 hops and the seam paths have 3, yet the proven path comes first.
    assert named[0] == ["p1", "p2", "p3", "sink"]
    assert named[1] == ["a0", "b0", "sink"]
    assert all(edge.seam is None for edge in search.paths[0])
    assert all(any(edge.seam for edge in path) for path in search.paths[1:])


def test_the_walk_is_bounded_by_the_hop_limit() -> None:
    length = MAX_HOPS
    names = [f"f{i}" for i in range(length + 1)]
    functions = {n: Function(n, EntityKind.FUNCTION, "m", n, Site(n)) for n in names}
    edges = {a: {b: CallEdge(a, b, ())} for a, b in zip(names, names[1:], strict=False)}
    search = flow_graph.find_paths(
        CallGraph(functions, edges, {}, {}), names[0], names[-1], max_paths=1, max_hops=MAX_HOPS
    )
    assert len(search.paths[0]) == length and search.complete


# ---------- gaps, seams and the order of the answer ----------
def _module(name: str) -> Entity:
    return Entity(f"MOD-{name}", EntityKind.MODULE, name, "python", presence=PresenceKind.DEFINED)


def _function(module: str, name: str) -> Entity:
    return Entity(
        f"FN-{module}.{name}",
        EntityKind.FUNCTION,
        f"{module}.{name}",
        "python",
        parent_id=f"MOD-{module}",
        presence=PresenceKind.DEFINED,
    )


def _call(source: str, resolution: ResolutionKind, target: str | None = None, **fields):
    identity = f"CALL-{source}-{target}-{resolution}-{len(fields)}"
    return Relationship(identity, RelationshipKind.CALLS, source, target, resolution, **fields)


def _import(module: str, library: str, identity: str = "IMP-1") -> Record:
    entries = (("source_module", module), ("target_module", library))
    return Record(
        identity, EvidenceClass.FACT, "dependencies", "import", "Import", (), (), (), (), (),
        RecordData(entries),
    )  # fmt: skip


def _calls(entities: list[Entity], relationships: list[Relationship], imports=()):
    graph = ArchitectureGraph(OriginKind.OBSERVED, tuple(entities), tuple(relationships), (), ())
    return build_call_graph(graph, imports)


def test_a_truncated_partial_call_and_a_re_export_are_seams_not_silence() -> None:
    modules = [_module("pkg"), _module("other")]
    functions = [_function("pkg", "run"), _function("pkg", "known"), _function("other", "x")]
    reexport = Entity(
        "REF-1", EntityKind.SYMBOL, "pkg.Thing", "python", presence=PresenceKind.REFERENCED
    )
    builtin = Entity(
        "REF-2", EntityKind.SYMBOL, "builtins.sorted", "python", presence=PresenceKind.REFERENCED
    )
    source = "FN-pkg.run"
    calls = _calls(
        [*modules, *functions, reexport, builtin],
        [
            _call(
                source,
                ResolutionKind.PARTIAL,
                candidate_ids=("FN-pkg.known",),
                candidate_count=60,
                candidates_truncated=True,
            ),
            _call(source, ResolutionKind.RESOLVED, "REF-2"),
        ],
    )
    seam = calls.unresolved["pkg.run"]
    assert seam.kind is SeamKind.UNRESOLVED_CALL and seam.calls == 1
    assert "only some" in (seam.reason or "")
    assert calls.edges["pkg.run"]["pkg.known"].seam is not None
    more = _calls(
        [*modules, *functions, reexport, builtin],
        [
            _call(source, ResolutionKind.RESOLVED, "REF-1"),
            _call(source, ResolutionKind.RESOLVED, "REF-2"),
        ],
    )
    # The re-export of the project is a seam; a builtin (a name outside the project) is not.
    assert more.unresolved["pkg.run"].calls == 1
    assert "re-export" in (more.unresolved["pkg.run"].reason or "")


def test_a_resolved_call_wins_over_a_partial_call_to_the_same_pair() -> None:
    entities = [_module("m"), _function("m", "a"), _function("m", "b")]
    calls = _calls(
        entities,
        [
            _call("FN-m.a", ResolutionKind.PARTIAL, candidate_ids=("FN-m.b",), candidate_count=1),
            _call("FN-m.a", ResolutionKind.RESOLVED, "FN-m.b"),
        ],
    )
    edge = calls.edges["m.a"]["m.b"]
    assert edge.seam is None and len(edge.sites) == 1


def test_each_partial_call_site_keeps_its_own_candidate_count_and_reason() -> None:
    entities = [_module("m"), _function("m", "a"), _function("m", "b"), _function("m", "c")]
    narrow = _call(
        "FN-m.a", ResolutionKind.PARTIAL, candidate_ids=("FN-m.b", "FN-m.c"), candidate_count=2
    )
    wide = _call(
        "FN-m.a",
        ResolutionKind.PARTIAL,
        candidate_ids=("FN-m.b",),
        candidate_count=7,
        reason="dynamic receiver",
    )
    calls = _calls(entities, [narrow, replace(wide, id="CALL-wide")])
    edge = calls.edges["m.a"]["m.b"]
    assert [site.record_id for site in edge.sites] == [narrow.id, "CALL-wide"]
    assert [seam.candidates for seam in edge.seams] == [2, 7]
    assert [seam.reason for seam in edge.seams] == [None, "dynamic receiver"]
    assert [site.candidates for site in call_evidence(edge)] == [2, 7]


def test_a_callee_reached_by_a_partial_call_adds_no_touchpoint() -> None:
    entities = [_module("m"), _module("n"), _function("m", "a"), _function("n", "b")]
    imports = [_import("n", "redis")]
    partial = _call("FN-m.a", ResolutionKind.PARTIAL, candidate_ids=("FN-n.b",), candidate_count=1)
    resolved = _call("FN-m.a", ResolutionKind.RESOLVED, "FN-n.b")
    guessed = _calls(entities, [partial], imports)
    assert touchpoints(guessed, "m.a") == () and touchpoints(guessed, "n.b")
    assert touchpoints(_calls(entities, [resolved], imports), "m.a")


def test_a_first_party_package_named_like_a_client_library_is_not_that_library() -> None:
    entities = [_module("redis.client"), _module("app"), _function("app", "a")]
    foreign = _import("app", "redis.client", "IMP-1")
    external = _import("app", "kafka", "IMP-2")
    calls = _calls(entities, [], [foreign, external])
    assert [touch.library for touch in calls.touches["app"]] == ["kafka"]
