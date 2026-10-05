# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Class assignments retain field identities without inventing type proof."""

from test_member_inventory import _coverage, _observation, _target

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.codec import decode_json
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.source_graph import observed_graph


def test_class_assignments_do_not_expand_the_native_public_field_inventory(tmp_path):
    observation = _observation(
        tmp_path, "class Data:\n object = str\n value: object\n _secret: str\n"
    )
    owner = next(
        r
        for r in observation.records("symbols") or ()
        if r.data.get("qualified_name") == "sample.model.Data"
    )
    fields = owner.data.get("fields")
    assert fields is not None
    assert [(field.get("name"), field.get("annotation")) for field in fields] == [
        ("value", "object")
    ]
    graph = observed_graph(observation)
    assert {
        e.qualified_name.rsplit(".", 1)[-1] for e in graph.entities if e.kind == "attribute"
    } == {"object", "value", "_secret"}


def test_unannotated_class_fields_keep_visibility_and_definition_evidence(tmp_path):
    graph = observed_graph(
        _observation(tmp_path, "class Data:\n limit = 10\n _cache = {}\n __token = None\n")
    )
    fields = {
        e.qualified_name.rsplit(".", 1)[-1]: e for e in graph.entities if e.kind == "attribute"
    }
    assert set(fields) == {"limit", "_cache", "__token"}
    assert fields["limit"].visibility.kind == "public"
    assert fields["_cache"].visibility.kind == "private"
    assert fields["__token"].visibility.kind == "private"
    assert all(e.annotation is None and e.evidence_ids for e in fields.values())
    assert all(e.modifiers == ("static",) for e in fields.values())
    assert parse_graph(decode_json(graph_bytes(graph))) == graph
    assert [c.status for c in _coverage(graph, "sample.model.Data", "attribute")] == ["partial"]
    assert "FAIL" in {a.status for a in compare_graphs(graph, _target()).assessments}


def test_chained_and_destructured_class_fields_keep_distinct_sites(tmp_path):
    graph = observed_graph(
        _observation(
            tmp_path,
            "class Data:\n first = second = 1\n left, (middle, right) = (1, (2, 3))\n first = 2\n",
        )
    )
    fields = [e for e in graph.entities if e.kind == "attribute"]
    assert sorted(e.qualified_name.rsplit(".", 1)[-1] for e in fields) == [
        "first",
        "first",
        "left",
        "middle",
        "right",
        "second",
    ]
    assert len({e.id for e in fields}) == 6
    assert (
        len({e.evidence_ids for e in fields if e.qualified_name.rsplit(".", 1)[-1] == "first"}) == 2
    )


def test_external_attribute_writes_do_not_become_members_of_the_writer(tmp_path):
    graph = observed_graph(
        _observation(tmp_path, "class Other: pass\nclass Data:\n Other.value = 1\n")
    )
    assert not any(e.kind == "attribute" for e in graph.entities)
