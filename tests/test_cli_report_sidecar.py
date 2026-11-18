# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The companion file keeps the gap records of the displayed run."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from archkeel.cli import core_arguments, core_delivery


def test_html_sidecar_keeps_every_gap_and_binds_its_bytes(tmp_path: Path) -> None:
    target = tmp_path / "report.html"
    options = core_arguments.parse(["report", "--output", str(target)])
    gaps = [
        {
            "kind": "collection_gap",
            "reason": "schemars::X",
            "subjects": [f"m{i}"],
            "evidence": ["E1"],
            "extra": 18446744073709551615,
        }
        for i in range(420)
    ]
    document = {
        "collection_gaps": gaps,
        "locations": {"E1": {"path": "x.rs", "line": 2}},
        "engine": "core",
        "status": "UNKNOWN",
        "contract_digest": "abc",
    }
    frame = SimpleNamespace(
        html='<section id="gap-records-file">Gap records file unavailable.</section>'
    )
    core_delivery._write_report(options, frame, b"", document)
    page = target.read_text()
    assert "420 gap records" in page
    assert "If the file is missing, the link cannot open it" in page
    files = list(tmp_path.glob("archkeel-gaps-*.json"))
    assert len(files) == 1
    content = files[0].read_bytes()
    assert hashlib.sha256(content).hexdigest() in page
    assert files[0].name in page
    result = json.loads(content)
    assert result["collection_gaps"] == gaps
    assert len({subject for gap in result["collection_gaps"] for subject in gap["subjects"]}) == 420
    assert result["locations"] == document["locations"]
    core_delivery._write_report(options, frame, b"", document)
    assert len(list(tmp_path.glob("archkeel-gaps-*.json"))) == 1
    files[0].write_bytes(b"changed")
    with pytest.raises(OSError, match="different digest"):
        core_delivery._write_report(options, frame, b"", document)
    assert files[0].read_bytes() == b"changed"


def test_html_sidecar_is_not_written_for_an_unsafe_target(tmp_path: Path) -> None:
    target = tmp_path / "report.html"
    target.symlink_to(tmp_path / "other.html")
    options = core_arguments.parse(["report", "--output", str(target)])
    frame = SimpleNamespace(
        html='<section id="gap-records-file">Gap records file unavailable.</section>'
    )
    with pytest.raises(OSError):
        core_delivery._write_report(options, frame, b"", {"collection_gaps": []})
    assert not list(tmp_path.glob("archkeel-gaps-*.json"))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_existing_fifo_sidecar_is_refused_without_waiting(tmp_path: Path) -> None:
    document = {"collection_gaps": []}
    content = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    fifo = tmp_path / f"archkeel-gaps-{digest}.json"
    os.mkfifo(fifo)
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from pathlib import Path; from archkeel.cli.core_output import write_output; "
        "write_output(Path(sys.argv[2]), b'', "
        "companion=(Path(sys.argv[3]), b'{\"collection_gaps\":[]}'))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(Path(__file__).resolve().parents[1] / "src"),
            str(tmp_path / "report.html"),
            str(fifo),
        ],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    assert result.returncode != 0
    assert "not a regular file" in result.stderr


def test_json_output_and_stdout_do_not_create_a_sidecar(tmp_path: Path) -> None:
    document = {"collection_gaps": [{"reason": "saved"}]}
    frame = SimpleNamespace(html=None)
    options = core_arguments.parse(
        ["report", "--output", str(tmp_path / "report.json"), "--format", "json"]
    )
    core_delivery._write_report(options, frame, b'{"saved":true}', document)
    assert (tmp_path / "report.json").read_bytes() == b'{"saved":true}'
    options = core_arguments.parse(["report"])
    core_delivery._write_report(options, frame, b"", document)
    assert not list(tmp_path.glob("archkeel-gaps-*.json"))
