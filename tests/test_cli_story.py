# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-291: a story is a checked view; the trace proposes its path from the call graph."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_cli_view import ROOT, _observation, _snapshot

from archkeel import cli
from archkeel.cli import main
from archkeel.ir import flow_graph, view_spec
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
    ExternalSystem,
    Function,
    Seam,
    SeamKind,
    Site,
    build_call_graph,
    module_lanes,
    touchpoints,
)
from archkeel.ir.model import EvidenceClass, Observation, Record, RecordData, Section
from archkeel.ir.story import trace_flow, trace_json, trace_summary
from archkeel.ir.view_spec import (
    CandidateEvidence,
    ViewCheckSession,
    ViewStatus,
    call_evidence,
    check_view,
    parse_view_spec,
    snapshot_identity,
    view_check_json,
    view_summary,
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


def test_a_resolved_call_proves_the_step_with_its_call_site(shop: Observation) -> None:
    result = _check(shop, [{"node": MAIN}, {"node": PLACE}])
    first, second = result.steps
    assert first.status is ViewStatus.PROVEN and second.status is ViewStatus.PROVEN
    (site,) = second.evidence
    assert (site.file, site.line, site.kind) == ("shop/cli/main.py", 17, "calls")
    assert not isinstance(site, CandidateEvidence)
    assert "candidates" not in json.loads(view_check_json(result))["steps"][1]["evidence"][0]
    assert site.record_id.startswith("CALL-") and site.evidence_id.startswith("EVD-")
    assert result.story is not None
    start, end = result.story.steps
    assert (start.lane, end.lane) == ("cli", "app")
    assert (start.defined_at.file, start.defined_at.line) == ("shop/cli/main.py", 14)
    assert end.seam is None
    verdict = result.story.verdict
    assert (verdict.proven, verdict.claim, verdict.unknown, verdict.modules) == (2, 0, 0, 2)


def test_a_claim_may_bridge_existing_nodes_but_cannot_invent_one(shop: Observation) -> None:
    existing = _check(shop, [{"node": MAIN}, {"node": PLACE, "claim": True, "note": "boundary"}])
    assert existing.nodes[1].status is ViewStatus.PROVEN
    assert existing.steps[1].status is ViewStatus.CLAIM

    invented = _check(
        shop,
        [{"node": MAIN}, {"node": "shop.cli.main.made_up", "claim": True, "note": "boundary"}],
    )
    assert invented.nodes[1].status is ViewStatus.MISSING
    assert invented.steps[1].status is ViewStatus.MISSING


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_legacy_view_claim_edges_keep_their_original_semantics(
    shop: Observation, version: str
) -> None:
    raw = _spec(shop, [{"node": MAIN}])
    raw.pop("story")
    raw["schema_version"] = version
    invented = "shop.cli.main.made_up"
    raw["nodes"] = [MAIN, invented]
    raw["edges"] = [{"source": MAIN, "target": invented, "claim": True}]

    result = check_view(parse_view_spec(raw), shop, strict=False)

    assert result.edges[0].status is ViewStatus.CLAIM


def test_an_incomplete_snapshot_does_not_claim_a_missing_node(shop: Observation) -> None:
    from archkeel.ir.model import Verdict

    incomplete = replace(shop, coverage=replace(shop.coverage, status=Verdict.FAIL))
    result = _check(
        incomplete,
        [{"node": MAIN}, {"node": "shop.cli.main.made_up", "claim": True, "note": "boundary"}],
    )
    assert result.nodes[1].status is ViewStatus.UNKNOWN
    assert result.steps[1].status is ViewStatus.UNKNOWN
    assert result.snapshot_completeness == "incomplete"
    assert "snapshot is incomplete" in view_summary(result)


def test_view_check_reports_complete_snapshot(shop: Observation) -> None:
    result = _check(shop, [{"node": MAIN}])
    assert result.snapshot_completeness == "complete"
    assert json.loads(view_check_json(result))["snapshot_completeness"] == "complete"


def test_a_partial_call_is_a_claim_with_its_candidate_count_never_proven(shop: Observation) -> None:
    result = _check(shop, [{"node": RENDER}, {"node": TOTAL}])
    link = result.steps[1]
    assert link.status is ViewStatus.CLAIM and link.evidence
    # AD-291: a partial call site carries `candidates`; a proof never has that shape.
    assert all(
        isinstance(site, CandidateEvidence) and site.candidates == 2 for site in link.evidence
    )
    data = json.loads(view_check_json(result))["steps"]
    assert all("candidates" in site for site in data[1]["evidence"])
    assert "partial call" in link.reason and "does not prove" in link.reason
    assert result.story is not None
    seam = result.story.steps[1].seam
    assert seam is not None and seam.kind is SeamKind.PARTIAL_CALL and seam.candidates == 2
    assert (result.story.verdict.proven, result.story.verdict.claim) == (1, 1)


def test_an_unresolved_call_makes_the_step_unknown_and_names_the_seam(shop: Observation) -> None:
    result = _check(shop, [{"node": PLACE}, {"node": SAVE}])
    link = result.steps[1]
    assert link.status is ViewStatus.UNKNOWN and link.evidence == ()
    assert "have no named target" in link.reason
    assert result.story is not None
    seam = result.story.steps[1].seam
    # The dynamic `.save` call and the re-exported `OrderRepository` are two calls without a name.
    assert (seam.kind, seam.node, seam.calls) == (SeamKind.UNRESOLVED_CALL, PLACE, 2)
    assert result.exit_code == 0 and result.story.verdict.unknown == 1


def test_a_function_that_is_not_in_the_snapshot_is_missing(shop: Observation) -> None:
    result = _check(shop, [{"node": MAIN}, {"node": "shop.app.orders.invented"}])
    assert result.nodes[1].status is ViewStatus.MISSING
    assert result.steps[1].status is ViewStatus.MISSING and result.exit_code == 1


def test_an_author_claim_stays_a_claim_when_a_resolved_call_exists(shop: Observation) -> None:
    result = _check(shop, [{"node": MAIN}, {"node": PLACE, "claim": True}])
    link = result.steps[1]
    assert link.status is ViewStatus.CLAIM and link.evidence == ()
    assert result.story is not None and result.story.verdict.proven == 1


def test_author_text_is_never_evidence_and_no_result_says_pass(shop: Observation) -> None:
    forged = "shop/cli/main.py:17 EVD-0000000000000000 CALL-0000000000000000 proven"
    steps = [
        {"node": MAIN, "note": forged, "title": forged, "question": forged},
        {"node": PLACE, "note": forged},
        {"node": SAVE, "note": forged},
    ]
    result = _check(shop, steps)
    text = view_check_json(result)
    data = json.loads(text)
    for link in data["steps"]:
        assert forged not in json.dumps(link["evidence"]) and link["status"] != "pass"
    assert data["steps"][2]["evidence"] == []
    assert data["story"]["steps"][0]["defined_at"]["line"] == 14
    assert "PASS" not in text and "FAIL" not in text
    assert "PASS" not in trace_json(_trace(shop, MAIN, RENDER))


def test_a_spec_without_a_story_keeps_its_result_byte_for_byte(shop: Observation) -> None:
    for path in (EXAMPLE, TOUR):
        raw = json.loads(path.read_text())
        old = check_view(parse_view_spec(raw), shop, strict=False)
        assert "story" not in json.loads(view_check_json(old))
        assert old.story is None
        # Only the version of the spec differs from a 1.2.0 spec that names no story.
        newer = check_view(parse_view_spec({**raw, "schema_version": "1.2.0"}), shop, strict=False)
        assert view_check_json(replace(newer, schema_version=old.schema_version)) == (
            view_check_json(old)
        )


def test_a_function_node_stays_unknown_without_a_story(shop: Observation) -> None:
    raw = _spec(shop, [{"node": MAIN}, {"node": PLACE}])
    del raw["story"]
    raw["steps"] = [{"node": MAIN}, {"node": PLACE}]
    result = check_view(parse_view_spec(raw), shop, strict=False)
    assert {node.status for node in result.nodes} == {ViewStatus.UNKNOWN}
    assert "not a view node" in result.nodes[0].reason


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


def test_chapters_are_named_by_every_step_once_the_story_has_chapters(shop: Observation) -> None:
    chapters = {"id": "s1", "title": "S", "chapters": [{"id": "a", "title": "Start"}]}
    with pytest.raises(ValueError, match=r"steps\[1\] must name a chapter"):
        parse_view_spec(_spec(shop, [{"node": MAIN, "chapter": "a"}, {"node": PLACE}], chapters))
    result = _check(
        shop, [{"node": MAIN, "chapter": "a"}, {"node": PLACE, "chapter": "a"}], chapters
    )
    assert result.story is not None
    assert [step.chapter for step in result.story.steps] == ["a", "a"]
    assert [chapter.title for chapter in result.story.chapters] == ["Start"]


def test_a_function_and_a_module_do_not_form_a_step(shop: Observation) -> None:
    result = _check(shop, [{"node": MAIN}, {"node": "shop.app.orders"}])
    assert result.steps[1].status is ViewStatus.UNKNOWN
    assert "two functions or two modules" in result.steps[1].reason


def test_a_step_names_the_systems_its_module_or_a_called_module_imports(flows: Observation) -> None:
    claims = [
        {"system": "redis", "direction": "reads"},
        {"system": "rabbitmq", "direction": "writes"},
    ]
    result = _check(flows, [{"node": START, "external": claims}, {"node": FETCH}])
    assert result.story is not None
    start, fetch = result.story.steps
    seen = {item.system: item for item in start.external}
    # start itself imports nothing; fetch is called by a resolved call, so its module counts.
    assert set(seen) == {
        ExternalSystem.REDIS,
        ExternalSystem.RELATIONAL_DATABASE,
        ExternalSystem.OBJECT_STORAGE,
        ExternalSystem.RABBITMQ,
    }
    redis = seen[ExternalSystem.REDIS]
    assert redis.touched and redis.direction == "reads"
    (touch,) = redis.evidence
    assert (touch.library, touch.module) == ("redis", "shop.store.cache")
    assert touch.site.record_id.startswith("IMP-") and touch.site.file == "shop/store/cache.py"
    assert touch.site.line == 10
    assert seen[ExternalSystem.OBJECT_STORAGE].evidence[0].library == "azure.storage.blob"
    assert seen[ExternalSystem.RELATIONAL_DATABASE].evidence[0].library == "sqlalchemy.orm"
    # The direction is a claim: a claim without an import is not touched and has no evidence.
    rabbit = seen[ExternalSystem.RABBITMQ]
    assert not rabbit.touched and rabbit.evidence == () and rabbit.direction == "writes"
    assert all(item.direction is None for item in fetch.external)
    assert result.story.verdict.systems == (
        ExternalSystem.OBJECT_STORAGE,
        ExternalSystem.REDIS,
        ExternalSystem.RELATIONAL_DATABASE,
    )


def test_a_lookalike_module_or_a_type_only_import_touches_no_system(flows: Observation) -> None:
    result = _check(flows, [{"node": "shop.store.redis_cache.ping"}])
    assert result.story is not None and result.story.steps[0].external == ()
    libraries = {
        touch.library
        for step in _check(flows, [{"node": FETCH}]).story.steps
        for item in step.external
        for touch in item.evidence
    }
    # redis_tools and shop.store.redis_cache only look like redis; kafka is a TYPE_CHECKING import.
    assert libraries == {"redis", "sqlalchemy.orm", "azure.storage.blob"}


def test_a_story_of_a_stale_snapshot_has_no_facts(shop: Observation) -> None:
    raw = _spec(shop, [{"node": MAIN}, {"node": PLACE}])
    raw["snapshot"]["source_digest"] = "0" * 64
    result = check_view(parse_view_spec(raw), shop, strict=False)
    assert result.exit_code == 2 and result.story is not None
    assert all(
        step.lane is None and step.seam is None and step.defined_at is None
        for step in result.story.steps
    )
    assert result.story.verdict.unknown == 2 and result.story.verdict.modules == 0


def test_a_lane_is_the_owning_component_else_the_second_name(shop: Observation) -> None:
    lanes = module_lanes(shop, ["shop.cli.main", "other.alpha.beta", "single"])
    assert lanes == {"shop.cli.main": "cli", "other.alpha.beta": "alpha", "single": "single"}


def test_the_story_result_and_spec_match_their_schemas(flows: Observation) -> None:
    steps = [
        {
            "node": START,
            "chapter": "a",
            "title": "Start",
            "question": "Why?",
            "note": "Text",
            "external": [{"system": "redis", "direction": "touches"}],
        },
        {"node": LEFT, "chapter": "a"},
        {"node": DYNAMIC, "chapter": "a"},
    ]
    story = {"id": "s1", "title": "S", "chapters": [{"id": "a", "title": "A"}]}
    raw = _spec(flows, steps, story)
    spec_schema = json.loads((ROOT / "schema/view-spec.schema.json").read_text())
    validator = Draft202012Validator(spec_schema)
    assert not list(validator.iter_errors(raw))
    for older in ("1.0.0", "1.1.0"):
        assert not validator.is_valid({**raw, "schema_version": older})
    plain = {key: value for key, value in raw.items() if key != "story"}
    plain["steps"] = [{"node": START, "note": "n"}]
    assert validator.is_valid({**plain, "schema_version": "1.0.0"})
    result = check_view(parse_view_spec(raw), flows, strict=False)
    check_schema = json.loads((ROOT / "schema/view-check.schema.json").read_text())
    assert not list(
        Draft202012Validator(check_schema).iter_errors(json.loads(view_check_json(result)))
    )


def test_view_check_runs_a_story_from_the_command_line(
    shop: Observation, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot, spec = tmp_path / "architecture.json", tmp_path / "story.json"
    snapshot.write_bytes(_snapshot(tmp_path / "cli"))
    spec.write_text(json.dumps(_spec(shop, [{"node": MAIN}, {"node": PLACE}])))
    assert main(["view", "check", str(spec), "--snapshot", str(snapshot), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["story"]["verdict"]["proven"] == 2


def test_the_trace_lists_a_proven_path_with_lanes_and_lines(shop: Observation) -> None:
    result = _trace(shop, MAIN, INDENT)
    (path,) = result.paths
    assert [hop.node.name for hop in path.hops] == [RENDER, INDENT]
    assert {hop.status for hop in path.hops} == {ViewStatus.PROVEN}
    assert (path.start.lane, path.hops[0].node.lane) == ("cli", "render")
    assert path.hops[0].evidence[0].line == 20 and path.hops[0].node.defined_at.line == 11
    assert path.seams == ()


def test_trace_display_labels_use_source_paths_without_changing_canonical_names(
    shop: Observation,
) -> None:
    result = _trace(shop, MAIN, INDENT)
    path = result.paths[0]
    assert path.start.name == MAIN
    assert path.start.label == "shop/cli/main.py:14 · main"
    assert "shop/cli/main.py:14 · main" in trace_json(result)
    assert "shop/cli/main.py:14 · main" in trace_summary(result)


def test_a_view_check_session_builds_the_snapshot_graph_once(
    shop: Observation, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = view_spec._view_graph
    calls = 0

    def counted(observation: Observation, *, story: bool):
        nonlocal calls
        calls += 1
        return original(observation, story=story)

    monkeypatch.setattr(view_spec, "_view_graph", counted)
    session = ViewCheckSession(shop)
    spec = parse_view_spec(_spec(shop, [{"node": MAIN}, {"node": PLACE}]))
    session.check(spec, strict=False)
    session.check(spec, strict=False)
    assert calls == 1


def test_story_checker_cache_is_cleared_for_a_new_snapshot_run(
    shop: Observation, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[Path] = []

    def read(path: Path) -> Observation:
        loaded.append(path)
        return shop

    monkeypatch.setattr(cli, "read_saved_snapshot", read)
    snapshot = tmp_path / "architecture.json"
    snapshot.touch()
    spec = json.dumps(_spec(shop, [{"node": MAIN}])).encode()
    check, clear = cli._story_checker()
    check(spec, snapshot)
    check(spec, snapshot)
    assert loaded == [snapshot]
    clear()
    check(spec, snapshot)
    assert loaded == [snapshot, snapshot]


def test_a_path_through_a_partial_call_is_a_claim_with_a_seam(shop: Observation) -> None:
    (path,) = _trace(shop, MAIN, TOTAL).paths
    assert [hop.status for hop in path.hops] == [ViewStatus.PROVEN, ViewStatus.CLAIM]
    seam = path.hops[1].seam
    assert seam is not None and seam.candidates == 2 and seam in path.seams
    assert path.hops[0].seam is None


def test_unresolved_calls_are_seams_of_the_function_never_hops(shop: Observation) -> None:
    result = _trace(shop, MAIN)
    placed = next(path for path in result.paths if path.hops[-1].node.name == PLACE)
    assert [seam.kind for seam in placed.seams] == [SeamKind.UNRESOLVED_CALL]
    assert placed.seams[0].node == PLACE
    assert SAVE not in {hop.node.name for path in result.paths for hop in path.hops}
    assert {hop.status for path in result.paths for hop in path.hops} == {ViewStatus.PROVEN}


def test_two_paths_come_in_a_fixed_order_and_a_cycle_does_not_repeat_a_node(
    flows: Observation,
) -> None:
    first = _trace(flows, START, FINISH)
    assert [[hop.node.name for hop in path.hops] for path in first.paths] == [
        [LEFT, FINISH],
        [RIGHT, FINISH],
    ]
    assert trace_json(first) == trace_json(_trace(flows, START, FINISH))
    # again() calls start(): the path to it must not loop back through start.
    for path in _trace(flows, START, AGAIN, max_paths=9).paths:
        names = [path.start.name, *(hop.node.name for hop in path.hops)]
        assert len(names) == len(set(names))
    assert len(_trace(flows, START, AGAIN, max_paths=9).paths) == 2


def test_the_trace_limits_paths_and_hops(flows: Observation) -> None:
    assert len(_trace(flows, START, FINISH, max_paths=1).paths) == 1
    assert _trace(flows, START, FINISH, max_hops=1).paths == ()
    assert _trace(flows, START, FINISH, max_hops=2).paths != ()


def test_no_path_is_an_empty_list_and_a_bad_name_is_an_error(flows: Observation) -> None:
    assert _trace(flows, FINISH, "shop.render.text._indent").paths == ()
    with pytest.raises(ValueError, match="--to .* not a function"):
        _trace(flows, START, "shop.app.flow.nothing")
    with pytest.raises(ValueError, match="--from"):
        _trace(flows, "shop.app.flow", FINISH)
    with pytest.raises(ValueError, match="same function"):
        _trace(flows, START, START)
    with pytest.raises(ValueError, match="at least 1"):
        _trace(flows, START, FINISH, max_paths=0)


def test_the_trace_lists_the_systems_touched_on_the_path(flows: Observation) -> None:
    (path,) = _trace(flows, START, FETCH).paths
    assert path.systems == (
        ExternalSystem.OBJECT_STORAGE,
        ExternalSystem.REDIS,
        ExternalSystem.RELATIONAL_DATABASE,
    )
    assert path.start.external and path.hops[0].node.external


def test_a_search_that_spends_its_work_says_it_is_incomplete(
    flows: Observation, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _trace(flows, START, AGAIN).complete
    monkeypatch.setattr(flow_graph, "WORK_LIMIT", 1)
    assert not _trace(flows, START, AGAIN).complete


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


def test_a_hop_limit_above_the_bound_is_an_input_error(flows: Observation) -> None:
    assert _trace(flows, START, FINISH, max_hops=MAX_HOPS).paths
    with pytest.raises(ValueError, match="--max-hops from 1 to 100"):
        _trace(flows, START, FINISH, max_hops=MAX_HOPS + 1)


def test_the_trace_command_prints_json_and_exits_2_on_a_bad_name(
    shop: Observation, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(_snapshot(tmp_path / "cli"))
    base = ["story", "trace", "--snapshot", str(snapshot), "--json"]
    assert main([*base, "--from", MAIN, "--to", RENDER]) == 0
    printed = capsys.readouterr().out
    assert printed == trace_json(_trace(shop, MAIN, RENDER))
    schema = json.loads((ROOT / "schema/story-trace.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(printed)))
    assert main([*base, "--from", "shop.cli.main.nope"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert (
        out["command"] == "story"
        and "not a function or method" in out["diagnostics"][0]["unknown_claim"]
    )
    assert main([*base, "--from", MAIN, "--max-hops", "0"]) == 2
    capsys.readouterr()
    snapshot.write_text("{}")
    assert main([*base, "--from", MAIN]) == 2


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


def test_a_missing_call_is_missing_only_without_a_gap_and_without_the_call_limit(
    flows: Observation, limitless: Observation
) -> None:
    pairs = [{"node": ONE}, {"node": THREE}]
    # Control: the module has no gap, so ONE -> TWO is proven and ONE -> THREE is really absent.
    assert _check(limitless, [{"node": ONE}, {"node": TWO}]).steps[1].status is ViewStatus.PROVEN
    absent = _check(limitless, pairs).steps[1]
    assert absent.status is ViewStatus.MISSING and "coverage is complete" in absent.reason
    assert _check(limitless, pairs).exit_code == 1
    # The same pair under the dynamic call limit of the full snapshot is unknown (AD-284).
    limited = _check(flows, pairs).steps[1]
    assert limited.status is ViewStatus.UNKNOWN and "dynamic" in limited.reason


def test_a_module_with_a_call_gap_makes_an_absent_call_unknown_not_missing(
    limitless: Observation,
) -> None:
    # render_order calls builtins, so its module has a gap: an absent call is not proven absent.
    result = _check(limitless, [{"node": RENDER}, {"node": "shop.app.orders.summarize"}])
    link = result.steps[1]
    assert link.status is ViewStatus.UNKNOWN and "re-exported" in link.reason
    assert result.exit_code == 0


def test_two_functions_relate_by_calls_only(flows: Observation) -> None:
    link = _check(flows, [{"node": START}, {"node": LEFT, "kind": "imports"}]).steps[1]
    assert link.status is ViewStatus.UNKNOWN and "calls, not imports" in link.reason


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


def test_the_no_target_trace_lists_more_hops_first(flows: Observation) -> None:
    names = [path.hops[-1].node.name for path in _trace(flows, START, max_paths=9).paths]
    assert names == [
        AGAIN,
        FINISH,
        "shop.store.redis_cache.ping",
        DYNAMIC,
        LEFT,
        RIGHT,
        FETCH,
    ]
    depths = [len(path.hops) for path in _trace(flows, START, max_paths=9).paths]
    assert depths == sorted(depths, reverse=True)


def test_a_trace_is_the_same_text_under_other_hash_seeds(
    flows_packet: bytes, tmp_path: Path
) -> None:
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(flows_packet)
    command = [
        sys.executable, "-m", "archkeel.cli", "story", "trace", "--from", START, "--to", AGAIN,
        "--snapshot", str(snapshot), "--max-paths", "9", "--json",
    ]  # fmt: skip
    outputs = [
        subprocess.run(
            command,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
        ).stdout
        for seed in ("1", "2", "31337")
    ]
    assert outputs[0] and outputs[0] == outputs[1] == outputs[2]


def test_a_null_story_key_is_invalid_before_version_1_2_0_as_in_the_schema(
    shop: Observation,
) -> None:
    raw = _spec(shop, [{"node": MAIN, "chapter": None}])
    del raw["story"]
    raw["schema_version"] = "1.1.0"
    schema = json.loads((ROOT / "schema/view-spec.schema.json").read_text())
    assert not Draft202012Validator(schema).is_valid(raw)
    with pytest.raises(ValueError, match="1.2.0"):
        parse_view_spec(raw)
