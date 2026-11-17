# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Layout shapes of real projects that `init` must draft without a fault.

Each plant is the smallest form of a shape that a public project has (the project is named).
"""

import json
import re
from pathlib import Path

from archkeel.cli.init_draft import draft

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
