# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A source file that the TSConfig drops under the scan roots is a coverage gap (AD-488).

Each plant starts from a TypeScript project that gives PASS. It adds `src/b/<file>`, which imports
component A. Component B does not require A, so the import breaks `complete_requires`. The
TSConfig drops the file. Release 4.0.1 and the core before AD-488 gave PASS, because the
collector never saw the file. Now the run is UNKNOWN and the gap names the file. The controls
show what is not project source: they keep their verdict.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, case_root, run

from archkeel.cli import core_only

REASON = "Source file under the scan roots is not selected by the TSConfig: "
IMPORT = "import { a } from '../a/a';\nexport const hidden = a;\n"
DECLARATION = "import type { a } from '../a/a';\nexport declare const h: typeof a;\n"
REQUIRE = "require('../a/a');\n"
IMPORT2 = "import { a } from '../../a/a';\nexport const e = a;\n"
IMPORT3 = "import { a } from '../../../a/a';\nexport const hidden = a;\n"
# The scan of the whole repository: the walk meets the linked output directory before `src`.
ROOT_TOML = (
    '[scan]\nlanguage = "typescript"\nroots = ["."]\nnamespace = "app"\n'
    'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
)
# A file value that starts with this marker is a symbolic link to the rest of the value.
LINK = "-> "
Files = dict[str, str]


@pytest.fixture(autouse=True)
def release(release_core: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)


def _tsconfig(value: dict[str, Any]) -> str:
    return json.dumps(value)


def _validate(files: Files, toml: str = "") -> tuple[int, dict[str, Any]]:
    with _project(files, toml) as root:
        return run("validate", "--root", str(root))


def _commit(root: Path) -> None:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    for command in (["add", "-A"], ["commit", "-q", "--allow-empty", "-m", "plant"]):
        subprocess.run([*git, *command], cwd=root, check=True, capture_output=True)


class _project:
    def __init__(self, files: Files, toml: str) -> None:
        self.files, self.toml = files, toml

    def __enter__(self) -> Path:
        self.context = case_root(HONEST)
        root = self.context.__enter__()
        for name, text in self.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if text.startswith(LINK):
                path.symlink_to(text[len(LINK) :])
            else:
                path.write_text(text, encoding="utf-8")
        if self.toml:
            config = root / "archkeel.toml"
            config.write_text(config.read_text(encoding="utf-8") + self.toml, encoding="utf-8")
        _commit(root)
        return root

    def __exit__(self, *details: object) -> None:
        self.context.__exit__(*details)


def _gaps(envelope: dict[str, Any]) -> list[str]:
    gaps = envelope["frame"].get("collection_gaps", [])
    return sorted(g["reason"][len(REASON) :] for g in gaps if g["reason"].startswith(REASON))


def _passes(envelope: dict[str, Any]) -> list[str]:
    return sorted(rule for rule, row in envelope["frame"]["rules"].items() if row[1] == "PASS")


SRC = {"include": ["src"]}
DROPPED: dict[str, tuple[Files, str]] = {
    "exclude": (
        {
            "tsconfig.json": _tsconfig({**SRC, "exclude": ["src/b/hidden.ts"]}),
            "src/b/hidden.ts": IMPORT,
        },
        "src/b/hidden.ts",
    ),
    "include": (
        {
            "tsconfig.json": _tsconfig({"include": ["src/a", "src/b/t.ts"]}),
            "src/b/hidden.ts": IMPORT,
        },
        "src/b/hidden.ts",
    ),
    "files": (
        {
            "tsconfig.json": _tsconfig({"files": ["src/a/a.ts", "src/b/t.ts"]}),
            "src/b/hidden.ts": IMPORT,
        },
        "src/b/hidden.ts",
    ),
    "extends": (
        {
            "tsconfig.json": _tsconfig({"extends": "./base.json"}),
            "base.json": _tsconfig({**SRC, "exclude": ["src/b/hidden.ts"]}),
            "src/b/hidden.ts": IMPORT,
        },
        "src/b/hidden.ts",
    ),
    "test-pattern": (
        {
            "tsconfig.json": _tsconfig({**SRC, "exclude": ["**/*.test.ts"]}),
            "src/b/hidden.test.ts": IMPORT,
        },
        "src/b/hidden.test.ts",
    ),
    "declaration": (
        {
            "tsconfig.json": _tsconfig({**SRC, "exclude": ["**/*.d.ts"]}),
            "src/b/hidden.d.ts": DECLARATION,
        },
        "src/b/hidden.d.ts",
    ),
    "javascript-without-allow-js": (
        {
            "tsconfig.json": _tsconfig({"compilerOptions": {"allowJs": False}, **SRC}),
            "src/b/hidden.js": IMPORT,
        },
        "src/b/hidden.js",
    ),
    "dot-directory": (
        {"tsconfig.json": _tsconfig(SRC), "src/b/.hidden/x.ts": "import { a } from '../../a/a';\n"},
        "src/b/.hidden/x.ts",
    ),
}


def test_the_project_without_a_plant_passes() -> None:
    code, envelope = _validate({})
    assert (code, envelope["status"]) == (0, "PASS"), envelope
    assert _gaps(envelope) == []


@pytest.mark.parametrize("form", sorted(DROPPED))
def test_a_source_file_that_the_tsconfig_drops_is_a_named_gap_and_no_rule_passes(form: str) -> None:
    files, dropped = DROPPED[form]
    code, envelope = _validate(files)
    assert _gaps(envelope) == [dropped]
    assert _passes(envelope) == []
    assert envelope["frame"]["scope"].startswith("incomplete scope")
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def test_project_references_stay_a_named_gap() -> None:
    files = {"tsconfig.json": _tsconfig({**SRC, "references": [{"path": "./other"}]})}
    code, envelope = _validate(files)
    reasons = [g["reason"] for g in envelope["frame"]["collection_gaps"]]
    assert "Project references require separately observed projects" in reasons
    assert _passes(envelope) == []
    assert (code, envelope["status"]) == (2, "UNKNOWN")


def _options(options: dict[str, Any], **rest: Any) -> str:
    return _tsconfig({"compilerOptions": options, **SRC, **rest})


# The findings of the proof review of #1160. Each file imports component A from component B.
# Release 4.0.1 and the first head of #1160 gave PASS for each; now each is a named gap.
REVIEW: dict[str, tuple[Files, list[str]]] = {
    # B1: a name beside a source does not prove emitted output.
    "B1-tsx-beside-ts": ({"src/b/t.tsx": IMPORT}, ["src/b/t.tsx"]),
    "B1-jsx-beside-ts": ({"src/b/t.jsx": IMPORT}, ["src/b/t.jsx"]),
    "B1-dts-beside-ts": ({"src/b/t.d.ts": DECLARATION}, ["src/b/t.d.ts"]),
    "B1-jsx-beside-js": (
        {"src/b/u.js": "export const u = 1;\n", "src/b/u.jsx": IMPORT},
        ["src/b/u.jsx"],
    ),
    "B1-mjs-beside-mts": (
        {"src/b/u.mts": "export const u = 1;\n", "src/b/u.mjs": IMPORT},
        ["src/b/u.mjs"],
    ),
    "B1-cjs-beside-cts": (
        {"src/b/u.cts": "export const u = 1;\n", "src/b/u.cjs": REQUIRE},
        ["src/b/u.cjs"],
    ),
    "B1-dmts-beside-mts": (
        {"src/b/u.mts": "export const u = 1;\n", "src/b/u.d.mts": DECLARATION},
        ["src/b/u.d.mts"],
    ),
    "B1-js-beside-ts-with-out-dir": (
        {"tsconfig.json": _options({"outDir": "dist"}), "src/b/t.js": REQUIRE},
        ["src/b/t.js"],
    ),
    "B1-js-beside-ts-without-emit": (
        {"tsconfig.json": _options({"noEmit": True}), "src/b/t.js": REQUIRE},
        ["src/b/t.js"],
    ),
    # B2: a build output directory can hold written code, and `noEmit` writes nothing.
    "B2-ts-in-out-dir": (
        {"tsconfig.json": _options({"outDir": "src/b/out"}), "src/b/out/evil.ts": IMPORT2},
        ["src/b/out/evil.ts"],
    ),
    "B2-out-dir-through-extends": (
        {
            "tsconfig.json": _tsconfig({"extends": "./base.json", **SRC}),
            "base.json": _tsconfig({"compilerOptions": {"outDir": "src/b/gen"}}),
            "src/b/gen/evil.ts": IMPORT2,
        },
        ["src/b/gen/evil.ts"],
    ),
    "B2-out-dir-from-config-dir": (
        {
            "tsconfig.json": _options({"outDir": "${configDir}/src/b/gen"}),
            "src/b/gen/evil.ts": IMPORT2,
        },
        ["src/b/gen/evil.ts"],
    ),
    "B2-written-declaration-in-declaration-dir": (
        {
            "tsconfig.json": _options({"declaration": True, "declarationDir": "src/b/types"}),
            "src/b/types/evil.d.ts": DECLARATION.replace("'../a/a'", "'../../a/a'"),
        },
        ["src/b/types/evil.d.ts"],
    ),
    "B2-js-in-out-dir-without-emit": (
        {
            "tsconfig.json": _options({"outDir": "src/b/out", "noEmit": True}),
            "src/b/out/evil.js": "require('../../a/a');\n",
        },
        ["src/b/out/evil.js"],
    ),
    # L-61: an output directory that links to excluded source.
    "L61-linked-out-dir": (
        {
            "archkeel.toml": ROOT_TOML,
            "tsconfig.json": _options({"outDir": "zout"}, exclude=["src/b/legacy"]),
            "src/b/legacy/evil.ts": IMPORT2,
            "zout": LINK + "src/b/legacy",
        },
        ["zout/evil.ts"],
    ),
    # B3: an installed-package directory without its manifest, or that the project uses.
    "B3-selected-by-include": (
        {
            "tsconfig.json": _tsconfig(
                {"include": ["src", "src/b/node_modules/local"], "exclude": []}
            ),
            "src/b/node_modules/local/index.ts": IMPORT3,
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-bare-import": (
        {
            "src/b/node_modules/local/index.ts": IMPORT3,
            "src/b/t.ts": "import { hidden } from 'local';\nexport const t = hidden;\n",
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-paths-alias": (
        {
            "tsconfig.json": _options(
                {"baseUrl": ".", "paths": {"@local/*": ["src/b/node_modules/local/*"]}}
            ),
            "src/b/node_modules/local/index.ts": IMPORT3,
            "src/b/t.ts": "import { hidden } from '@local/index';\nexport const t = hidden;\n",
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-paths-alias-beside-manifest": (
        {
            "tsconfig.json": _options(
                {"baseUrl": ".", "paths": {"@local/*": ["src/b/node_modules/local/*"]}}
            ),
            "src/b/package.json": "{}",
            "src/b/node_modules/local/index.ts": IMPORT3,
            "src/b/t.ts": "import { hidden } from '@local/index';\nexport const t = hidden;\n",
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-base-url-beside-manifest": (
        {
            "tsconfig.json": _options({"baseUrl": "src/b/node_modules"}),
            "src/b/package.json": "{}",
            "src/b/node_modules/local/index.ts": IMPORT3,
            "src/b/t.ts": "import { hidden } from 'local/index';\nexport const t = hidden;\n",
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-unimported": (
        {"src/b/node_modules/local/index.ts": IMPORT3},
        ["src/b/node_modules/local/index.ts"],
    ),
    "B3-bower-components": (
        {"src/b/bower_components/evil.ts": IMPORT2},
        ["src/b/bower_components/evil.ts"],
    ),
    "B3-jspm-packages": (
        {"src/b/jspm_packages/evil.ts": IMPORT2},
        ["src/b/jspm_packages/evil.ts"],
    ),
    "B3-installed-beside-manifest-but-selected": (
        {
            "tsconfig.json": _tsconfig(
                {"include": ["src", "src/b/node_modules/local"], "exclude": []}
            ),
            "src/b/package.json": "{}",
            "src/b/node_modules/local/index.ts": IMPORT3,
        },
        ["src/b/node_modules/local/index.ts"],
    ),
    # The letter case of a suffix does not hide a source file.
    "upper-case-suffix": ({"src/b/evil.TS": IMPORT}, ["src/b/evil.TS"]),
}


@pytest.mark.parametrize("finding", sorted(REVIEW))
def test_each_review_finding_is_a_named_gap_and_no_rule_passes(finding: str) -> None:
    files, dropped = REVIEW[finding]
    code, envelope = _validate(files)
    assert _gaps(envelope) == dropped
    assert _passes(envelope) == []
    assert (code, envelope["status"]) == (2, "UNKNOWN")


CONTROLS: dict[str, tuple[Files, str]] = {
    # The package manager owns an installed directory beside its manifest; the project reaches
    # its code only as an external package.
    "installed-beside-manifest": (
        {"src/package.json": "{}", "src/node_modules/pkg/index.ts": IMPORT3},
        "",
    ),
    # The request removes test sources by name (AD-313): that is not a TSConfig drop.
    "request-removes-tests": (
        {
            "tsconfig.json": _tsconfig({**SRC, "exclude": ["**/*.test.ts"]}),
            "src/b/t.test.ts": IMPORT,
        },
        "exclude_test_sources = true\n",
    ),
}


@pytest.mark.parametrize("control", sorted(CONTROLS))
def test_a_file_that_is_not_project_source_is_no_gap(control: str) -> None:
    files, toml = CONTROLS[control]
    code, envelope = _validate(files, toml)
    assert _gaps(envelope) == []
    assert (code, envelope["status"]) == (0, "PASS"), envelope


def test_a_dropped_file_that_a_selected_file_imports_is_read_and_its_import_fails() -> None:
    files = {
        "tsconfig.json": _tsconfig({**SRC, "exclude": ["src/b/hidden.ts"]}),
        "src/b/hidden.ts": IMPORT,
        "src/b/t.ts": "import { hidden } from './hidden';\nexport const t = hidden;\n",
    }
    code, envelope = _validate(files)
    assert _gaps(envelope) == []
    assert envelope["frame"]["rules"]["REQUIRES"][1] == "FAIL"
    assert (code, envelope["status"]) == (1, "FAIL")
