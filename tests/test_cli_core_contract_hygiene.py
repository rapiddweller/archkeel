# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-466: each contract hygiene defect of release 4.0.1 keeps the default path from PASS.

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
TARGET = "\n<!-- archkeel-target-graph -->\n```mermaid\nflowchart LR\n    app --> data\n```\n"


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
    contract["rules"].append(
        allowed | {"source": forbidden["source"], "target": forbidden["target"]}
    )


def _interface(contract: dict[str, Any]) -> None:
    base = {
        key: rule(contract, "REQUIRES")[key] for key in ("rationale", "provenance", "decided_by")
    }
    contract["rules"].append(base | {"id": "FACADES", "kind": "interface_boundary"})


def _cite(text: str) -> Callable[[Path], None]:
    """Let the `data` component cite the page through another form of its path."""

    def plant(root: Path) -> None:
        value = str(root / PAGE) if text == "absolute" else text
        edit(root, lambda c: component(c, "data").update(provenance=[value]))

    return plant


def _declare(declarations: dict[str, Any]) -> Callable[[Path], None]:
    """Add declarations with schema 3.6, the newest schema that 4.0.1 reads."""

    def change(contract: dict[str, Any]) -> None:
        contract["schema_version"] = "3.6.0"
        contract["declarations"] = declarations

    return lambda root: edit(root, change)


def _mount(root: Path, rules: list[dict[str, Any]], package: str) -> None:
    """Mount an inside contract on `domain` with one component and `rules`."""

    def change(contract: dict[str, Any]) -> None:
        domain = component(contract, "domain")
        domain["inside"] = "inside.json"
        child = {**domain, "id": "COMP-ORDER", "label": "order", "packages": [package]}
        child["public"] = [package]
        child.pop("inside")
        child["requires"] = []
        inside = {"schema_version": contract["schema_version"], "components": [child]}
        (root / "inside.json").write_text(json.dumps(inside | {"rules": rules}))

    edit(root, change)


def _inside_allows_data(root: Path) -> None:
    base = {"rationale": "Order reads data.", "provenance": [PAGE], "decided_by": "architect"}
    allowed = base | {"id": "ORDER-DATA", "kind": "allowed_dependency"}
    allowed |= {"source": "shop.src.domain.order_x2e_ts", "target": "shop.src.data"}
    _mount(root, [allowed], "shop.src.domain.order_x2e_ts")


def _inside_claims_data(root: Path) -> None:
    _mount(root, [], "shop.src.data")


def _fence(root: Path) -> None:
    text = (root / PAGE).read_text()
    (root / PAGE).write_text(text.replace("```mermaid\n", "```text\n"))


PAGE_BUDGET = {"provenance": [PAGE]}

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
        lambda root: edit(
            root, lambda c: component(c, "data")["packages"].append("shop.src.ghost")
        ),
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
    "dot-dot-path": ("reference.provenance", _cite("docs/../docs/architecture/shop.md")),
    "dot-path": ("reference.provenance", _cite("docs/./architecture/shop.md")),
    "empty-segment": ("reference.provenance", _cite("docs//architecture/shop.md")),
    "trailing-slash": ("reference.provenance", _cite("docs/architecture/shop.md/")),
    "absolute-path": ("reference.provenance", _cite("absolute")),
    "backslash-path": ("reference.provenance", _cite("docs\\architecture\\shop.md")),
    "text-fence": ("graph.count", _fence),
    "facade-budget": (
        "budget",
        _declare({"facade_budgets": [{"component": "domain", "max_names": 0} | PAGE_BUDGET]}),
    ),
    "coupling-budget": (
        "budget",
        _declare(
            {
                "coupling_budgets": [
                    {"source": "data", "target": "domain", "max_names": 0} | PAGE_BUDGET
                ]
            }
        ),
    ),
    "measurement-budget": (
        "budget",
        _declare({"measurement_budgets": [{"name": "cycle_edges"} | PAGE_BUDGET]}),
    ),
    "compat": (
        "compatibility.invalid",
        _declare(
            {
                "compat": [
                    {
                        "module": "shop.src.domain.index_x2e_ts",
                        "target": "shop.src.domain.order_x2e_ts",
                        "lifetime": "migration",
                    }
                ]
            }
        ),
    ),
    "inside-allows-forbidden": ("inside.forbidden_import", _inside_allows_data),
    "inside-claims-outside": ("contract.invalid", _inside_claims_data),
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


# A cited path that the core cannot read refuses the whole contract (exit 2).
REFUSED = frozenset(
    {
        "missing-page",
        "outside-link",
        "dot-dot-path",
        "dot-path",
        "empty-segment",
        "trailing-slash",
        "absolute-path",
        "backslash-path",
    }
)
# A family that applies and that the core does not port: a named gap.
NOT_PORTED = frozenset({"interface", "compat", "measurement-budget", "inside-allows-forbidden"})
# The core holds these runs by a gap that it already had: a profile limit, a refused contract or
# the domain of a mount. The hygiene check is not reached, as in 4.0.1, which also stops earlier.
EARLIER = frozenset({"facade-budget", "coupling-budget", "inside-claims-outside"})


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
            kinds = {gap["kind"] for gap in result["gaps"]}
            if name in REFUSED:
                refusal = result["frame"]["unsupported"]["rules"]
                assert code == 2 and isinstance(refusal, str) and "cannot read" in refusal
                assert "reference.provenance" in kinds, result["gaps"]
            elif name in NOT_PORTED:
                assert "contract_hygiene_not_ported" in kinds, result["gaps"]
                assert code_name.split(".")[0] in json.dumps(result["frame"]["unsupported"])
            elif name not in EARLIER:
                # The gap kind is the code of release 4.0.1, typed by the shell.
                assert code_name in kinds, result["gaps"]


def test_the_static_report_shows_the_hygiene_code(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    with shop() as root:
        PLANTS["no-graph"][1](root)
        code, _ = run("report", "--root", str(root), "--output", str(target))
    assert code == 2
    assert "contract hygiene graph.count" in target.read_text()


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
