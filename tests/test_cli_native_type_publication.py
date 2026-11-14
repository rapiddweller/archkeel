# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-434: release-core type imports need a direct witness or one same-name export hop."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.test_native_interface_boundary import run_core, scan


@pytest.fixture(scope="module")
def release() -> Path:
    native = Path(__file__).parents[1] / "native"
    subprocess.run(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "-q",
            "-p",
            "archkeel-core",
            "-p",
            "archkeel-typescript-collector",
            "-p",
            "archkeel-rust-collector",
        ],
        cwd=native,
        env={**os.environ, "ARCHKEEL_VERSION": "0.0.0"},
        check=True,
    )
    return native / "target/release"


@pytest.mark.parametrize(
    ("api", "implementation", "source", "expected"),
    [
        ("export interface Published {}", "", 'import type { Published } from "./api";', "PASS"),
        ("export type Published = string;", "", 'import { type Published } from "./api";', "PASS"),
        (
            'export type { Published } from "./impl";',
            "export interface Published {}",
            'import type { Published } from "./api";',
            "PASS",
        ),
        (
            'export { type Published } from "./impl";',
            "export type Published = string;",
            'import type { Published } from "./api";',
            "PASS",
        ),
        (
            "export interface Published {}",
            "export interface Published {}",
            'import type { Published } from "./impl";',
            "FAIL",
        ),
        (
            'export type { Secret as Published } from "./impl";',
            "export interface Secret {}",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            'export type { Published as Published } from "./impl";',
            "export interface Published {}",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            'export type { Published } from "./impl";',
            'export type { Published } from "./other";',
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            'export * from "./impl";',
            "export interface Published {}",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {} export interface Published { x: string }",
            "",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {} export class Published {}",
            "",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {} export namespace Published {}",
            "",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {} export namespace Published.Inner {}",
            "",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        (
            'export type { Published } from "./impl";',
            "export interface Published {} export class Published {}",
            'import type { Published } from "./api";',
            "UNKNOWN",
        ),
        ("interface Published {}", "", 'import type { Published } from "./api";', "UNKNOWN"),
        (
            "export interface Published {}",
            "",
            'import type { Published as Local } from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {}",
            "",
            'import type { Published as Published } from "./api";',
            "UNKNOWN",
        ),
        (
            "export default interface Published {}",
            "",
            'import type Published from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {}",
            "",
            'import type * as Published from "./api";',
            "UNKNOWN",
        ),
        (
            "export interface Published {}",
            "",
            'import type { Published } from "./api"; interface Published {}',
            "UNKNOWN",
        ),
    ],
)
def test_type_publication_forms(
    release: Path, tmp_path: Path, api: str, implementation: str, source: str, expected: str
) -> None:
    scan(release, tmp_path, source)
    (tmp_path / "src/api.ts").write_text(api)
    (tmp_path / "src/impl.ts").write_text(implementation or "export {};")
    if "./other" in implementation:
        (tmp_path / "src/other.ts").write_text("export interface Published {}")
    frame = run_core(release, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == expected, frame
    if expected == "UNKNOWN":
        assert "unproven named type publication" in frame["explained"]["INTERFACE"], frame


def test_a_proven_type_cannot_hide_an_unowned_source(release: Path, tmp_path: Path) -> None:
    scan(release, tmp_path, 'import type { Published } from "./api";')
    (tmp_path / "src/api.ts").write_text("export interface Published {}")
    extra = tmp_path / "src/extra.ts"
    extra.write_text('import type { Published } from "./api";')
    frame = run_core(release, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == "UNKNOWN", frame
    assert "a module has not exactly one owner" in frame["explained"]["INTERFACE"], frame


def test_type_publication_does_not_lift_dependency_symbol_limits(
    release: Path, tmp_path: Path
) -> None:
    scan(release, tmp_path, 'import type { Published } from "./api";')
    (tmp_path / "src/api.ts").write_text("export interface Published {}")
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["components"][0]["requires"] = [
        {
            "component": "service",
            "rationale": "Use the type port.",
            "through": ["app.src.api_x2e_ts:Published"],
        }
    ]
    contract["rules"].extend(
        [
            {
                **contract["rules"][0],
                "id": "SYMBOL",
                "kind": "forbidden_dependency",
                "source": "app.src.client_x2e_ts",
                "target": "app.src.api_x2e_ts",
                "target_symbol": "Other",
                "include_type_checking": True,
            },
            {**contract["rules"][0], "id": "REQUIRES", "kind": "complete_requires"},
        ]
    )
    path.write_text(json.dumps(contract))
    frame = run_core(release, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == "PASS", frame
    for rule in ("SYMBOL", "REQUIRES"):
        assert frame["rules"][rule][1] == "UNKNOWN", frame
        assert "undecided" in frame["explained"][rule], frame
