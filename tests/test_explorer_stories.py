# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Saved story text is separate from verified snapshot evidence."""

import hashlib
import json
from pathlib import Path

import pytest

from archkeel.explorer_store import SnapshotIdentity, publish_snapshot
from archkeel.explorer_stories import list_stories, read_story, save_story


def snapshot(root: Path, target: Path) -> None:
    source = root / "app.py"
    source.write_text("def a():\n    b()\ndef b():\n    pass\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def populate(db):
        db.execute("CREATE TABLE analysis(root TEXT, coverage TEXT)")
        db.execute("INSERT INTO analysis VALUES (?,?)", (str(root), '{"complete":false}'))
        db.execute("CREATE TABLE element(id TEXT,name TEXT,kind TEXT,parent TEXT,body TEXT)")
        db.execute("CREATE TABLE relation(id TEXT,source TEXT,target TEXT,kind TEXT,body TEXT)")
        db.execute("CREATE TABLE location(id TEXT,path TEXT,line INTEGER,digest TEXT)")
        db.execute(
            "INSERT INTO element VALUES (?,?,?,?,?)",
            ("component", "Service", "component", "system", "{}"),
        )
        db.execute(
            "INSERT INTO element VALUES (?,?,?,?,?)", ("app", "app", "module", "component", "{}")
        )
        for key, line in [("a", 1), ("b", 3), ("call", 2)]:
            db.execute("INSERT INTO location VALUES (?,?,?,?)", (key, "app.py", line, digest))
        for key in ("a", "b"):
            db.execute(
                "INSERT INTO element VALUES (?,?,?,?,?)",
                (
                    key,
                    "app." + key,
                    "function",
                    "app",
                    json.dumps({"source": key, "module": "app"}),
                ),
            )
        body = {"resolution": "resolved", "evidence": [{"reference": "call"}]}
        db.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)", ("call", "a", "b", "call", json.dumps(body))
        )

    publish_snapshot(
        target, SnapshotIdentity("revision", "contract", "source"), populate, "UNKNOWN"
    )


def spec() -> dict:
    return {
        "schema_version": "1.2.0",
        "title": "Story",
        "snapshot": {"source_digest": "source", "contract_digest": "contract"},
        "nodes": ["app.a", "app.b"],
        "story": {"id": "example", "title": "Story"},
        "steps": [{"node": "app.a", "note": "author claim"}, {"node": "app.b"}],
    }


def test_checked_story_revalidates_sources_and_never_overwrites(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    result = save_story(tmp_path, db, spec())
    assert [item["status"] for item in result["steps"]] == ["proven", "proven"]
    assert result["steps"][1]["evidence"][0]["line"] == 2
    assert result["steps"][0]["lane"] == "app"
    assert result["steps"][0]["function"] == "a"
    assert list_stories(tmp_path, db)[0]["id"] == "example"
    with pytest.raises(FileExistsError):
        save_story(tmp_path, db, spec())
    (tmp_path / "app.py").write_text("changed\n")
    assert [item["status"] for item in read_story(tmp_path, db, "example")["steps"]] == [
        "unknown",
        "unknown",
    ]


def test_story_rejects_foreign_snapshot_and_unsafe_paths(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    body = spec()
    body["snapshot"]["source_digest"] = "other"
    with pytest.raises(ValueError, match="snapshot does not match"):
        save_story(tmp_path, db, body)
    with pytest.raises(ValueError, match="invalid story id"):
        read_story(tmp_path, db, "../escape")
    (tmp_path / ".archkeel").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a link"):
        save_story(tmp_path, db, spec())


def test_rejects_forged_fields_and_does_not_prove_unresolved_calls(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    body = spec()
    body["steps"][1]["status"] = "proven"
    with pytest.raises(ValueError, match="invalid story fields"):
        save_story(tmp_path, db, body)
    body = spec()
    body["steps"][1]["node"] = "app.missing"
    body["nodes"].append("app.missing")
    result = save_story(tmp_path, db, body)
    assert [step["status"] for step in result["steps"]] == ["proven", "unknown"]
    assert result["steps"][0]["text_status"] == "claim"


def test_snapshot_rebind_checks_again_without_rewriting_spec(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    body = spec()
    save_story(tmp_path, db, body)
    path = tmp_path / ".archkeel/stories/example.story.json"
    saved = path.read_bytes()
    edited = json.loads(saved)
    edited["snapshot"]["source_digest"] = "older"
    path.write_text(json.dumps(edited))
    before = path.read_bytes()
    result = read_story(tmp_path, db, "example")
    assert result["rebound"] is True
    assert [step["status"] for step in result["steps"]] == ["proven", "proven"]
    assert path.read_bytes() == before


def test_rejects_story_link(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    folder = tmp_path / ".archkeel/stories"
    folder.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(spec()))
    (folder / "example.story.json").symlink_to(outside)
    with pytest.raises(ValueError, match="not found"):
        read_story(tmp_path, db, "example")


def test_path_fallback_rechecks_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    monkeypatch.setattr(os, "supports_dir_fd", set())
    assert save_story(tmp_path, db, spec())["id"] == "example"
    assert read_story(tmp_path, db, "example")["id"] == "example"
    with pytest.raises(FileExistsError):
        save_story(tmp_path, db, spec())


def test_path_fallback_refuses_a_linked_story_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / ".archkeel").symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(ValueError, match="link or junction"):
        save_story(tmp_path, db, spec())


def test_older_story_without_steps_and_unchecked_kind_remains_unknown(tmp_path: Path) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    body = spec()
    body["steps"][1]["kind"] = "imports"
    result = save_story(tmp_path, db, body)
    assert result["steps"][1]["status"] == "unknown"
    assert "not checked" in result["steps"][1]["reason"]
    body["story"]["id"] = "empty"
    del body["steps"]
    assert save_story(tmp_path, db, body)["steps"] == []


def test_saved_story_conforms_to_view_schema(tmp_path: Path) -> None:
    import jsonschema

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    save_story(tmp_path, db, spec())
    saved = json.loads((tmp_path / ".archkeel/stories/example.story.json").read_text())
    schema = json.loads((Path(__file__).parents[1] / "schema/view-spec.schema.json").read_text())
    jsonschema.validate(saved, schema)


def test_list_does_not_recheck_source_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    save_story(tmp_path, db, spec())

    def no_recheck(*args: object) -> None:
        raise AssertionError("list must not read evidence")

    monkeypatch.setattr("archkeel.explorer_stories._location", no_recheck)
    assert list_stories(tmp_path, db) == [{"id": "example", "title": "Story", "steps": 2}]


def test_external_systems_need_current_external_import_evidence(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    with sqlite3.connect(db) as connection:
        for target, resolution in (("sqlite3", "external"), ("redis", "local")):
            body = {"target": target, "resolution": resolution, "evidence": [{"reference": "a"}]}
            connection.execute(
                "INSERT INTO relation VALUES (?,?,?,?,?)",
                ("import-" + target, "app", target, "import", json.dumps(body)),
            )
        body = {
            "expression": "sqlite3.connect",
            "resolution": "external",
            "evidence": [{"reference": "call"}],
        }
        connection.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)",
            ("external-call", "a", None, "call", json.dumps(body)),
        )
    result = save_story(tmp_path, db, spec())
    external = result["steps"][0]["external"]
    assert len(external) == 1
    assert external[0]["label"] == "SQLite" and external[0]["status"] == "observed_call"
    assert external[0]["evidence"][0]["line"] == 2
    (tmp_path / "app.py").write_text("changed\n")
    assert read_story(tmp_path, db, "example")["steps"][0]["external"] == []


def test_external_import_without_call_does_not_prove_use(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    with sqlite3.connect(db) as connection:
        body = {"target": "sqlite3", "resolution": "external", "evidence": [{"reference": "a"}]}
        connection.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)",
            ("i", "app", "sqlite3", "import", json.dumps(body)),
        )
    assert save_story(tmp_path, db, spec())["steps"][0]["external"] == []


def test_external_call_with_unresolved_binding_stays_unknown(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    with sqlite3.connect(db) as connection:
        source = {"target": "sqlite3", "resolution": "external", "evidence": [{"reference": "a"}]}
        call = {
            "expression": "sqlite3.connect",
            "resolution": "unresolved",
            "evidence": [{"reference": "call"}],
        }
        other = {
            "expression": "sqlite3.Error",
            "resolution": "unresolved",
            "evidence": [{"reference": "call"}],
        }
        for id, src, target, kind, body in (
            ("i", "app", "sqlite3", "import", source),
            ("c", "a", None, "call", call),
            ("e", "a", None, "call", other),
        ):
            connection.execute(
                "INSERT INTO relation VALUES (?,?,?,?,?)", (id, src, target, kind, json.dumps(body))
            )
    rows = save_story(tmp_path, db, spec())["steps"][0]["external"]
    assert len(rows) == 1 and rows[0]["status"] == "observed_call"
    assert rows[0]["binding"] == "unknown"
    assert "binding is unresolved" in rows[0]["reason"]


def test_external_hint_excludes_known_local_shadow(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "snapshot.sqlite3"
    snapshot(tmp_path, db)
    with sqlite3.connect(db) as connection:
        source = {"target": "sqlite3", "resolution": "external", "evidence": [{"reference": "a"}]}
        call = {
            "target": "b",
            "expression": "sqlite3.connect",
            "resolution": "resolved",
            "evidence": [{"reference": "call"}],
        }
        connection.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)",
            ("i", "app", "sqlite3", "import", json.dumps(source)),
        )
        connection.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)",
            ("shadow", "a", "b", "call", json.dumps(call)),
        )
    assert save_story(tmp_path, db, spec())["steps"][0]["external"] == []
