# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-660: a mixed repository gets a system draft, one part for each language area.

The plant has a Python package, a TypeScript project, a Dart package and a Cargo workspace. No
source is read to draft it; the core then runs the system and the report draws it.
"""

import json
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.init_draft import SYSTEM
from tests.test_cli_auto_init import commit, write

CRATE = '[package]\nname = "{}"\nversion = "0.1.0"\nedition = "2021"\n'
FILES = {
    "pyproject.toml": '[project]\nname = "shop"\nversion = "0"\nrequires-python = ">=3.11"\n',
    "src/shop/__init__.py": "",
    "src/shop/orders/__init__.py": "",
    "src/shop/orders/service.py": "def place(): return 1\n",
    "src/shop/billing/__init__.py": "",
    "src/shop/billing/pay.py": "from shop.orders import service\n",
    "src/shop/openapi.json": '{"openapi": "3.0.0"}',
    "web/package.json": '{"name": "web", "version": "1.0.0"}',
    "web/tsconfig.json": '{"compilerOptions": {"strict": true, "noEmit": true, '
    '"module": "CommonJS", "moduleResolution": "Node"}, "include": ["src/**/*.ts"]}',
    "web/src/index.ts": 'import { a } from "./api/client";\nexport const w = a;\n',
    "web/src/api/client.ts": "export const a = 1;\n",
    "web/src/ui/page.ts": 'import { a } from "../api/client";\nexport const p = a;\n',
    "mobile/pubspec.yaml": "name: shop_mobile\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n",
    "mobile/lib/main.dart": "void main() {}\n",
    "mobile/lib/data/repo.dart": "class Repo {}\n",
    "mobile/lib/ui/page.dart": "class Page {}\n",
    "engine/Cargo.toml": '[workspace]\nmembers = ["crates/core-a", "crates/util"]\n',
    "engine/crates/core-a/Cargo.toml": CRATE.format("core-a"),
    "engine/crates/core-a/src/lib.rs": "pub fn run() {}\n",
    "engine/crates/util/Cargo.toml": CRATE.format("util"),
    "engine/crates/util/src/lib.rs": "pub fn one() {}\n",
    ".gitignore": "target\nnode_modules\n",
}


# The Python area of the repository root first, then the folders in alphabetical order.
PARTS = ["Python shop", "Rust engine", "Dart mobile", "TypeScript web"]
IDS = ["shop", "engine", "mobile", "web"]


def mixed(root: Path) -> Path:
    return commit(write(root, FILES))


def run(
    capsys: pytest.CaptureFixture[str], root: Path, *argv: str
) -> tuple[int, dict[str, object]]:
    code = core_only.run([*argv, "--root", str(root), "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_init_drafts_one_part_for_each_language_area(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mixed(tmp_path)
    code, document = run(capsys, root, "init")
    assert code == 0 and document["parts"] == PARTS
    system = json.loads((root / SYSTEM).read_text(encoding="utf-8"))
    assert [part["id"] for part in system["parts"]] == IDS
    assert all("TODO" in line for part in system["parts"] for line in part["responsibilities"])
    for part in system["parts"]:
        config = root / part["config"]
        assert config.is_file() and (config.parent / "architecture-contract.json").is_file()
        assert (config.parent / "architecture.md").is_file()
    # A spec file of the Python area is the one crossing that the manifests can name; each other
    # part is a candidate caller, and every one is open until the user confirms it.
    assert {(i["source"], i["target"]) for i in system["interfaces"]} == {
        ("web", "shop"),
        ("mobile", "shop"),
        ("engine", "shop"),
    }
    assert all(i["title"].startswith("TODO") for i in system["interfaces"])


def test_the_default_run_finds_the_system_and_the_report_draws_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mixed(tmp_path)
    code, document = run(capsys, root, "validate")
    # The block comes from the auto-init and the run is the system run, not a refusal.
    init = document["init"]
    assert isinstance(init, dict) and init["parts"] == PARTS
    frame = document["frame"]
    assert isinstance(frame, dict) and "refusal" not in document and code == 2
    assert [p["id"] for p in frame["system"]["parts"]] == IDS
    assert not frame["violations"], frame["violations"]
    # The second run takes the system document by itself, with no new block.
    code, again = run(capsys, root, "validate")
    assert "init" not in again and again["status"] == "UNKNOWN"
    page = tmp_path / "page.html"
    code = core_only.run(["report", "--root", str(root), "--output", str(page), "--text"])
    assert code == 2 and "shop" in page.read_text(encoding="utf-8")


def test_a_repository_with_a_configuration_keeps_it_and_gets_the_system_beside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mixed(tmp_path)
    own = 'scan_is_mine = "yes"\n'
    (root / "archkeel.toml").write_text(own, encoding="utf-8")
    code, _ = run(capsys, root, "init")
    assert code == 0 and (root / SYSTEM).is_file()
    assert (root / "archkeel.toml").read_text(encoding="utf-8") == own
    code, text = (core_only.run(["init", "--root", str(root)]), capsys.readouterr().out)
    assert code == 2 and "exist" in text


def test_no_init_writes_nothing_for_a_mixed_repository_and_names_the_parts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = mixed(tmp_path)
    code = core_only.run(["validate", "--root", str(root), "--text", "--no-init"])
    text = capsys.readouterr().out
    assert code == 2 and not (root / "docs").exists()
    assert "a system of 4 parts" in text and "Rust engine" in text


def test_a_json_import_does_not_stop_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A resolved import of a file that is no module of the list (here JSON) is an external edge:
    the topology check of the shell refused the whole report for it before AD-660."""
    root = commit(
        write(
            tmp_path,
            {
                "package.json": '{"name": "app", "version": "1.0.0"}',
                "tsconfig.json": '{"compilerOptions": {"strict": true, "noEmit": true, '
                '"module": "CommonJS", "moduleResolution": "Node", "resolveJsonModule": true}}',
                "src/ui/page.ts": 'import data from "../data.json";\nexport const d = data;\n',
                "src/data.json": '{"a": 1}',
                "src/index.ts": "export const i = 1;\n",
            },
        )
    )
    page = tmp_path / "page.html"
    code = core_only.run(["report", "--root", str(root), "--output", str(page), "--text"])
    out = capsys.readouterr().out
    assert code == 2 and page.is_file() and "REFUSED" not in out, out


def test_the_source_suffixes_have_one_owner_that_the_shell_and_the_core_read() -> None:
    """The table of source suffixes is the file `schema/archkeel-source-suffixes.txt`: the contract
    crate embeds it and the shell reads it. A second table in code fails `test_table_overlap.py`."""
    from archkeel.cli.init_areas import _code_suffixes

    rows = [
        line.split(" ", 1)
        for line in (Path(__file__).parents[1] / "schema/archkeel-source-suffixes.txt")
        .read_text()
        .splitlines()
    ]
    assert {language for language, _ in rows} == {"python", "dart", "typescript"}
    assert _code_suffixes() == {suffix for language, suffix in rows if language == "typescript"}
    assert ".ts" in _code_suffixes() and ".py" not in _code_suffixes()
