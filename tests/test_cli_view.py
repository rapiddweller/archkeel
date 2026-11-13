# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-284: a view spec is checked data; each reference is proven, declared, claim or unknown."""

import json
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.model import Observation
from archkeel.ir.view_spec import (
    check_view,
    parse_view_spec,
    snapshot_identity,
)

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "fixtures/F-architecture-view/place-order.json"
_HINTS = (
    '"""Name the order type for annotations only."""\n\n'
    "from __future__ import annotations\n\n"
    "from typing import TYPE_CHECKING\n\n"
    "if TYPE_CHECKING:\n"
    "    from shop.model.entities import Order\n\n\n"
    "def label(order: Order) -> str:\n"
    "    return str(order)\n"
)
_SUBMODULE = (
    '"""Import a submodule through its package."""\n\n'
    "from shop.store import repository\n\n\n"
    "def load() -> object:\n"
    "    return repository.OrderRepository\n"
)
_LOADER = (
    '"""Load a renderer by a name known only at run time."""\n\n'
    "import importlib\n\n\n"
    "def load(name: str) -> object:\n"
    '    return importlib.import_module(f"shop.{name}")\n'
)


def _snapshot(
    tmp_path: Path, overlay: dict[str, str | None] | None = None, *, complete: bool = True
) -> bytes:
    root = _prepare_repo(tmp_path, overlay or {})
    result, packet = run_report(root, config=load_config(root), analyzer=observe)
    assert result.exit_code == (0 if complete else 2) and packet is not None
    return packet


def _observation(packet: bytes) -> Observation:
    raw = decode_json(packet)
    assert isinstance(raw, dict)
    return parse_observation(decode_canonical_model(raw))


@pytest.fixture(scope="module")
def shop(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    return _observation(_snapshot(tmp_path_factory.mktemp("clean")))


@pytest.fixture(scope="module")
def changed(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    """The shop with a dynamic loader, a type-only import, a submodule import and a requires."""
    contract = json.loads((ROOT / "fixtures/F-architecture/architecture-contract.json").read_text())
    app = next(item for item in contract["components"] if item["id"] == "COMP-APP")
    app["requires"] = [{"component": "store", "rationale": "Use cases persist orders."}]
    header = (ROOT / "fixtures/F-architecture/shop/render/text.py").read_text().split('"""')[0]
    overlay = {
        "shop/render/loader.py": header + _LOADER,
        "shop/render/hints.py": header + _HINTS,
        "shop/app/p_ext.py": header + _SUBMODULE,
        "architecture-contract.json": json.dumps(contract, indent=2) + "\n",
    }
    return _observation(_snapshot(tmp_path_factory.mktemp("changed"), overlay))


def _spec(observation: Observation, **fields: object) -> dict[str, object]:
    identity = snapshot_identity(observation)
    spec: dict[str, object] = {
        "schema_version": "1.0.0",
        "title": "Place an order",
        "snapshot": {
            "source_digest": identity.source_digest,
            "contract_digest": identity.contract_digest,
        },
        "nodes": ["shop.cli.main", "shop.app.orders", "shop.render.text", "shop.model.entities"],
    }
    spec.update(fields)
    return spec


def _check(observation: Observation, strict: bool = False, **fields: object):
    return check_view(parse_view_spec(_spec(observation, **fields)), observation, strict=strict)


def _edge(source: str, target: str, kind: str | None = "imports", **extra: object) -> dict:
    return {"source": source, "target": target, **({"kind": kind} if kind else {}), **extra}


def _tampered(packet: bytes) -> str:
    """Add a fabricated render.text -> store import whose evidence is not in the snapshot."""
    raw = json.loads(packet)
    fields = raw["encoding"]["section_data_fields"]["imports"]
    record = json.loads(json.dumps(raw["imports"][0]))
    record[0], record[6] = "IMP-00000000deadbeef", ["EVD-00000000deadbeef"]
    for name, value in (("source_module", "shop.render.text"), ("target_module", "shop.store")):
        record[10][fields.index(name)] = value
    raw["imports"].append(record)
    return json.dumps(raw)


def test_a_snapshot_error_names_the_snapshot_and_no_report_panel(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "view.json"
    spec.write_text(EXAMPLE.read_text())
    missing = tmp_path / "absent.json"
    assert main(["view", "check", str(spec), "--snapshot", str(missing), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == str(missing)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    spec.write_text("{}")
    assert main(["view", "check", str(spec), "--snapshot", str(missing)]) == 2
    shown = capsys.readouterr()
    assert "Scan complete" not in shown.out + shown.err and "view spec" in shown.out + shown.err
    assert str(spec) in shown.out


# ---------- AD-289: a tour stop is author text beside facts measured from the snapshot ----------
TOUR = ROOT / "fixtures/F-architecture-view/first-contact-tour.json"


def _tour(observation: Observation, stops: list[dict], nodes: list[str]):
    raw = _spec(observation, schema_version="1.1.0", nodes=nodes, stops=stops)
    return check_view(parse_view_spec(raw), observation, strict=False)


def _oracle(observation: Observation, inside: set[str]) -> tuple[set, set]:
    """Count from the raw import records, not through the code under test."""
    modules = {record.title for record in observation.records("modules") or ()}
    pairs = {
        (str(record.data.get("source_module")), str(record.data.get("target_module")))
        for record in observation.records("imports") or ()
    }
    pairs = {(source, target) for source, target in pairs if target in modules}
    out = {pair for pair in pairs if pair[0] in inside and pair[1] not in inside}
    into = {pair for pair in pairs if pair[1] in inside and pair[0] not in inside}
    return out, into
