# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Indexed views of the topology emitted by the core."""

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from .explorer_boundaries import boundary_rows
from .explorer_hierarchy import _element_status
from .explorer_map import _aggregate_relations, _call_scope, _map_search, _map_view, _open_targets
from .explorer_source import (
    _call_resolution,
    _number,
    _relation_evidence,
    _source,
    _source_path,
    _text,
)
from .explorer_store import open_snapshot
from .explorer_symbols import _symbol_rows
from .explorer_verdict import _ANSWERS, VerdictRows, _store

_SCHEMA = (
    "CREATE TABLE element(id TEXT PRIMARY KEY,name TEXT,kind TEXT,parent TEXT,body TEXT)",
    "CREATE INDEX children_order ON element(parent,id)",
    "CREATE TABLE relation(id TEXT PRIMARY KEY,source TEXT,target TEXT,kind TEXT,body TEXT)",
    "CREATE INDEX outbound ON relation(source,id)",
    "CREATE INDEX inbound ON relation(target,id)",
    "CREATE TABLE location(id TEXT PRIMARY KEY,path TEXT,line INTEGER,digest TEXT)",
    "CREATE TABLE analysis(root TEXT,coverage TEXT)",
)


Row = dict[str, object]
_AddElement = Callable[[str, str, str, str, Row], None]
_Reference = Callable[[str, int], str]


def _key(domain: str, value: str) -> str:
    return f"{domain}:{value}"


def _endpoint(domain: str, value: object) -> str | None:
    return _key(domain, value) if isinstance(value, str) and value else None


def _object(value: object) -> Row:
    if not isinstance(value, dict):
        raise ValueError("expected an Explorer record")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _records(value: object) -> Iterator[Row]:
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError("expected an Explorer record list")
    for row in value:
        yield _object(row)


def _strings(row: Row, field: str) -> list[str]:
    value = row[field]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid {field}")
    return list(value)


def _fact_locations(record: Row, locations: Row) -> list[Row]:
    return [_object(locations[key]) for key in _strings(record, "evidence_ids") if key in locations]


def _rows(topology: Row, section: str) -> Iterator[Row]:
    for part in _records(topology.get("explorer")):
        yield from _records(part.get(section))


def _calls(
    part: Row,
    locations: Row,
    symbols: dict[str, list[str]],
    declarations: dict[str, list[Row]],
) -> Iterator[Row]:
    for data in _records(part.get("calls")):
        targets = _strings(data, "targets")
        candidates = [symbol for name in targets for symbol in symbols.get(name, [])]
        origin = _endpoint("definition", data.get("source_definition_id")) or _key(
            "module", _text(data, "source_module")
        )
        target = _endpoint("definition", data.get("target_definition_id"))
        if target is None and len(candidates) == 1 and len(targets) == 1:
            target = candidates[0]
        exact = (
            target is not None
            and data["status"] == "resolved"
            and data.get("candidate_count", len(targets)) == 1
            and not data["candidates_truncated"]
            and data.get("evidence_class", "FACT") == "FACT"
        )
        evidence = _fact_locations(data, locations)
        if exact and isinstance(target, str):
            evidence = [dict(loc, role="call_site") for loc in evidence]
            evidence.extend(dict(loc, role="declaration") for loc in declarations.get(target, []))
        yield {
            "id": data["id"],
            "source": origin,
            "target": target if exact else None,
            "kind": "call",
            "expression": data["expression"],
            "reason": data.get("reason"),
            "candidates": candidates,
            "resolution": "resolved" if exact else "unresolved",
            "evidence": evidence,
        }


def _source_calls(topology: Row) -> Iterator[Row]:
    locations = _object(topology.get("locations", {}))
    for part in _records(topology.get("explorer")):
        for row in _records(part.get("source_call_candidates")):
            site = _text(row, "call_evidence")
            declaration = _text(row, "declaration_evidence")
            yield {
                "id": json.dumps(["source_call", part.get("part"), site, declaration]),
                "source": _text(row, "source_module"),
                "target": _text(row, "target_module"),
                "expression": _text(row, "expression"),
                "declaration": _text(row, "target"),
                "resolution": "candidate",
                "evidence": [
                    dict(_object(locations.get(key)), role=role)
                    for key, role in ((site, "call_site"), (declaration, "declaration"))
                ],
            }


def _imports(topology: Row) -> Iterator[Row]:
    locations = _object(topology.get("locations", {}))
    for row in _rows(topology, "imports"):
        yield dict(
            row,
            source=row["source_module"],
            target=row.get("target_module"),
            evidence=_fact_locations(row, locations),
        )


def _part_coverage(part: Row) -> Row:
    files = [(_text(row, "module"), _text(row, "path")) for row in _records(part.get("files"))]
    facts: dict[str, int | None] = {}
    summary: Row = {
        "part": part.get("part"),
        "language": part.get("language"),
        "facts": facts,
        "files_indexed": None if part.get("files") is None else len({path for _, path in files}),
    }
    for kind, module_key in (("symbols", "module"), ("calls", "source_module"), ("imports", "")):
        rows = list(_records(part.get(kind)))
        facts[kind] = None if part.get(kind) is None else len(rows)
        if module_key:
            modules = {name for row in rows if isinstance(name := row.get(module_key), str)}
            summary["files_with_" + kind] = (
                None
                if facts[kind] is None or part.get("files") is None
                else len({path for module, path in files if module in modules})
            )
    return summary


def _coverage(connection: sqlite3.Connection, topology: Row, root: Path) -> None:
    coverage = {
        k: topology.get(k)
        for k in ("complete", "truncated", "total", "gaps", "verdict", "observed_only")
    }
    coverage["parts"] = [_part_coverage(part) for part in _records(topology.get("explorer"))]
    packages = {
        _text(row, "target_module")
        for row in _rows(topology, "imports")
        if (row.get("resolution"), row.get("evidence_class")) == ("external", "FACT")
        and not row.get("inferred_receiver")
        and row.get("target_module")
    }
    coverage["external_imports"] = {"packages": sorted(packages)[:12], "total": len(packages)}
    metadata = (str(root.resolve()), json.dumps(coverage))
    connection.execute("INSERT INTO analysis VALUES (?,?)", metadata)


def _elements(topology: Row, element: _AddElement, reference: _Reference) -> None:
    languages = {
        "PART:" + _text(part, "part"): part.get("language")
        for part in _records(topology.get("explorer"))
        if part.get("part")
    }
    for row in _records(topology["components"]):
        key = _text(row, "id")
        element(
            _key("component", key),
            _text(row, "name"),
            "component",
            _endpoint("component", row["parent"]) or "system",
            dict(
                row,
                language=languages.get(key, row.get("language")),
                system_part=key.startswith("PART:"),
            ),
        )
    for row in _records(topology["modules"]):
        owner = _endpoint("component", row["component"])
        element(
            _key("module", _text(row, "name")),
            _text(row, "name"),
            "module",
            owner or "system",
            dict(row, component=owner, source=reference(_text(row, "path"), 1)),
        )
    modules = {_text(row, "name") for row in _records(topology["modules"])}
    for part in _records(topology.get("explorer")):
        for file in _records(part.get("files")):
            module = _text(file, "module")
            if module not in modules:
                element(
                    _key("module", module),
                    module,
                    "module",
                    "system",
                    {
                        "path": file["path"],
                        "source": reference(_text(file, "path"), 1),
                        "language": part.get("language"),
                        "ownership": "unknown",
                    },
                )
                modules.add(module)


def _symbols(topology: Row, element: _AddElement, reference: _Reference) -> list[Iterator[Row]]:
    calls: list[Iterator[Row]] = []
    locations = _object(topology.get("locations", {}))
    for part in _records(topology.get("explorer")):
        symbols: dict[str, list[str]] = defaultdict(list)
        declarations: dict[str, list[Row]] = {}
        for row in _symbol_rows(list(_records(part.get("symbols")))):
            name = row.get("qualified_name")
            if not isinstance(name, str) or not row.get("module"):
                continue
            key = _key("definition", _text(row, "id"))
            symbols[name].append(key)
            refs = _fact_locations(row, locations)
            declarations[key] = refs
            anchor = (
                reference(_text(refs[0], "path"), _number(refs[0], "line", 1, 2**31 - 1))
                if refs
                else None
            )
            element(
                key,
                name,
                _text(row, "kind"),
                _key(_text(row, "parent_domain"), _text(row, "parent")),
                _object(row["body"]) | {"source": anchor, "language": part.get("language")},
            )
        calls.append(_calls(part, locations, symbols, declarations))
    return calls


def populate(
    connection: sqlite3.Connection, topology: Row, root: Path, verdict: VerdictRows | None = None
) -> None:
    """Project the same scan as the report and retain its coverage and truncation."""
    if topology.get("version") != 1:
        raise ValueError("unsupported topology version")
    for statement in _SCHEMA:
        connection.execute(statement)
    _store(connection, verdict)
    _coverage(connection, topology, root)
    digests: dict[str, str | None] = {}

    def reference(name: str, line: int) -> str:
        if name not in digests:
            try:
                with _source_path(root, name).open("rb") as stream:
                    digests[name] = hashlib.file_digest(stream, "sha256").hexdigest()
            except (OSError, ValueError):
                digests[name] = None
        key = hashlib.sha256(json.dumps([name, line]).encode()).hexdigest()
        connection.execute(
            "INSERT OR IGNORE INTO location VALUES (?,?,?,?)", (key, name, line, digests[name])
        )
        return key

    def element(key: str, name: str, kind: str, parent: str, row: Row) -> None:
        body = dict(row, id=key, name=name, kind=kind, parent=parent)
        connection.execute(
            "INSERT INTO element VALUES (?,?,?,?,?)", (key, name, kind, parent, json.dumps(body))
        )

    _elements(topology, element, reference)
    _relations(connection, topology, root, _symbols(topology, element, reference), reference)


def _relations(
    connection: sqlite3.Connection,
    topology: Row,
    root: Path,
    calls: list[Iterator[Row]],
    reference: _Reference,
) -> None:
    interfaces = (
        dict(row, source="PART:" + _text(row, "source"), target="PART:" + _text(row, "target"))
        for row in _records(topology.get("interfaces"))
    )
    sections: tuple[tuple[str, str, str | None, Iterable[Row]], ...] = (
        ("call", "call", None, (row for group in calls for row in group)),
        ("source_call", "source_call", "module", _source_calls(topology)),
        ("import_site", "import_site", "module", _imports(topology)),
        (
            "boundary",
            "boundary",
            "module",
            boundary_rows(root, list(_records(topology["modules"]))),
        ),
        ("interface", "interface", "component", interfaces),
        ("module_import", "import", "module", _records(topology["edges"])),
        ("component_import", "import", "component", _records(topology.get("component_edges"))),
        ("requires", "requires", "component", _records(topology.get("requires"))),
    )
    for section, kind, domain, rows in sections:
        for row in rows:
            relation_kind = row["kind"] if kind == "boundary" else kind
            if kind == "import_site" and row.get("inferred_receiver"):
                relation_kind = "inferred_receiver"
            source, target = row["source"], row["target"]
            source_name, target_name = source, target
            if domain is not None:
                source = _endpoint(domain, source)
                if kind in {"import", "import_site"} and row.get("resolution") in {
                    "external",
                    "builtin",
                    "unresolved",
                }:
                    target = _endpoint("open_module", target)
                else:
                    target = _endpoint(domain, target)
            identity = row.get("id") or json.dumps([source, target])
            key = _key("relation:" + section, str(identity))
            refs = [
                dict(
                    loc, reference=reference(_text(loc, "path"), _number(loc, "line", 1, 2**31 - 1))
                )
                for loc in _records(row.get("evidence"))
            ]
            body = dict(
                row,
                id=key,
                kind=relation_kind,
                source=source,
                target=target,
                evidence=refs,
                resolution=row.get("resolution", "declared"),
            )
            if domain is not None:
                body.update(source_name=source_name, target_name=target_name)
            if kind == "call":
                for end in ("source", "target"):
                    label = connection.execute(
                        "SELECT name,parent FROM element WHERE id=?", (body[end],)
                    ).fetchone()
                    if label:
                        body[end + "_name"], body[end + "_owner"] = label
            connection.execute(
                "INSERT INTO relation VALUES (?,?,?,?,?)",
                (key, source, target, relation_kind, json.dumps(body)),
            )


def _story_step(db: sqlite3.Connection, args: Row) -> Row:
    row = db.execute(
        "SELECT body FROM relation WHERE id=? AND kind='call'", (_text(args, "id"),)
    ).fetchone()
    if not row:
        return {"status": "UNKNOWN", "reason": "No call evidence for this step", "items": []}
    hop = json.loads(row[0])
    return {"status": hop["resolution"], "items": [hop]}


def query(path: Path, root: Path, operation: str, args: Row) -> Row:
    """Serve one bounded operation against an immutable published database."""
    with open_snapshot(path) as db:
        saved_root, coverage = db.execute("SELECT root,coverage FROM analysis").fetchone()
        if Path(saved_root) != root.resolve():
            raise ValueError("snapshot belongs to another repository")
        if operation in _ANSWERS:
            return _ANSWERS[operation](db, root, args, path.stem)
        result = {"snapshot": path.stem, "coverage": json.loads(coverage)}
        if operation == "map":
            return result | _map_view(
                db,
                _text(args, "parent", "system"),
                _text(args, "view", "components"),
                _text(args, "cursor", ""),
                _number(args, "limit", 50, 200),
                _text(args, "focus", ""),
            )
        if operation == "source":
            return result | _source(db, root, args)
        if operation == "evidence":
            return result | _relation_evidence(db, args)
        if operation == "call_resolution":
            return result | _call_resolution(db, args, _call_scope, _element_status)
        if operation == "story":
            return result | _story_step(db, args)
        if operation == "relations" and "aggregate" in args:
            return result | _aggregate_relations(
                db,
                _text(args, "aggregate"),
                _text(args, "cursor", ""),
                _number(args, "limit", 50, 200),
            )
        table = "element"
        if operation in {"overview", "children"}:
            where, params = "parent=?", [_text(args, "parent", "system")]
        elif operation == "search":
            where, params = _map_search(db, _text(args, "text"), _text(args, "parent", ""))
        elif operation == "relations":
            table = "relation"
            direction = _text(args, "direction", "both")
            elem = _text(args, "element")
            result["element_status"] = _element_status(db, elem)
            if args.get("scope") == "unlinked_calls":
                where, params = (
                    _call_scope(db, elem) if result["element_status"] == "known" else ("0", [])
                )
                where = "kind='call' AND target IS NULL AND " + where
            elif direction == "both":
                where, params = "(source=? OR target=?)", [elem, elem]
            elif direction in {"in", "out"}:
                where, params = ("target=?" if direction == "in" else "source=?"), [elem]
            else:
                raise ValueError("invalid direction")
            if "kind" in args:
                where += " AND kind=?"
                params.append(_text(args, "kind"))
        else:
            raise ValueError("unknown operation")
        limit = _number(args, "limit", 50, 200)
        cursor = _text(args, "cursor", "")
        rows = db.execute(
            f"SELECT id,body FROM {table} WHERE {where} AND id>? ORDER BY id LIMIT ?",
            (*params, cursor, limit + 1),
        ).fetchall()
        items = [json.loads(r[1]) for r in rows[:limit]]
        if table == "element":
            _open_targets(db, items)
        return result | {
            "items": items,
            "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
        }
