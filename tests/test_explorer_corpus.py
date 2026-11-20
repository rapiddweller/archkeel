# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The corpus harness preserves incomplete topology and refuses invented checks."""

import json
import subprocess
from pathlib import Path

from tools.explorer_corpus import check_import, failed, run


def test_incomplete_topology_does_not_prove_absence(tmp_path: Path) -> None:
    (tmp_path / "archkeel.toml").touch()
    cli = tmp_path / "archkeel"
    cli.write_text(
        "#!/bin/sh\nprintf '%s' "
        '\'{"status":"UNKNOWN","frame":{"topology":{"complete":false,'
        '"truncated":true,"total":{"edges":1},"gaps":[]}}}\'\nexit 2\n'
    )
    cli.chmod(0o755)
    result = run("sample", tmp_path, None, tmp_path, cli)
    assert result["status"] == "UNKNOWN"
    assert result["exit"] == 2
    assert result["topology"]["complete"] is False
    assert result["checks"]["error"] == "no source oracle"
    assert json.loads((tmp_path / "sample.json").read_text())["status"] == "UNKNOWN"


def test_positive_import_requires_source_and_edge(tmp_path: Path) -> None:
    file = tmp_path / "datamimic_ce/authoring/__init__.py"
    file.parent.mkdir(parents=True)
    file.write_text("from datamimic_ce.authoring.application.app import AuthoringApplication\n")
    topology = {
        "edges": [
            {
                "source": "datamimic_ce.authoring",
                "target": "datamimic_ce.authoring.application.app",
                "evidence": [{"path": "datamimic_ce/authoring/__init__.py", "line": 1}],
            }
        ]
    }
    assert check_import("ce", tmp_path, topology)["positive_import"] == "observed"
    assert check_import("ce", tmp_path, topology)["negative_import"] == "UNKNOWN"
    topology["edges"].append(
        {
            "source": "datamimic_ce.authoring",
            "target": "wrong",
            "evidence": [{"path": "datamimic_ce/authoring/__init__.py", "line": 1}],
        }
    )
    assert check_import("ce", tmp_path, topology)["negative_import"] == "wrong edge observed"
    file.write_text("")
    assert check_import("ce", tmp_path, topology)["positive_import"] == "source changed"


def test_missing_config_uses_the_original_repository(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    def launch(cli, target, config, *, probe):
        assert target == root and config is None
        return {"checks": probe(tmp_path / "unused"), "stable_snapshot": True}

    monkeypatch.setattr("tools.explorer_corpus.measure", launch)
    result = run("sample", root, None, tmp_path, tmp_path / "cli")
    assert result["mode"] == "observed"
    assert result["checks"] == {"error": "no source oracle"}
    assert not (root / "archkeel.toml").exists()


def test_observed_import_follows_the_public_cursor(tmp_path: Path, monkeypatch) -> None:
    from tools.explorer_corpus import ORACLES, _observed_import

    name, statement, source, target = ORACLES["platform"]
    file = tmp_path / name
    file.parent.mkdir(parents=True)
    file.write_text(statement + "\n")
    edge = {"source": source, "target": target, "evidence": [{"path": name, "line": 1}]}
    pages = {"": ([], "next"), "next": ([edge], None)}

    def query(snapshot, root, operation, args):
        assert operation == "relations" and args["element"] == source
        items, following = pages[args["cursor"]]
        return {"items": items, "next_cursor": following}

    monkeypatch.setattr("tools.explorer_corpus.query", query)
    assert _observed_import("platform", tmp_path, tmp_path / "db")["positive_import"] == "observed"


def test_missing_wrong_or_refused_probe_fails() -> None:
    assert failed({"checks": {"positive_import": "missing", "wrong_targets": []}})
    assert failed({"checks": {"positive_import": "observed", "wrong_targets": ["wrong"]}})
    assert failed({"refusal": {"kind": "collection_refused"}})
    assert not failed(
        {
            "checks": {"positive_import": "observed", "wrong_targets": []},
            "launch": {"stable_snapshot": True},
        }
    )


def test_cluster_check_compares_sql_with_api(tmp_path: Path, monkeypatch) -> None:
    import io
    import sqlite3

    from tools.explorer_launch import check_clusters

    snapshot = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(snapshot) as db:
        db.execute("CREATE TABLE analysis(root TEXT,coverage TEXT)")
        db.execute(
            "INSERT INTO analysis VALUES (?,?)", ("root", '{"parts":[{"language":"python"}]}')
        )
        db.execute("CREATE TABLE element(id TEXT,kind TEXT,parent TEXT,body TEXT)")
        db.execute(
            "INSERT INTO element VALUES (?,?,?,?)", ("class", "class", "module", '{"source":"a"}')
        )
        db.execute(
            "INSERT INTO element VALUES (?,?,?,?)",
            ("method", "method", "class", '{"source":"b","language":"python"}'),
        )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(
            b'{"items":[{"id":"method","parent":"class","kind":"method"}],"next_cursor":null}'
        ),
    )
    assert check_clusters(snapshot, "http://localhost/") == {"python": "PASS"}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(b'{"items":[],"next_cursor":null}'),
    )
    assert check_clusters(snapshot, "http://localhost/") == {
        "python": "FAIL: SQL member absent from API"
    }
