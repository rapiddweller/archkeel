# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432: the cache rule of the survey cannot hide a source file from a verdict.

Consumer: `archkeel validate`. The survey does not charge the file bytes below a directory that a
valid `CACHEDIR.TAG` proves as a cache. The survey selects no source: each collector still finds
its own files. Each test plants a source file with a forbidden edge below such a directory. The
run must find the edge or name a gap; it must not give PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from rust_repository import CRATE_RULES, claims, repository, rule, statuses, validate

from archkeel.cli import core_only

# The Cache Directory Tagging Specification: a cache holds a file with this name and this start.
TAG = "Signature: 8a477f597d28d172789f06886806bc55\n# This directory holds build output.\n"
USE_B = "use crate::b::make;\n"
PLANTS = {
    "a path module in a tagged target directory": (
        {
            "src/lib.rs": '#[path = "../target/planted.rs"]\nmod planted;\nmod b;\n',
            "target/CACHEDIR.TAG": TAG,
            "target/planted.rs": USE_B,
        },
        "native.app.planted",
    ),
    "a path module in a target directory without a tag": (
        {
            "src/lib.rs": '#[path = "../target/planted.rs"]\nmod planted;\nmod b;\n',
            "target/planted.rs": USE_B,
        },
        "native.app.planted",
    ),
    "a module directory that holds a tag": (
        {
            "src/lib.rs": "mod cache;\nmod b;\n",
            "src/cache/CACHEDIR.TAG": TAG,
            "src/cache/mod.rs": USE_B,
        },
        "native.app.cache",
    ),
    "a module file below a tagged module directory": (
        {
            "src/lib.rs": "mod cache;\nmod b;\n",
            "src/cache/CACHEDIR.TAG": TAG,
            "src/cache/mod.rs": "mod planted;\n",
            "src/cache/planted.rs": USE_B,
        },
        "native.app.cache.planted",
    ),
    "an include of a generated file in the build output": (
        {
            "src/lib.rs": 'mod b;\ninclude!(concat!(env!("OUT_DIR"), "/generated.rs"));\n',
            "target/CACHEDIR.TAG": TAG,
            "target/debug/build/app/out/generated.rs": USE_B,
        },
        "native.app",
    ),
}
# Build output that no source file names: the control. The same fixture must be able to pass.
OUTPUT = {
    "src/lib.rs": "mod b;\n",
    "target/CACHEDIR.TAG": TAG,
    "target/debug/app.d": "src/lib.rs:\n",
    "target/debug/build/app/out/generated.rs": USE_B,
}


def _validate(
    tmp_path: Path, core_binary: Path, files: dict[str, str], source: str
) -> dict[str, Any]:
    sources = {f"crates/app/{name}": text for name, text in files.items()}
    sources["crates/app/src/b.rs"] = "pub fn make() {}\n"
    forbidden = rule(
        "NO-PLANT-TO-B",
        "forbidden_dependency",
        source=source,
        target="native.app.b",
        include_type_checking=True,
    )
    rules = (*CRATE_RULES, forbidden)
    return validate(repository(tmp_path, core_binary, sources, rules=rules))


@pytest.mark.parametrize(("files", "source"), PLANTS.values(), ids=PLANTS.keys())
def test_a_rust_source_below_a_cache_name_is_not_dropped_without_a_named_gap(
    tmp_path: Path, core_binary: Path, files: dict[str, str], source: str
) -> None:
    result = _validate(tmp_path, core_binary, files, source)

    status = statuses(result).get("NO-PLANT-TO-B")
    assert status != "PASS", claims(result)
    assert (result["status"], result["exit_code"]) in {("FAIL", 1), ("UNKNOWN", 2)}, claims(result)
    if status != "FAIL":
        # The run did not prove the edge, so it must say what it did not read.
        named = [gap["reason"] for gap in result["gaps"]]
        named += [gap["reason"] for gap in result.get("frame", {}).get("collection_gaps", ())]
        assert named and all(named), claims(result)


def test_build_output_that_no_source_names_does_not_change_a_pass(
    tmp_path: Path, core_binary: Path
) -> None:
    # Without this control, a fixture that can never pass would make the plant tests empty.
    result = _validate(tmp_path, core_binary, OUTPUT, "native.app")

    assert (result["status"], result["exit_code"]) == ("PASS", 0), claims(result)
    assert set(statuses(result).values()) == {"PASS"}
    assert not result["gaps"]


def _component(name: str) -> dict[str, Any]:
    return {
        "id": f"COMP-{name.upper()}",
        "label": name,
        "role": "component",
        "packages": [f"app.src.{name}"],
        "public": [f"app.src.{name}"],
        "responsibilities": [f"Hold {name}."],
        "forbidden_responsibilities": [],
        "provenance": ["README.md"],
        "requires": [],
        "decided_by": "architect",
    }


TYPESCRIPT = {
    "tsconfig.json": '{"compilerOptions":{"allowJs":true},"include":["src"]}',
    "archkeel.toml": (
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    ),
    "architecture-contract.json": json.dumps(
        {
            "schema_version": "2.2.0",
            "components": [_component("a"), _component("b")],
            "rules": [
                {
                    "id": "REQUIRES",
                    "kind": "complete_requires",
                    "rationale": "a uses nothing.",
                    "provenance": ["README.md"],
                    "decided_by": "architect",
                }
            ],
        }
    ),
    "README.md": "# probe\n",
    "src/b/t.ts": "export type T = number;\n",
    "src/a/dist/CACHEDIR.TAG": TAG,
    "src/a/dist/planted.ts": 'import type { T } from "../../b/t";\nexport const x: T = 1;\n',
}


def test_a_typescript_source_below_a_tagged_directory_is_still_decided(
    tmp_path: Path, core_binary: Path
) -> None:
    for name, text in TYPESCRIPT.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(tmp_path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core_binary)
        code, document = run("validate", "--root", str(tmp_path))

    assert document["frame"]["rules"]["REQUIRES"][1] == "FAIL", document
    assert (code, document["status"]) == (1, "FAIL")
