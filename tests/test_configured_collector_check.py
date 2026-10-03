# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Historical check uses the same configured process port as init and report."""

import json
import shutil
import sys
from pathlib import Path

from archkeel.cli import main
from archkeel.cli.config import parse_config
from archkeel.cli.observe import observer_for
from fixtures import demo_catalog_check


def test_check_reobserves_revisions_with_configured_collector(
    tmp_path: Path, monkeypatch, capsys
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
    assert code == 0, result
    assert seen.is_file(), "check bypassed the configured collector"
    revisions = seen.read_text().splitlines()
    assert source.head in revisions
    assert len(revisions) == 2
