# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A requires target must name a component at the contract level that declares it."""

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from test_analyzer import _component

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import COMPONENT_GRAPH_MARKER
from archkeel.ir.model import Diagnostic


def _component_at(
    label: str,
    package: str,
    *,
    requires: tuple[str, ...] = (),
    inside: str | None = None,
) -> dict[str, object]:
    component = _component(label, packages=[package])
    if requires:
        component["requires"] = [
            {"component": target, "rationale": "Uses this peer."} for target in requires
        ]
    if inside is not None:
        component["inside"] = inside
    return component


def _contract(
    components: list[dict[str, object]], *, complete_requires: bool = False
) -> dict[str, object]:
    rules = (
        [
            {
                "id": "REQUIRES-COMPLETE",
                "kind": "complete_requires",
                "rationale": "Every dependency pair is explicitly decided.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ]
        if complete_requires
        else []
    )
    return {"schema_version": "2.1.0", "components": components, "rules": rules}


def _write_repo(
    root: Path,
    *,
    app_requires: tuple[str, ...] = ("peer",),
    service_requires: tuple[str, ...] = ("local",),
    deep_requires: tuple[str, ...] = ("deep_peer",),
) -> ScanConfig:
    (root / "contracts").mkdir(parents=True, exist_ok=True)
    (root / "docs/architecture").mkdir(parents=True, exist_ok=True)
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n',
        encoding="utf-8",
    )
    (root / "contract.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at(
                        "app", "sample.app", requires=app_requires, inside="contracts/one.json"
                    ),
                    _component_at("peer", "sample.peer", inside="contracts/peer.json"),
                ],
                complete_requires=True,
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/one.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at(
                        "service",
                        "sample.app.service",
                        requires=service_requires,
                        inside="contracts/two.json",
                    ),
                    _component_at("local", "sample.app.local"),
                ]
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/two.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at("deep", "sample.app.service.deep", requires=deep_requires),
                    _component_at("deep_peer", "sample.app.service.deep_peer"),
                ]
            )
        ),
        encoding="utf-8",
    )
    (root / "contracts/peer.json").write_text(
        json.dumps(_contract([_component_at("peer_api", "sample.peer.api")])),
        encoding="utf-8",
    )
    (root / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n", encoding="utf-8"
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    for package in (
        "sample",
        "sample/app",
        "sample/app/service",
        "sample/app/local",
        "sample/app/service/deep",
        "sample/app/service/deep_peer",
        "sample/peer",
        "sample/peer/api",
    ):
        directory = root / package
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "qa@example.invalid"],
        ["git", "config", "user.name", "QA"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def _append_component(root: Path, contract_path: str, component: dict[str, object]) -> None:
    path = root / contract_path
    raw = json.loads(path.read_bytes())
    raw["components"].append(component)
    path.write_text(json.dumps(raw), encoding="utf-8")


def _assert_requires_diagnostic(
    diagnostics: Iterable[Diagnostic], *, target: str, pointer: str
) -> None:
    matches = [item for item in diagnostics if item.pointer == pointer]
    assert len(matches) == 1, diagnostics
    diagnostic = matches[0]
    assert target in diagnostic.subject or target in diagnostic.unknown_claim
