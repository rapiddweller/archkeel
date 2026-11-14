# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-446: a closed source witness resolves a script-global dependency, not execution order."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_native_interface_boundary import run_core, scan

CASES = json.loads(
    (Path(__file__).parents[1] / "native/typescript/testdata/global-publication.json").read_text()
)


def project(release: Path, root: Path, publisher: str, consumer: str) -> None:
    scan(release, root, consumer)
    (root / "src/api.ts").write_text(publisher)
    (root / "src/impl.ts").write_text("")
    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"moduleDetection": "legacy", "module": "none"},
                "include": ["src/**/*.ts"],
                "archkeel": {"scriptHost": "classic-browser"},
            }
        )
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    rule = {
        **contract["rules"][0],
        "kind": "forbidden_dependency",
        "source": "app.src.client_x2e_ts",
        "target": "app.src.api_x2e_ts",
        "include_type_checking": True,
    }
    contract["rules"] = [
        rule,
        {**rule, "id": "REVERSE", "source": rule["target"], "target": rule["source"]},
    ]
    path.write_text(json.dumps(contract))


@pytest.mark.parametrize("name,publisher,consumer", CASES["proved"])
def test_proven_edge_has_a_direction(
    release_core: Path, tmp_path: Path, name: str, publisher: str, consumer: str
) -> None:
    project(release_core.parent, tmp_path, publisher, consumer)
    frame = run_core(release_core.parent, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == "FAIL", (name, frame)
    assert frame["rules"]["REVERSE"][1] == "PASS", (name, frame)


@pytest.mark.parametrize("name,publisher,consumer,extra,content", CASES["unproved"])
def test_unproved_edge_keeps_its_named_gap(
    release_core: Path,
    tmp_path: Path,
    name: str,
    publisher: str,
    consumer: str,
    extra: str,
    content: str,
) -> None:
    project(release_core.parent, tmp_path, publisher, consumer)
    if extra:
        (tmp_path / extra).write_text(content)
    frame = run_core(release_core.parent, tmp_path)
    for rule in ("INTERFACE", "REVERSE"):
        assert frame["rules"][rule][1] == "UNKNOWN", (name, frame)
    assert "source_resolution_gap" in json.dumps(frame), (name, frame)


@pytest.mark.parametrize(
    "change",
    ["no-host", "auto", "force", "nodenext", "bundler", "mts", "cts", "mjs", "cjs"],
)
def test_unproved_script_environment_stays_unknown(
    release_core: Path, tmp_path: Path, change: str
) -> None:
    project(release_core.parent, tmp_path, "var Published = 1;", "Published();")
    path = tmp_path / "tsconfig.json"
    config = json.loads(path.read_text())
    options = config["compilerOptions"]
    if change == "no-host":
        config.pop("archkeel")
    elif change in {"auto", "force"}:
        options["moduleDetection"] = change
    elif change == "nodenext":
        options.update(module="nodenext", moduleResolution="nodenext")
    elif change == "bundler":
        options.update(module="esnext", moduleResolution="bundler")
    else:
        (tmp_path / "src/api.ts").rename(tmp_path / f"src/api.{change}")
        config["include"] = ["src/**/*"]
        options["allowJs"] = True
    path.write_text(json.dumps(config))
    frame = run_core(release_core.parent, tmp_path)
    assert frame["rules"]["REVERSE"][1] == "UNKNOWN", (change, frame)
    assert "source_resolution_gap" in json.dumps(frame), (change, frame)


@pytest.mark.parametrize(
    "consumer",
    [
        "function use(Published) { Published(); }",
        "function use() { let Published = 1; Published(); }",
        "declare function Published(): void; Published();",
        'import { Published } from "./impl"; Published();',
    ],
)
def test_a_shadowed_name_is_not_a_global_use(
    release_core: Path, tmp_path: Path, consumer: str
) -> None:
    project(release_core.parent, tmp_path, "var Published = 1;", consumer)
    (tmp_path / "src/impl.ts").write_text("export function Published() {}")
    frame = run_core(release_core.parent, tmp_path)
    assert frame["rules"]["INTERFACE"][1] != "FAIL", frame
    assert "Script global Published" not in json.dumps(frame), frame


def test_platform_globals_are_not_project_edges(release_core: Path, tmp_path: Path) -> None:
    project(release_core.parent, tmp_path, "var Published = 1;", "console.log(); document.close();")
    frame: dict[str, Any] = run_core(release_core.parent, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == "PASS", frame


@pytest.mark.parametrize("name,write", CASES["issue740"])
def test_issue740_cannot_prove_a_replaced_platform_global(
    release_core: Path, tmp_path: Path, name: str, write: str
) -> None:
    project(release_core.parent, tmp_path, "", "window.open();")
    (tmp_path / "src/impl.ts").write_text("export {}; " + write)
    frame = run_core(release_core.parent, tmp_path)
    assert frame["rules"]["REVERSE"][1] == "UNKNOWN", (name, frame)
    assert "source_resolution_gap" in json.dumps(frame), (name, frame)
