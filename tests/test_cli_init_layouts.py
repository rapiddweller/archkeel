# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Layout shapes of real projects that `init` must draft without a fault.

Each plant is the smallest form of a shape that a public project has (the project is named).
"""

import json
import re
from pathlib import Path

import pytest
from test_cli_native_python_imports import RULE, rows, verdict

from archkeel.cli.init_draft import draft, write_missing
from archkeel.cli.native_scan import prepare_disposable_git

CRATE = '[package]\nname = "{}"\nversion = "0.1.0"\nedition = "2021"\n'


def _write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_a_member_workspace_of_its_own_folder_is_no_fault(tmp_path: Path) -> None:
    """tokio 1.48.0: `tokio/fuzz/Cargo.toml` is a workspace with `members = ["."]`."""
    root = _write(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = [\n  "core",\n\n  # Internal\n  "util",\n]\n',
            "core/Cargo.toml": CRATE.format("core-a"),
            "core/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
            "core/fuzz/Cargo.toml": CRATE.format("core-fuzz") + '\n[workspace]\nmembers = ["."]\n',
            "core/fuzz/src/main.rs": "fn main() {}\n",
            "util/Cargo.toml": CRATE.format("util"),
            "util/src/lib.rs": "pub fn two() -> i32 { 2 }\n",
        },
    )
    result = draft(root)
    assert result.language == "rust"
    # The scan reads the fuzz crate too, so it gets a component of its own (see below).
    assert result.components == ("core_a", "util", "core_fuzz")


def test_a_workspace_draft_leaves_test_sources_out_as_a_crate_draft_does(tmp_path: Path) -> None:
    """tokio 1.48.0, serde 1.0.228: a proc-macro crate tests itself through the main crate (a
    `[dev-dependencies]` edge back). A draft that scans test sources fails its first run with a
    cycle that only tests close (#1680)."""
    root = _write(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = ["main", "derive"]\n',
            "main/Cargo.toml": CRATE.format("main")
            + '[dependencies]\nderive = { path = "../derive" }\n',
            "main/src/lib.rs": "pub use derive::*;\n",
            "derive/Cargo.toml": CRATE.format("derive")
            + '[dev-dependencies]\nmain = { path = "../main" }\n',
            "derive/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
        },
    )
    config = next(file for file in draft(root).files if file.path == "archkeel.toml")
    assert "exclude_test_sources = true" in config.text


def test_a_workspace_draft_owns_each_crate_that_the_scan_reads(tmp_path: Path) -> None:
    """tokio 1.48.0 (`tokio/fuzz` is its own workspace) and serde 1.0.228 (`test_suite/no_std`
    is not a member): the scan reads every crate below the root, so a crate that `members` does
    not name had no owner, and the first run failed with `module has no unique owner`."""
    root = _write(
        tmp_path,
        {
            "Cargo.toml": '[workspace]\nmembers = ["core", "util"]\nexclude = ["suite/no_std"]\n',
            "core/Cargo.toml": CRATE.format("core-a"),
            "core/src/lib.rs": "pub fn one() -> i32 { 1 }\n",
            "core/fuzz/Cargo.toml": CRATE.format("core-fuzz") + '\n[workspace]\nmembers = ["."]\n',
            "core/fuzz/src/main.rs": "fn main() {}\n",
            "util/Cargo.toml": CRATE.format("util"),
            "util/src/lib.rs": "pub fn two() -> i32 { 2 }\n",
            "suite/no_std/Cargo.toml": CRATE.format("suite-no-std"),
            "suite/no_std/src/main.rs": "fn main() {}\n",
            "target/debug/build/x/Cargo.toml": CRATE.format("generated"),
        },
    )
    result = draft(root)
    assert result.components == ("core_a", "util", "core_fuzz", "suite_no_std")
    contract = next(f for f in result.files if f.path == "architecture-contract.json")
    assert f'"{result.namespace}.core_fuzz"' in contract.text


def test_a_workspace_without_a_root_tsconfig_drafts_each_member_with_its_own(
    tmp_path: Path,
) -> None:
    """fastapi/full-stack-fastapi-template 0.12.0: the root package.json names the workspaces and
    has no tsconfig.json; each member has its own. One scan of both members named a root
    tsconfig.json that does not exist, so the first run was refused."""
    member = {"compilerOptions": {"strict": True}, "include": ["src"]}
    root = _write(
        tmp_path,
        {
            "package.json": json.dumps({"name": "mono", "workspaces": ["web", "packages/*"]}),
            "web/package.json": '{"name": "web"}',
            "web/tsconfig.json": json.dumps(member),
            "web/src/index.ts": "export const a = 1;\n",
            "packages/mail/package.json": '{"name": "mail"}',
            "packages/mail/tsconfig.json": json.dumps(member),
            "packages/mail/src/index.ts": "export const b = 2;\n",
        },
    )
    result = draft(root)
    configs = {file.path: file.text for file in result.files if file.path.endswith(".toml")}
    assert result.parts == ("TypeScript web", "TypeScript mail"), result.parts
    for path, text in configs.items():
        named = re.search(r'^tsconfig = "([^"]+)"$', text, re.M)
        assert named and (root / named[1]).is_file(), (path, text)


def test_a_folder_of_another_part_with_only_a_test_sample_is_no_python_component(
    tmp_path: Path,
) -> None:
    """#1619: `src/` holds Python packages and a TypeScript project `src/web` whose only Python
    file is a test sample under `tests/data`. The Python draft made a component `web` for it."""
    member = {"compilerOptions": {"strict": True}, "include": ["src"]}
    root = _write(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "p"\nversion = "0"\nrequires-python = ">=3.11"\n',
            "src/alpha/__init__.py": "",
            "src/alpha/a.py": "from beta import b\n",
            "src/alpha/test_alpha.py": "",
            "src/beta/__init__.py": "",
            "src/beta/b.py": "b = 1\n",
            "src/web/package.json": '{"name": "web"}',
            "src/web/tsconfig.json": json.dumps(member),
            "src/web/src/index.ts": "export const a = 1;\n",
            "src/web/tests/data/test_upload.scr.py": "print(1)\n",
        },
    )
    result = draft(root)
    assert result.parts == ("Python src", "TypeScript web")
    # The Python part has a component for each package and none for the folder `web`; the test
    # file of `alpha` and the sample are no modules of its scan.
    assert result.components == ("src/alpha", "src/beta", "web/root")
    python = next(f for f in result.files if f.path.endswith("src/archkeel.toml"))
    assert "exclude_test_sources = true" in python.text


def test_a_typescript_project_below_the_root_does_not_repeat_its_path_in_its_names(
    tmp_path: Path,
) -> None:
    """#1617: a TypeScript project at `src/web` drafted the namespace `web`, so each module read
    `web.src.web.src.application`. The namespace is the repository's."""
    member = {"compilerOptions": {"strict": True}, "include": ["src"]}
    root = _write(
        tmp_path / "mono",
        {
            "src/web/package.json": '{"name": "web"}',
            "src/web/tsconfig.json": json.dumps(member),
            "src/web/src/application/main.ts": "export const a = 1;\n",
            "src/web/src/domain/rule.ts": "export const b = 2;\n",
        },
    )
    result = draft(root)
    assert result.namespace == "mono"
    contract = next(f for f in result.files if f.path.endswith("architecture-contract.json"))
    assert '"mono.src.web.src.application"' in contract.text
    assert "web.src.web" not in contract.text


def test_a_typescript_root_project_drafts_only_folders_that_its_tsconfig_selects(
    tmp_path: Path,
) -> None:
    """#1710, graphql-js 16.15.0: the root tsconfig includes `src/**/*`. The draft also made the
    components `benchmark`, `resources` and `website`, and `website` is a project of its own."""
    root = _write(
        tmp_path / "graphql",
        {
            "package.json": '{"name": "graphql"}',
            "tsconfig.json": '{\n  // the library\n  "include": ["src/**/*"],\n}\n',
            "src/error/GraphQLError.ts": "export const e = 1;\n",
            "src/language/parser.ts": "export const p = 2;\n",
            "src/__tests__/starWars.ts": "export const s = 3;\n",
            "src/index.ts": "export * from './error/GraphQLError';\n",
            "benchmark/run.js": "module.exports = 1;\n",
            "resources/build.ts": "export const b = 4;\n",
            "website/package.json": '{"name": "site"}',
            "website/tsconfig.json": '{"include": ["pages"]}',
            "website/pages/index.tsx": "export const i = 5;\n",
        },
    )
    result = draft(root)
    assert result.parts == ("TypeScript graphql", "TypeScript website"), result.parts
    assert [c for c in result.components if c.startswith("graphql/")] == [
        "graphql/error",
        "graphql/language",
        "graphql/root",
    ], result.components


def test_the_part_at_the_root_is_named_after_the_project_and_not_its_language(
    tmp_path: Path,
) -> None:
    """#1709, graphql-js 16.15.0: the main project at the repository root became the part
    `typescript`; the part takes the name of the project (its namespace) instead."""
    member = {"compilerOptions": {"strict": True}, "include": ["pages"]}
    root = _write(
        tmp_path / "graphql-js",
        {
            "package.json": '{"name": "graphql"}',
            "tsconfig.json": '{"include": ["src"]}',
            "src/error/GraphQLError.ts": "export const e = 1;\n",
            "website/package.json": '{"name": "site"}',
            "website/tsconfig.json": json.dumps(member),
            "website/pages/index.tsx": "export const i = 5;\n",
        },
    )
    result = draft(root)
    assert result.parts == ("TypeScript graphql_js", "TypeScript website"), result.parts
    assert "graphql_js/error" in result.components, result.components


def test_python_declared_import_root_names_sibling_packages(tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": (
                '[tool.setuptools]\npackages.find.where = [ # "decoy"\n "backend", "backend/"\n]\n'
            ),
            "backend/shared/__init__.py": "",
            "backend/shared/helper.py": "value = 1\n",
            "backend/worker/__init__.py": "",
            "backend/worker/task.py": "from shared import helper\n",
        },
    )
    result = draft(root)
    config = next(file.text for file in result.files if file.path.endswith("archkeel.toml"))
    contract = next(
        file.text for file in result.files if file.path.endswith("architecture-contract.json")
    )
    assert 'roots = ["backend"]' in config
    assert 'namespace = ""' in config
    assert '"shared"' in contract and '"worker"' in contract
    assert '"backend.shared"' not in contract


def test_pytest_path_does_not_erase_a_real_src_package(release_core: Path, tmp_path: Path) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nrequires-python = ">=3.11"\n'
                '[tool.pytest.ini_options]\npythonpath = ["src"]\n'
            ),
            "src/__init__.py": "",
            "src/shared/__init__.py": "",
            "src/shared/helper.py": "value = 1\n",
            "src/worker/__init__.py": "",
            "src/worker/task.py": "from src.shared import helper\nimport shared.helper\n",
        },
    )
    result = draft(root)
    config = next(file.text for file in result.files if file.path.endswith("archkeel.toml"))
    assert 'namespace = "src"' in config
    write_missing(root, result)
    prepare_disposable_git(root)
    topology = verdict(release_core, root, "report", "--topology")["frame"]["topology"]
    assert {(edge["source"], edge["target"], edge["resolution"]) for edge in topology["edges"]} == {
        ("src.worker.task", "src.shared.helper", "resolved"),
        ("src.worker.task", "shared.helper", "external"),
    }


def test_conflicting_python_import_roots_keep_inventory_and_withhold_edges(
    release_core: Path, tmp_path: Path
) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nrequires-python = ">=3.11"\n'
                '[tool.setuptools]\npackage-dir = {"" = "one"}\n'
                'packages.find.where = ["two"]\n'
            ),
            "one/worker/__init__.py": "",
            "one/worker/task.py": "from shared import helper\n",
            "two/shared/__init__.py": "",
            "two/shared/helper.py": "value = 1\n",
        },
    )
    generated = draft(root)
    write_missing(root, generated)
    prepare_disposable_git(root)
    result = verdict(release_core, root, "report", "--topology")
    frame = result["frame"]
    assert result["status"] == "UNKNOWN", result
    assert "ambiguous_import_roots" in json.dumps(frame["collection_gaps"])
    topology = frame["topology"]
    assert {"worker.task", "shared.helper"} <= {module["name"] for module in topology["modules"]}
    assert [(edge["target"], edge["resolution"]) for edge in topology["edges"]] == [
        ("shared.helper", "unresolved")
    ]


@pytest.mark.parametrize(
    "options",
    [
        'where = ["library"]\ninclude = ["entry*"]',
        'where = ["library"]\nexclude = ["client"]',
        'where = ["library", "library/vendor"]',
    ],
)
def test_restricted_or_overlapping_distribution_keeps_inventory(
    tmp_path: Path, options: str
) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": "[tool.setuptools.packages.find]\n" + options,
            "library/entry/__init__.py": "import client\n",
            "library/client/__init__.py": "",
            "library/vendor/helper.py": "",
        },
    )
    result = draft(root)
    config = next(file.text for file in result.files if file.path.endswith("archkeel.toml"))
    assert 'roots = ["library"]' in config
    assert "import_roots_ambiguous = true" in config


def test_source_roots_enforce_a_forbidden_sibling_import(
    release_core: Path, tmp_path: Path
) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nrequires-python = ">=3.11"\n'
                '[tool.setuptools.packages.find]\nwhere = ["backend"]\n'
            ),
            "backend/worker/__init__.py": "",
            "backend/worker/task.py": "from shared import helper\nimport requests\n",
            "backend/shared/__init__.py": "",
            "backend/shared/helper.py": "",
        },
    )
    write_missing(root, draft(root))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["rules"] = [
        {
            **RULE,
            "provenance": ["docs/architecture/architecture.md"],
            "id": "FORBID",
            "kind": "forbidden_dependency",
            "source": "worker",
            "target": "shared",
            "include_type_checking": True,
        },
        {
            **RULE,
            "provenance": ["docs/architecture/architecture.md"],
            "id": "EXTERNAL",
            "kind": "complete_external_scope",
            "source": "worker",
        },
    ]
    path.write_text(json.dumps(contract), encoding="utf-8")
    prepare_disposable_git(root)
    result = verdict(release_core, root)
    assert rows(result) == {"FORBID": "FAIL", "EXTERNAL": "FAIL"}, result


@pytest.mark.parametrize(
    ("base", "manifest", "resolution"),
    [
        (".", "", "resolved"),
        ("backend", '[tool.setuptools.package-data]\n"root" = ["*.json"]\n', "resolved"),
        ("backend", "", "unresolved"),
    ],
)
def test_python_peer_packages_without_an_explicit_where(
    release_core: Path, tmp_path: Path, base: str, manifest: str, resolution: str
) -> None:
    root = _write(
        tmp_path,
        {
            "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n' + manifest,
            f"{base}/worker/__init__.py": "",
            f"{base}/worker/task.py": "from root import helper\n",
            f"{base}/root/__init__.py": "",
            f"{base}/root/helper.py": "",
            f"{base}/loose.py": "",
            "src/frontend.ts": "",
        },
    )
    generated = draft(root)
    assert generated.components == ("root", "worker", "modules"), generated.components
    write_missing(root, generated)
    prepare_disposable_git(root)
    result = verdict(release_core, root, "report", "--topology")
    topology = result["frame"]["topology"]
    assert {"worker.task", "root.helper", "loose"} <= {
        module["name"] for module in topology["modules"]
    }
    assert [(edge["target"], edge["resolution"]) for edge in topology["edges"]] == [
        ("root.helper", resolution)
    ]
    if resolution == "unresolved":
        assert "available files do not establish" in json.dumps(result["frame"]["collection_gaps"])
