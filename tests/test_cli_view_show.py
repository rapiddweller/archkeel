# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-287: `archkeel view show` writes the Explorer report with the check result embedded."""

import json
import re
from pathlib import Path

import pytest
from test_cli_view import EXAMPLE, _edge, _observation, _snapshot, _spec, _tampered

from archkeel.cli import main

_PAGE = "architecture.report.html"
_EMBED = re.compile(r'<script id="view-check-data" type="application/json">(.*?)</script>', re.S)


def _embedded(page: Path) -> object:
    match = _EMBED.search(page.read_text())
    assert match is not None
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def packet(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _snapshot(tmp_path_factory.mktemp("show"))


def _files(tmp_path: Path, packet: bytes, spec: dict) -> tuple[Path, Path]:
    snapshot, view = tmp_path / "architecture.json", tmp_path / "view.json"
    snapshot.write_bytes(packet)
    view.write_text(json.dumps(spec))
    return view, snapshot


def test_show_embeds_the_check_result_and_prints_what_check_prints(
    tmp_path: Path, packet: bytes, capsys: pytest.CaptureFixture
) -> None:
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(packet)
    output = tmp_path / "out"
    arguments = [str(EXAMPLE), "--snapshot", str(snapshot), "--json"]
    assert main(["view", "check", *arguments]) == 0
    checked = capsys.readouterr().out
    assert main(["view", "show", *arguments, "--output", str(output)]) == 0
    shown = capsys.readouterr()
    assert shown.out == checked
    page = output / _PAGE
    assert shown.err == f"archkeel view show: wrote {page}\n"
    assert _embedded(page) == json.loads(checked)
    assert (output / "architecture.json").read_bytes() == packet
    # The page links the copied snapshot, never an absolute path of this machine.
    assert str(tmp_path) not in page.read_text()
    assert not any(_EMBED.search(item.read_text()) for item in output.glob("*.detail*.html"))


def test_a_missing_reference_is_drawn_and_exits_1(
    tmp_path: Path, packet: bytes, capsys: pytest.CaptureFixture
) -> None:
    spec = _spec(_observation(packet), edges=[_edge("shop.render.text", "shop.cli.main")])
    view, snapshot = _files(tmp_path, packet, spec)
    output = tmp_path / "out"
    assert (
        main(["view", "show", str(view), "--snapshot", str(snapshot), "--output", str(output)]) == 1
    )
    embedded = _embedded(output / _PAGE)
    assert isinstance(embedded, dict) and embedded["edges"][0]["status"] == "missing"


@pytest.mark.parametrize("broken", ["stale", "tampered", "invalid"])
def test_a_check_that_did_not_run_writes_nothing(
    tmp_path: Path, packet: bytes, broken: str, capsys: pytest.CaptureFixture
) -> None:
    spec = _spec(_observation(packet))
    if broken == "stale":
        spec["snapshot"] = {"source_digest": "0" * 64, "contract_digest": "0" * 64}
    if broken == "invalid":
        spec["status"] = "proven"
    view, snapshot = _files(tmp_path, packet, spec)
    if broken == "tampered":
        snapshot.write_text(_tampered(packet))
    output = tmp_path / "out"
    assert (
        main(["view", "show", str(view), "--snapshot", str(snapshot), "--output", str(output)]) == 2
    )
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["exit_code"] == 2


def test_show_writes_nothing_into_the_analyzed_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repository = tmp_path / "repository"
    packet = _snapshot(repository)
    root = repository / "repo"
    snapshot = root / "test-artifacts/architecture/architecture.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(packet)
    spec = root / "flow.json"
    spec.write_text(json.dumps(_spec(_observation(packet))))
    before = sorted(path for path in root.rglob("*") if ".git" not in path.parts)
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    assert main(["view", "show", str(spec), "--snapshot", str(snapshot), "--json"]) == 0
    assert sorted(path for path in root.rglob("*") if ".git" not in path.parts) == before
    digest = _observation(packet).source.source_digest
    page = cache / "archkeel/view" / digest[:16] / _PAGE
    assert capsys.readouterr().err == f"archkeel view show: wrote {page}\n"
    assert page.is_file()


def test_show_on_a_contract_without_rules_draws_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The explore shape (#791): layout components, no rule; the view keeps every status."""
    components = [
        {
            "id": f"COMP-{name.upper()}",
            "label": name,
            "role": "component",
            "packages": [f"shop.{name}"],
            "namespace": f"shop.{name}",
            "responsibilities": [f"Hold shop.{name}."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/architecture/shop.md"],
        }
        for name in ("app", "cli", "model", "render", "store")
    ]
    contract = {"schema_version": "2.2.0", "components": components, "rules": []}
    packet = _snapshot(
        tmp_path / "bare", {"architecture-contract.json": json.dumps(contract, indent=2) + "\n"}
    )
    nodes = ["COMP-CLI", "COMP-APP", "shop.cli.main", "shop.app.orders"]
    steps = [{"node": "shop.cli.main"}, {"node": "shop.app.orders", "kind": "imports"}]
    view, snapshot = _files(tmp_path, packet, _spec(_observation(packet), nodes=nodes, steps=steps))
    output = tmp_path / "out"
    assert (
        main(["view", "show", str(view), "--snapshot", str(snapshot), "--output", str(output)]) == 0
    )
    embedded = _embedded(output / _PAGE)
    assert isinstance(embedded, dict)
    assert [step["status"] for step in embedded["steps"]] == ["proven", "proven"]
    assert "PASS" not in json.dumps(embedded)


def test_check_takes_no_output(
    tmp_path: Path, packet: bytes, capsys: pytest.CaptureFixture
) -> None:
    view, snapshot = _files(tmp_path, packet, _spec(_observation(packet)))
    output = tmp_path / "out"
    arguments = ["view", "check", str(view), "--snapshot", str(snapshot), "--output", str(output)]
    assert main(arguments) == 2
    assert not output.exists()
    assert "--output" in capsys.readouterr().out
