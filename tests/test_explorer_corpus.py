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


def test_missing_config_is_drafted_only_in_copy(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "sample.py").write_text("pass\n")
    cli = tmp_path / "archkeel"
    cli.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = init ]; then touch archkeel.toml; exit 0; fi\n'
        'printf \'%s\' \'{"status":"UNKNOWN","frame":{}}\'\n'
    )
    cli.chmod(0o755)
    result = run("sample", root, None, tmp_path, cli)
    assert result["disposable_copy"] is True
    assert not (root / "archkeel.toml").exists()


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
