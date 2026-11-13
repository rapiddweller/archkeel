# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-428: import verdicts need publication proof, not a profile permission."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_cli_native_core_scan import built as built  # noqa: F401


def scan(
    built: Path, root: Path, source: str, *, public: str = "app.api", grant: str | None = None
) -> dict[str, Any]:
    (root / "src").mkdir(exist_ok=True)
    (root / "src/client.ts").write_text(source)
    (root / "src/api.ts").write_text("export const Published = 1; export const _private = 2;\n")
    (root / "src/impl.ts").write_text("export const Secret = 1;\n")
    (root / "tsconfig.json").write_text(
        (Path(__file__).parents[1] / "fixtures/H-typescript/tsconfig.json").read_text()
    )
    template = json.loads(
        (Path(__file__).parents[1] / "fixtures/H-typescript/architecture-contract.json").read_text()
    )
    components = []
    for label, modules in (("client", ["app.client"]), ("service", ["app.api", "app.impl"])):
        component = {**template["components"][0], "id": f"COMP-{label.upper()}", "label": label}
        component.update(
            packages=[m.replace("app.", "app.src.") + "_x2e_ts" for m in modules], requires=[]
        )
        component.pop("public", None)
        if label == "service":
            module, separator, name = public.partition(":")
            component["public"] = [
                module.replace("app.", "app.src.") + "_x2e_ts" + separator + name
            ]
        components.append(component)
    rule: dict[str, Any] = {
        "id": "INTERFACE",
        "kind": "interface_boundary",
        "rationale": "Use the public interface.",
        "provenance": ["p"],
        "decided_by": "architect",
    }
    if grant:
        rule["module_object_grants"] = [
            {
                "source_module": grant.replace("app.", "app.src.") + "_x2e_ts",
                "target_module": "app.src.impl_x2e_ts",
            }
        ]
    (root / "architecture-contract.json").write_text(
        json.dumps(
            {
                "schema_version": "3.14.0",
                "components": components,
                "rules": [rule],
            }
        )
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\n'
    )
    for args in (
        ["init", "-q"],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-qm",
            "Create test root",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return run_core(built, root)


def run_core(built: Path, root: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    request = {
        "protocol": "archkeel-core-scan-1",
        "root": str(root),
        "config": "archkeel.toml",
        "git_head": head,
        "dirty": True,
    }
    done = subprocess.run(
        [str(built / "archkeel-core"), "scan"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    assert done.returncode in (0, 3), done.stderr
    frame = json.loads(done.stdout)
    assert "INTERFACE" in frame["rules"], frame
    return frame


@pytest.mark.parametrize(
    ("source", "public", "grant", "expected"),
    [
        ('import { Published } from "./api";', "app.api", None, "PASS"),
        ('import "./api";', "app.api", None, "PASS"),
        ('import "./impl";', "app.api", "app.client", "PASS"),
        ('import { _private } from "./api";', "app.api", None, "FAIL"),
        ('import { Published } from "./api";', "app.api:Other", None, "FAIL"),
        ('import "./impl";', "app.api", None, "FAIL"),
        ('import "./impl";', "app.api", "app.other", "FAIL"),
        ('import { Secret } from "./impl";', "app.api", "app.client", "UNKNOWN"),
    ],
)
def test_direct_imports_and_exact_module_object_grants(
    built: Path, tmp_path: Path, source: str, public: str, grant: str | None, expected: str
) -> None:
    frame = scan(built, tmp_path, source, public=public, grant=grant)
    assert frame["rules"]["INTERFACE"][1] == expected, frame


@pytest.mark.parametrize(
    "source",
    [
        'export * from "./impl";',
        'export { Secret as Published } from "./impl";',
        'import * as hidden from "./impl"; hidden.Secret;',
        'export { default } from "./impl";',
        'const hidden = require("./impl");',
        'const hidden = import("./impl");',
        'import type { Secret } from "./impl";',
    ],
)
def test_an_unproved_crossing_never_passes(built: Path, tmp_path: Path, source: str) -> None:
    frame = scan(built, tmp_path, source)
    assert frame["rules"]["INTERFACE"][1] in {"UNKNOWN", "FAIL"}, frame


@pytest.mark.parametrize(
    "publication",
    [
        'export * from "./impl";',
        'export { Secret as Published } from "./impl";',
        'export { default as Published } from "./impl";',
        "export class Published {} export namespace Published {}",
    ],
)
def test_a_public_barrel_needs_a_witness(built: Path, tmp_path: Path, publication: str) -> None:
    scan(built, tmp_path, 'import { Published } from "./api";')
    (tmp_path / "src/api.ts").write_text(publication)
    frame = run_core(built, tmp_path)
    assert frame["rules"]["INTERFACE"][1] != "PASS", frame
    assert "unread import binding" in json.dumps(frame), frame


def test_fail_retains_import_evidence_beside_a_gap(built: Path, tmp_path: Path) -> None:
    frame = scan(
        built, tmp_path, 'import { _private } from "./api"; import * as hidden from "./impl";'
    )
    assert frame["rules"]["INTERFACE"][1] == "FAIL", frame
    assert frame["violations"], frame


def test_excluded_types_and_forbidden_imports_are_not_subjects(built: Path, tmp_path: Path) -> None:
    scan(built, tmp_path, 'import type { Secret } from "./impl";')
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"][0]["include_type_checking"] = False
    path.write_text(json.dumps(contract))
    assert run_core(built, tmp_path)["rules"]["INTERFACE"][1] == "PASS"
    (tmp_path / "src/client.ts").write_text('import "./impl";')
    contract["rules"].append(
        {
            **contract["rules"][0],
            "id": "FORBID",
            "kind": "forbidden_dependency",
            "source": "app.src.client_x2e_ts",
            "target": "app.src.impl_x2e_ts",
        }
    )
    path.write_text(json.dumps(contract))
    frame = run_core(built, tmp_path)
    assert frame["rules"]["INTERFACE"][1] == "PASS", frame
    assert frame["rules"]["FORBID"][1] == "FAIL", frame


def test_rust_names_its_missing_publication_surface(built: Path, tmp_path: Path) -> None:
    from tests.test_cli_native_core_scan import _rust_repository

    root = _rust_repository(built, tmp_path)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"] = [
        {
            "id": "INTERFACE",
            "kind": "interface_boundary",
            "rationale": "Use the public interface.",
            "provenance": ["p"],
            "decided_by": "architect",
        }
    ]
    path.write_text(json.dumps(contract))
    frame = run_core(built, root)
    assert frame["rules"]["INTERFACE"][1] == "UNKNOWN", frame
    assert "interface_boundary: incomplete publication surface" in json.dumps(frame), frame


@pytest.mark.parametrize(
    "case", ["no_public", "same_component", "unowned_source", "unowned_target"]
)
def test_non_subject_imports_do_not_fail(built: Path, tmp_path: Path, case: str) -> None:
    scan(built, tmp_path, 'import "./impl";')
    path = tmp_path / "architecture-contract.json"
    contract = json.loads(path.read_text())
    client, service = contract["components"]
    if case == "no_public":
        service.pop("public")
    elif case == "same_component":
        service["packages"].extend(client["packages"])
        contract["components"] = [service]
    elif case == "unowned_source":
        contract["components"] = [service]
    else:
        contract["components"] = [client]
    path.write_text(json.dumps(contract))
    assert run_core(built, tmp_path)["rules"]["INTERFACE"][1] == "PASS"
