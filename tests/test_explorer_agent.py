# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The story agent can select only bounded, checked snapshot facts."""

import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

from archkeel import explorer_agent


def test_facts_find_prompt_and_follow_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE analysis(root TEXT)")
    db.execute("INSERT INTO analysis VALUES (?)", (str(tmp_path),))
    db.execute("CREATE TABLE snapshot(source TEXT,contract TEXT,complete INTEGER)")
    db.execute("INSERT INTO snapshot VALUES ('s','c',1)")
    db.execute("CREATE TABLE element(id TEXT,name TEXT,kind TEXT,parent TEXT)")
    db.executemany(
        "INSERT INTO element VALUES (?,?,?,?)",
        [
            ("mod", "demo", "module", "system"),
            ("a", "demo.order", "function", "mod"),
            ("b", "demo.pay", "function", "mod"),
            ("c", "demo.save", "function", "mod"),
        ],
    )
    db.execute("CREATE TABLE relation(id TEXT,source TEXT,target TEXT,kind TEXT,body TEXT)")
    for source, target in (("a", "b"), ("b", "c")):
        body = {
            "id": source,
            "source": source,
            "target": target,
            "expression": target,
            "resolution": "resolved",
            "secret": "must not leave",
        }
        db.execute(
            "INSERT INTO relation VALUES (?,?,?,?,?)",
            (source, source, target, "call", json.dumps(body)),
        )
    monkeypatch.setattr(explorer_agent, "open_snapshot", lambda path: nullcontext(db))
    _, nodes, calls = explorer_agent._facts(tmp_path, tmp_path / "snap", "", "Explain order")
    assert nodes == ["demo.order", "demo.pay", "demo.save"]
    assert [(c["source_name"], c["target_name"]) for c in calls] == [
        ("demo.order", "demo.pay"),
        ("demo.pay", "demo.save"),
    ]
    assert all("secret" not in call for call in calls)
    _, nodes, _ = explorer_agent._facts(tmp_path, tmp_path / "snap", "mod", "ignored")
    assert len(nodes) == 3


def test_candidate_is_validated_before_save(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    identity = {"source_digest": "s", "contract_digest": "c"}
    monkeypatch.setattr(explorer_agent, "_facts", lambda *args: (identity, ["demo.run"], []))
    monkeypatch.setattr(
        explorer_agent,
        "ask_story_model",
        lambda prompt, root: {"title": "Run", "steps": [{"node": "demo.run", "note": "Entry"}]},
    )
    saved = []
    monkeypatch.setattr(
        explorer_agent, "save_story", lambda root, snap, spec: saved.append(spec) or {"id": "saved"}
    )
    confirms = []
    assert explorer_agent._create_story(
        tmp_path, tmp_path / "snap", "Explain run", confirm=lambda: confirms.append(1)
    ) == {"id": "saved"}
    assert confirms == [1] and saved[0]["nodes"] == ["demo.run"]
    monkeypatch.setattr(
        explorer_agent,
        "ask_story_model",
        lambda prompt, root: {"title": "Run", "steps": [{"node": "invented", "note": ""}]},
    )
    with pytest.raises(RuntimeError, match="not in the snapshot"):
        explorer_agent._create_story(tmp_path, tmp_path / "snap", "Explain run")
    assert len(saved) == 1


def test_template_rejects_symlink(tmp_path: Path) -> None:
    (tmp_path / ".archkeel").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="symbolic link"):
        explorer_agent._template(tmp_path)


def test_mcp_registers_story_storage_without_starting_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys
    from types import SimpleNamespace

    from archkeel import explorer_mcp

    snapshot = tmp_path / "snapshot"
    snapshot.touch()
    registered = {}

    class Server:
        def __init__(self, name: str) -> None:
            pass

        def tool(self, operation: object) -> None:
            registered[operation.__name__] = operation

        def run(self, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setitem(sys.modules, "fastmcp", SimpleNamespace(FastMCP=Server))
    monkeypatch.setattr(
        sys, "argv", ["archkeel-mcp", "--snapshot", str(snapshot), "--root", str(tmp_path)]
    )
    monkeypatch.setattr(explorer_mcp, "query", lambda path, root, op, args: args)
    monkeypatch.setattr(explorer_mcp, "list_stories", lambda root, path: [{"id": "one"}])
    monkeypatch.setattr(explorer_mcp, "read_story", lambda root, path, id: {"id": id})
    monkeypatch.setattr(explorer_mcp, "save_story", lambda root, path, spec: {"saved": spec})
    explorer_mcp.main()
    assert registered["stories"]() == [{"id": "one"}]
    assert registered["story_read"]("one") == {"id": "one"}
    assert registered["story_save"]({"title": "T"}) == {"saved": {"title": "T"}}
    assert registered["map"](view="hierarchy")["view"] == "hierarchy"
    assert registered["search"]("display", parent="shell")["parent"] == "shell"
    assert "create_story" not in registered


def test_followup_sends_bounded_context_and_converts_chapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    previous = {
        "title": "Earlier",
        "chapters": [{"id": "one", "title": "Start"}],
        "steps": [{"node": "demo.run", "note": "Entry", "evidence": ["secret"]}],
        "coverage": {"details": "secret"},
    }
    monkeypatch.setattr(explorer_agent, "read_story", lambda *args: previous)
    selections = []
    monkeypatch.setattr(
        explorer_agent,
        "_facts",
        lambda root, snapshot, element, prompt: (
            selections.append(element)
            or ({"source_digest": "s", "contract_digest": "c"}, ["demo.run", "demo.next"], [])
        ),
    )

    def ask(prompt: str, root: Path) -> dict[str, object]:
        assert "secret" not in prompt
        assert "in English" in prompt
        return {
            "title": "Follow",
            "steps": [
                {"node": "demo.run", "note": "Entry", "title": "Start", "chapter": "Setup"},
                {"node": "demo.next", "note": "Next", "title": "Execute", "chapter": "Run"},
            ],
        }

    monkeypatch.setattr(explorer_agent, "ask_story_model", ask)
    monkeypatch.setattr(explorer_agent, "save_story", lambda root, path, spec: spec)
    result = explorer_agent._create_story(
        tmp_path, tmp_path / "snapshot", "Continue", story="earlier"
    )
    assert selections == ["demo.run"]
    assert result["story"]["chapters"] == [
        {"id": "chapter-1", "title": "Setup"},
        {"id": "chapter-2", "title": "Run"},
    ]
    assert result["steps"][1]["title"] == "Execute"


def test_model_refuses_codex_inside_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from archkeel.cli import story_model

    monkeypatch.setattr(story_model.shutil, "which", lambda name: str(tmp_path / "codex"))
    with pytest.raises(RuntimeError, match="outside the analyzed repository"):
        story_model.ask_story_model("prompt", tmp_path)


def test_model_needs_sign_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from archkeel.cli import story_model

    monkeypatch.setattr(story_model.shutil, "which", lambda name: str(tmp_path.parent / "codex"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-auth"))
    with pytest.raises(RuntimeError, match="sign-in"):
        story_model.ask_story_model("prompt", tmp_path)
