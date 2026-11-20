# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate a saved story against the checked view specification."""

import re
from typing import Any

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_SYSTEMS = {"redis", "relational_database", "mongodb", "object_storage", "kafka", "rabbitmq"}
_DIRECTIONS = {"reads", "writes", "reads_writes", "touches"}
_KINDS = {
    "imports",
    "calls",
    "references",
    "inherits",
    "realizes",
    "mixes_in",
    "creates",
    "instance_of",
    "owns",
    "requires",
    "publishes",
}


def _object(value: object, required: set[str], optional: set[str]) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - optional
    ):
        raise ValueError("invalid story fields")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("invalid story text")
    return value


def _steps(steps: list[Any], nodes: list[Any], ids: list[str]) -> None:
    for index, raw in enumerate(steps):
        step = _object(
            raw,
            {"node"},
            {"note", "kind", "claim", "chapter", "title", "question", "external", "transition"},
        )
        if _text(step["node"]) not in nodes:
            raise ValueError("step node is not declared")
        for field in ("note", "title", "question", "chapter"):
            if step.get(field) is not None:
                _text(step[field])
        if (
            ids
            and step.get("chapter") not in ids
            or step.get("chapter") is not None
            and step["chapter"] not in ids
        ):
            raise ValueError("unknown chapter")
        kind = step.get("kind")
        if (kind is not None and (not isinstance(kind, str) or kind not in _KINDS)) or type(
            step.get("claim", False)
        ) is not bool:
            raise ValueError("invalid story relationship")
        if index == 0 and (step.get("kind") is not None or step.get("claim", False)):
            raise ValueError("first step has no relationship")
        if step.get("transition", "call") not in (
            "call",
            "return",
            "process_request",
            "process_response",
        ):
            raise ValueError("invalid story transition")
        if index == 0 and step.get("transition", "call") != "call":
            raise ValueError("first step has no transition")
        external = step.get("external", [])
        if not isinstance(external, list):
            raise ValueError("invalid external systems")
        for raw_external in external:
            item = _object(raw_external, {"system", "direction"}, set())
            if (
                not isinstance(item["system"], str)
                or not isinstance(item["direction"], str)
                or item["system"] not in _SYSTEMS
                or item["direction"] not in _DIRECTIONS
            ):
                raise ValueError("invalid external system")


def _metadata(spec: dict[str, Any]) -> None:
    for field in ("created", "git_head", "agent"):
        if spec.get(field) is not None:
            _text(spec[field])
    if spec.get("author_kind") is not None and spec["author_kind"] not in ("agent", "human"):
        raise ValueError("invalid author kind")
    notes = spec.get("notes", [])
    if not isinstance(notes, list):
        raise ValueError("invalid notes")
    for note in notes:
        _text(note)


def _validate(value: object) -> dict[str, Any]:
    spec = _object(
        value,
        {"schema_version", "title", "snapshot", "nodes", "story"},
        {"steps", "edges", "notes", "stops", "created", "git_head", "author_kind", "agent"},
    )
    if spec["schema_version"] != "1.2.0":
        raise ValueError("story needs view spec 1.2.0")
    _text(spec["title"])
    snap = _object(spec["snapshot"], {"source_digest", "contract_digest"}, set())
    _text(snap["source_digest"])
    _text(snap["contract_digest"])
    story = _object(spec["story"], {"id", "title"}, {"chapters"})
    if not isinstance(story["id"], str) or not _ID.fullmatch(story["id"]):
        raise ValueError("invalid story id")
    _text(story["title"])
    chapters = story.get("chapters", [])
    if not isinstance(chapters, list) or len(chapters) > 1000:
        raise ValueError("invalid chapters")
    ids = []
    for chapter in chapters:
        part = _object(chapter, {"id", "title"}, set())
        ids.append(_text(part["id"]))
        _text(part["title"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chapter")
    nodes = spec["nodes"]
    steps = spec.get("steps", [])
    if (
        not isinstance(nodes, list)
        or not isinstance(steps, list)
        or len(nodes) > 1000
        or len(steps) > 1000
    ):
        raise ValueError("invalid story nodes or steps")
    for node in nodes:
        _text(node)
    if len(set(nodes)) != len(nodes):
        raise ValueError("duplicate story node")
    _metadata(spec)
    edges = spec.get("edges", [])
    stops = spec.get("stops", [])
    if not isinstance(edges, list) or not isinstance(stops, list):
        raise ValueError("invalid edges or stops")
    for raw in edges:
        edge = _object(raw, {"source", "target"}, {"kind", "claim", "note"})
        if edge["source"] not in nodes or edge["target"] not in nodes:
            raise ValueError("edge node is not declared")
        if edge.get("kind") is not None and (
            not isinstance(edge["kind"], str) or edge["kind"] not in _KINDS
        ):
            raise ValueError("invalid edge kind")
        if type(edge.get("claim", False)) is not bool:
            raise ValueError("invalid edge claim")
        if edge.get("note") is not None:
            _text(edge["note"])
    for raw in stops:
        stop = _object(raw, {"node"}, {"title", "note"})
        if stop["node"] not in nodes:
            raise ValueError("stop node is not declared")
        for field in ("title", "note"):
            if stop.get(field) is not None:
                _text(stop[field])
    _steps(steps, nodes, ids)
    return spec
