# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-458: each contract hygiene defect of release 4.0.1 keeps the default path from PASS.

Each plant starts from `fixtures/H-typescript` without its UML target, which the release core and
the default shell decide with PASS. Each plant breaks one condition that release 4.0.1 rejects
with exit 2 and names the code of that condition. The core must name the same code, and the run
must not give PASS or exit 0.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import case, materialized

from archkeel.cli import core_only
from archkeel.cli.native_scan import exchange

CONTRACT = "architecture-contract.json"
PAGE = "docs/architecture/shop.md"


@contextmanager
def shop() -> Iterator[Path]:
    """The TypeScript fixture without its UML target: the core decides it with PASS."""
    with materialized(case("fixture/H-typescript")) as root:
        edit(root, lambda contract: contract.pop("declarations"))
        yield root.resolve()


def edit(root: Path, change: Callable[[dict[str, Any]], object]) -> None:
    path = root / CONTRACT
    contract = json.loads(path.read_text())
    change(contract)
    path.write_text(json.dumps(contract))


def component(contract: dict[str, Any], label: str) -> dict[str, Any]:
    return next(item for item in contract["components"] if item["label"] == label)


def rule(contract: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(item for item in contract["rules"] if item["id"] == identifier)


def page(root: Path, old: str, new: str) -> None:
    path = root / PAGE
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


GRAPH = "<!-- archkeel-component-graph -->"
TARGET = (
    "\n<!-- archkeel-target-graph -->\n```mermaid\nflowchart LR\n    app --> data\n```\n"
)


def _forbid_observed(contract: dict[str, Any]) -> None:
    forbidden = {**rule(contract, "DOMAIN-NO-DATA"), "id": "APP-NO-DATA"}
    contract["rules"].append(forbidden | {"source": "shop.src.main_x2e_ts"})


def _link_outside(root: Path) -> None:
    # A link inside the root reads its target, as 4.0.1 does; a link that leaves the root does not.
    outside = root.parent / f"{root.name}-page.md"
    outside.write_bytes((root / PAGE).read_bytes())
    (root / PAGE).unlink()
    (root / PAGE).symlink_to(outside)


def _duplicate(contract: dict[str, Any]) -> None:
    contract["rules"].append({**rule(contract, "DOMAIN-NO-DATA"), "id": "DOMAIN-NO-DATA-AGAIN"})


def _conflict(contract: dict[str, Any]) -> None:
    forbidden = rule(contract, "DOMAIN-NO-DATA")
    allowed = {key: forbidden[key] for key in ("rationale", "provenance", "decided_by")}
    allowed |= {"id": "DOMAIN-DATA", "kind": "allowed_dependency"}
    contract["rules"].append(allowed | {"source": forbidden["source"], "target": forbidden["target"]})


def _interface(contract: dict[str, Any]) -> None:
    base = {key: rule(contract, "REQUIRES")[key] for key in ("rationale", "provenance", "decided_by")}
    contract["rules"].append(base | {"id": "FACADES", "kind": "interface_boundary"})


# Each plant: the code that 4.0.1 names, and the change of the fixture.
PLANTS: dict[str, tuple[str, Callable[[Path], None]]] = {
    "missing-page": ("reference.provenance", lambda root: (root / PAGE).unlink()),
    "outside-link": ("reference.provenance", _link_outside),
    "no-graph": ("graph.count", lambda root: page(root, GRAPH, "")),
    "two-graphs": (
        "graph.count",
        lambda root: (root / PAGE).write_text((root / PAGE).read_text() * 2),
    ),
    "drawn-not-found": ("graph.drift", lambda root: page(root, "    app --> data\n", "")),
    "unknown-line": (
        "graph.drift",
        lambda root: page(root, "    app --> data\n", "    app --> data\n    subgraph x\n"),
    ),
    "target-graph": (
        "graph.drift",
        lambda root: (root / PAGE).write_text((root / PAGE).read_text() + TARGET),
    ),
    "namespace": (
        "reference.namespace",
        lambda root: edit(root, lambda c: rule(c, "DOMAIN-NO-DATA").update(source="other.x")),
    ),
    "public-owner": (
        "reference.public_owner",
        lambda root: edit(
            root, lambda c: component(c, "data").update(public=["shop.src.domain.order_x2e_ts"])
        ),
    ),
    "public-underscore": (
        "reference.public_underscore",
        lambda root: edit(
            root, lambda c: component(c, "data").update(public=["shop.src.data.local_x2e_ts:_x"])
        ),
    ),
    "package-unscanned": (
        "reference.package_unscanned",
        lambda root: edit(root, lambda c: component(c, "data")["packages"].append("shop.src.ghost")),
    ),
    "observed-forbidden": (
        "closed_world.observed_forbidden",
        lambda root: edit(root, _forbid_observed),
    ),
    "duplicate": ("closed_world.duplicate", lambda root: edit(root, _duplicate)),
    "conflict": ("decision.conflict", lambda root: edit(root, _conflict)),
    "open": (
        "decision.open",
        lambda root: edit(
            root, lambda c: c.update(rules=[r for r in c["rules"] if r["id"] != "REQUIRES"])
        ),
    ),
    "placeholder": (
        "rationale.placeholder",
        lambda root: edit(root, lambda c: rule(c, "LAYOUT").update(rationale="TODO: explain.")),
    ),
    "repeated": (
        "rationale.repeated",
        lambda root: edit(
            root,
            lambda c: rule(c, "DOMAIN-NO-DATA").update(rationale="Domain does not depend on data."),
        ),
    ),
    "responsibility": (
        "responsibility.missing",
        lambda root: edit(root, lambda c: component(c, "data").update(responsibilities=["TBD"])),
    ),
    "interface": ("interface.unused", lambda root: edit(root, _interface)),
    "api-surface": (
        "api_surface.missing",
        lambda root: edit(
            root,
            lambda c: c.update(
                declarations={
                    "public_api": ["shop.src.ghost"],
                    "public_api_provenance": [PAGE],
                }
            ),
        ),
    ),
}


def test_the_unbroken_fixture_passes_and_binds_its_page(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    with shop() as root:
        code, result = run("validate", "--root", str(root))
    assert (code, result["status"]) == (0, "PASS"), result
    assert not result["frame"]["unsupported"]["rules"]
    assert PAGE in result["frame"]["self_test"]["collect"]["contract_files"]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_each_hygiene_defect_keeps_the_run_from_pass(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    code_name, plant = PLANTS[name]
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    with shop() as root:
        plant(root)
        for verb in ("validate", "report"):
            code, result = run(verb, "--root", str(root))
            assert code != 0 and result["status"] != "PASS", result
            assert code_name in json.dumps(result["frame"]["unsupported"]), result
    if name in {"missing-page", "outside-link"}:
        # A cited file that the core cannot read refuses the whole contract (exit 2).
        assert code == 2 and isinstance(result["frame"]["unsupported"]["rules"], str)


def test_a_page_change_after_the_run_refuses_the_replay(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    with shop() as root:
        # Keep HEAD and dirty unchanged across the replay.
        (root / "untracked").write_text("dirty")
        saved: tuple[bytes, int] | None = None

        def replay(binary: str, kind: str, payload: bytes) -> tuple[bytes, int]:
            nonlocal saved
            saved = saved or exchange(binary, kind, payload)
            return saved

        monkeypatch.setattr(core_only, "exchange", replay)
        assert core_only.run(["validate", "--root", str(root), "--json"]) == 0
        capsys.readouterr()
        page(root, "flowchart LR\n", "flowchart LR\n%% edited\n")
        assert core_only.run(["validate", "--root", str(root), "--json"]) == 2
        result = json.loads(capsys.readouterr().out)
    assert result["refusal"]["kind"] == "request_mismatch"
    assert PAGE in result["refusal"]["message"]
