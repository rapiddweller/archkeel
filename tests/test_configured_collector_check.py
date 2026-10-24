# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Historical check uses the same configured process port as init and report."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from archkeel import cli
from archkeel.cli import main
from archkeel.cli.config import parse_config
from archkeel.cli.observe import observer_for
from fixtures import demo_catalog_check


@pytest.mark.parametrize("limit", [None, 1, 256 * 1024 * 1024])
@pytest.mark.parametrize("timeout", [None, 600])
def test_check_reobserves_revisions_with_configured_collector(
    tmp_path: Path, monkeypatch, capsys, limit: int | None, timeout: int | None
) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(demo_catalog_check.FIXTURE_DIR, fixture)
    seen = tmp_path / "collector-requests.jsonl"
    collector = (
        "import sys\nfrom pathlib import Path\n"
        "from archkeel.ir.facts_codec import decode_request,encode_response\n"
        "from archkeel.ir.protocol import CollectionResponse\n"
        "from archkeel.analyzer.python.collect import collect\n"
        "request=decode_request(sys.stdin.buffer.read())\n"
        f"with Path({str(seen)!r}).open('a') as stream:\n"
        "    stream.write(request.snapshot.git_head+'\\n')\n"
        "sys.stdout.buffer.write(encode_response(CollectionResponse(collect(request))))\n"
    )
    argv = (sys.executable, "-B", "-c", collector)
    config_bytes = (
        '[scan]\nroots=["shop"]\nnamespace="shop"\ncontract="architecture-contract.json"\n'
        f"collector_argv={json.dumps(argv)}\n"
    ).encode()
    if limit is not None:
        config_bytes += f"collector_output_limit_bytes={limit}\n".encode()
    if timeout is not None:
        config_bytes += f"collector_timeout_seconds={timeout}\n".encode()
    (fixture / "archkeel.toml").write_bytes(config_bytes)
    config = parse_config(config_bytes)
    monkeypatch.setattr(demo_catalog_check, "FIXTURE_DIR", fixture)
    monkeypatch.setattr(demo_catalog_check, "CONFIG", config)
    prepared = demo_catalog_check.build_and_run_check(
        tmp_path / "protocol",
        demo_catalog_check._COMMENT_ONLY_FILES,
        "empty_declaration",
        analyzer=observer_for("python", collector_argv=argv),
    )
    assert prepared.exit_code == 0
    source = prepared.provenance
    assert source is not None
    seen.unlink()
    root = tmp_path / "protocol/root"
    requested: list[object] = []
    build_observer = cli.observer_for

    def record(*args, **kwargs):
        requested.append(kwargs.get("timeout_seconds"))
        return build_observer(*args, **kwargs)

    monkeypatch.setattr(cli, "observer_for", record)
    code = main(
        [
            "check",
            "--root",
            str(root),
            "--baseline",
            source.baseline,
            "--expectation-commit",
            source.expectation,
            "--head",
            source.head,
            "--expected",
            "expectation.json",
            "--expected-digest",
            source.expected_digest,
            "--branch",
            "candidate",
            "--accepted-branch",
            "main",
            "--host-records",
            str(tmp_path / "protocol/host-records.json"),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    if limit == 1:
        assert code == 2, result
        assert result["observation_complete"] == "UNKNOWN"
        assert any("1 byte limit" in item["unknown_claim"] for item in result["diagnostics"])
    else:
        assert code == 0, result
    assert requested == [timeout], "check did not bind the configured timeout"
    assert seen.is_file(), "check bypassed the configured collector"
    revisions = seen.read_text().splitlines()
    if limit == 1:
        assert len(revisions) == 1  # Reject incomplete accepted evidence before the candidate.
    else:
        assert source.head in revisions
        assert len(revisions) == 2
