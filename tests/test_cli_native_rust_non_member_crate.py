# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1047, #1989: a crate under the scan root that is no workspace member is foreign code.

`crates/vendor/erdep` is excluded from the workspace and is a path dependency of `app`.
The test runs `cargo run` as the oracle: the foreign function runs, and the scan must read no
module of it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rust_repository import component, repository, rule, validate

pytestmark = pytest.mark.skipif(
    shutil.which("cargo") is None or shutil.which("git") is None,
    reason="the scan needs cargo and git",
)

WORKSPACE = '[workspace]\nmembers = ["base", "app"]\nexclude = ["vendor/erdep"]\n'
APP = (
    '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n'
    '[dependencies]\nerdep = { path = "../vendor/erdep", package = "%s" }\n'
)
# Another version: Cargo refuses two path packages with one name and one version in a lock file.
FOREIGN = '[package]\nname = "%s"\nversion = "0.0.1"\nedition = "2021"\n'
APP_SOURCE = "pub fn run() { erdep::erase_any(1u8); }\n"
APP_MAIN = "fn main() { app::run(); }\n"
FOREIGN_SOURCE = (
    "pub fn erase_any<T: std::any::Any>(t: T) -> Box<dyn std::any::Any> {\n"
    '    println!("foreign code ran");\n    Box::new(t)\n}\n'
)


PARTS = (component("base", "base_crate"), component("app", "app"))


def _layout(name: str) -> dict[str, str]:
    return {
        "crates/Cargo.toml": WORKSPACE,
        "crates/app/Cargo.toml": APP % name,
        "crates/app/src/lib.rs": APP_SOURCE,
        "crates/app/src/main.rs": APP_MAIN,
        "crates/vendor/erdep/Cargo.toml": FOREIGN % name,
        "crates/vendor/erdep/src/lib.rs": FOREIGN_SOURCE,
    }


def _counter(root: Path) -> str:
    """What `cargo run` prints: the proof that the non-member crate runs."""
    done = subprocess.run(
        ["cargo", "run", "--offline", "-q", "--manifest-path", str(root / "crates/app/Cargo.toml")],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "CARGO_TARGET_DIR": str(root.parent / "target")},
    )
    assert done.returncode == 0, done.stderr
    return str(done.stdout)


def _reasons(result: dict[str, Any]) -> list[str]:
    return [gap["reason"] for gap in result["frame"]["collection_gaps"]]


def test_a_non_member_crate_is_no_module_of_the_workspace(
    tmp_path: Path, release_core: Path
) -> None:
    root = repository(tmp_path / "repo", release_core, files=_layout("other"), components=PARTS)
    assert _counter(root) == "foreign code ran\n"
    result = validate(root)
    assert result["outcome"] == "verdict", result["gaps"]
    rules = {name: row[1] for name, row in result["frame"]["rules"].items()}
    assert rules["ASSIGNED"] == "PASS" and rules["REQUIRES"] != "PASS", rules
    assert any("a crate that is no workspace member" in r for r in _reasons(result))
    # The workspace manifest, the two crates and their two sources: no file of `vendor`.
    assert result["frame"]["self_test"]["reply"]["files"] == 5


@pytest.mark.parametrize("name", ["base-crate", "base_crate"])
def test_a_non_member_crate_with_the_name_of_a_member_gives_a_named_gap(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    # The dependency `erdep` reads as the member `base-crate`.
    # That edge must not satisfy a declared requirement.
    parts = (component("base", "base_crate"), component("app", "app", ("base",)))
    root = repository(tmp_path / "repo", release_core, files=_layout(name), components=parts)
    assert _counter(root) == "foreign code ran\n"
    result = validate(root)
    assert result["outcome"] == "verdict", result["gaps"]
    assert any(f"has the package name {name} of a member" in r for r in _reasons(result))
    assert result["frame"]["rules"]["REQUIRES"][1] != "PASS"


def test_a_member_below_a_non_member_crate_stays_in_the_scan(
    tmp_path: Path, release_core: Path
) -> None:
    layout = _layout("other")
    layout["crates/Cargo.toml"] = (
        '[workspace]\nmembers = ["base", "app", "vendor/erdep/nested"]\n'
        'exclude = ["vendor/erdep"]\n'
    )
    layout["crates/vendor/erdep/nested/Cargo.toml"] = (
        '[package]\nname = "nested"\nversion = "0.0.0"\nedition = "2021"\n'
    )
    layout["crates/vendor/erdep/nested/src/lib.rs"] = "pub fn n() {}\n"
    root = repository(tmp_path / "repo", release_core, files=layout, components=PARTS)
    result = validate(root)
    assert result["outcome"] == "verdict", result["gaps"]
    # No component owns the nested member, so ASSIGNED names it. The foreign crate is no module.
    sources = {row["source"] for row in result["frame"]["details"]["ASSIGNED"]}
    assert "native.nested" in sources, sources
    assert not any("other" in source for source in sources), sources


def test_a_non_member_manifest_inside_a_member_keeps_the_targets_of_the_member(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["base", "app"]\nexclude = ["app/src"]\n',
        "crates/app/Cargo.toml": '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n',
        "crates/app/src/lib.rs": "pub fn run() {}\n",
        "crates/app/src/Cargo.toml": (
            '[package]\nname = "other"\nversion = "0.0.1"\nedition = "2021"\n'
            '[lib]\npath = "foreign.rs"\n'
        ),
        "crates/app/src/foreign.rs": "pub fn f() {}\n",
    }
    root = repository(tmp_path / "repo", release_core, files=layout, components=PARTS)
    result = validate(root)
    assert result["outcome"] == "verdict", result["gaps"]
    # The member keeps its library, and the foreign file is named as unclaimed.
    assert not any("package_unscanned" in gap["kind"] for gap in result["gaps"]), result["gaps"]
    assert any(r.startswith("Source file is in no module tree") for r in _reasons(result))


def _forbid(indirect: bool) -> tuple[dict[str, Any], ...]:
    forbid = rule(
        "FORBID",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate",
        indirect=indirect,
        include_type_checking=True,
    )
    return (forbid,)


def _recommit(root: Path) -> None:
    """The contract needs the schema of the `indirect` key."""
    contract = root / "architecture-contract.json"
    contract.write_text(contract.read_text().replace('"2.1.0"', '"3.21.0"'))
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(root), *identity, "commit", "-qam", "3.21"], check=True)


def _run_marker(root: Path, manifest: str) -> str:
    done = subprocess.run(
        ["cargo", "run", "--offline", "-q", "--manifest-path", str(root / manifest)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "CARGO_TARGET_DIR": str(root.parent / "target")},
    )
    assert done.returncode == 0, done.stderr
    return str(done.stdout)


MEMBER = '[package]\nname = "base-crate"\nversion = "0.0.0"\nedition = "2021"\n'
APP_SRC = "pub fn run() { base_crate::make(); x::f(); }\n"
MARKED_MAIN = 'fn main() { app::run(); println!("app ran"); }\n'
FOREIGN_X = '[package]\nname = "x"\nversion = "0.0.0"\nedition = "2021"\n'


def _app(extra: str) -> str:
    head = '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n[dependencies]\n'
    return head + extra


def test_a_member_that_is_a_symlink_to_an_excluded_directory_stays_in_the_scan(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": (
            '[workspace]\nmembers = ["base", "zapp"]\nexclude = ["app", "vendor/x"]\n'
        ),
        "crates/app/Cargo.toml": _app(
            'base-crate = { path = "../base" }\nx = { path = "../vendor/x" }\n'
        ),
        "crates/app/src/lib.rs": APP_SRC,
        "crates/app/src/main.rs": MARKED_MAIN,
        "crates/vendor/x/Cargo.toml": FOREIGN_X,
        "crates/vendor/x/src/lib.rs": "pub fn f() {}\n",
    }
    parts = (component("base", "base_crate"), component("app", "app"))
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=parts, rules=_forbid(False)
    )
    (root / "crates/zapp").symlink_to("app")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    _recommit(root)
    assert _run_marker(root, "crates/zapp/Cargo.toml") == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] == "FAIL", result["frame"]["rules"]


def test_an_excluded_crate_does_not_hide_an_edge_that_passes_through_it(
    tmp_path: Path, release_core: Path
) -> None:
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["app", "base"]\nexclude = ["vendor/x"]\n',
        "crates/app/Cargo.toml": _app('x = { path = "../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "crates/vendor/x/Cargo.toml": (
            FOREIGN_X + '[dependencies]\nbase-crate = { path = "../../base" }\n'
        ),
        "crates/vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    parts = (component("base", "base_crate"), component("app", "app"))
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=parts, rules=_forbid(True)
    )
    _recommit(root)
    assert _run_marker(root, "crates/app/Cargo.toml") == "app ran\n"
    result = validate(root)
    # The chain app -> x -> base is not read: the rule must not PASS.
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]
    assert any("depends on x, a crate that is no workspace member" in r for r in _reasons(result))


def test_two_dependency_keys_that_differ_by_dash_do_not_hide_a_foreign_crate(
    tmp_path: Path, release_core: Path
) -> None:
    app = _app(
        'x-foo = { path = "../vendor/x", package = "x" }\n'
        '[build-dependencies]\nx_foo = { path = "../base", package = "base-crate" }\n'
    )
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["app", "base"]\nexclude = ["vendor/x"]\n',
        "crates/app/Cargo.toml": app,
        "crates/app/build.rs": "fn main() {}\n",
        "crates/app/src/lib.rs": "pub fn run() { x_foo::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "crates/vendor/x/Cargo.toml": (
            FOREIGN_X + '[dependencies]\nbase-crate = { path = "../../base" }\n'
        ),
        "crates/vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    parts = (component("base", "base_crate"), component("app", "app"))
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=parts, rules=_forbid(True)
    )
    _recommit(root)
    assert _run_marker(root, "crates/app/Cargo.toml") == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_an_excluded_crate_with_an_unreadable_manifest_does_not_pass(
    tmp_path: Path, release_core: Path
) -> None:
    deep = "[" * 70 + "]" * 70
    layout = {
        "crates/Cargo.toml": '[workspace]\nmembers = ["app", "base"]\nexclude = ["vendor/x"]\n',
        "crates/app/Cargo.toml": _app('x = { path = "../vendor/x" }\n'),
        "crates/app/src/lib.rs": "pub fn run() { x::f(); }\n",
        "crates/app/src/main.rs": MARKED_MAIN,
        "crates/vendor/x/Cargo.toml": (
            FOREIGN_X
            + f"[package.metadata]\ndeep = {deep}\n"
            + '[dependencies]\nbase-crate = { path = "../../base" }\n'
        ),
        "crates/vendor/x/src/lib.rs": "pub fn f() { base_crate::make(); }\n",
    }
    parts = (component("base", "base_crate"), component("app", "app"))
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=parts, rules=_forbid(True)
    )
    _recommit(root)
    assert _run_marker(root, "crates/app/Cargo.toml") == "app ran\n"
    result = validate(root)
    assert result["frame"]["rules"]["FORBID"][1] != "PASS", result["frame"]["rules"]


def test_a_symlink_as_scan_root_does_not_hide_a_member(tmp_path: Path, release_core: Path) -> None:
    layout = {"crates/app/src/main.rs": MARKED_MAIN}
    root = repository(
        tmp_path / "repo", release_core, files=layout, components=(component("base", "base_crate"),)
    )
    (root / "alias").symlink_to("crates/app")
    config = root / "archkeel.toml"
    config.write_text(
        config.read_text().replace('roots = ["crates"]', 'roots = ["crates/base", "alias"]')
    )
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(root), *identity, "commit", "-qm", "alias"], check=True)
    assert _run_marker(root, "crates/app/Cargo.toml") == "app ran\n"
    result = validate(root)
    # `app` is a member that no component owns: it is no foreign code, so ASSIGNED fails.
    assert result["frame"]["rules"]["ASSIGNED"][1] == "FAIL", result["frame"]["rules"]


def _without_cargo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = shutil.which("git")
    assert git is not None
    (bin_dir / "git").symlink_to(git)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_without_cargo_an_excluded_crate_gives_a_named_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", release_core, files=_layout("other"), components=PARTS)
    _without_cargo(tmp_path, monkeypatch)
    result = validate(root)
    reasons = _reasons(result)
    assert any(r.startswith("The Cargo workspace members are unavailable") for r in reasons), (
        reasons
    )
    assert any("crates/vendor/erdep" in r for r in reasons), reasons
    # The old read stays: the foreign crate is a module that no component owns.
    assert result["frame"]["rules"]["ASSIGNED"][1] != "PASS"


def test_without_cargo_a_plain_workspace_needs_no_gap(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", release_core)
    _without_cargo(tmp_path, monkeypatch)
    result = validate(root)
    assert _reasons(result) == []
    assert {row[1] for row in result["frame"]["rules"].values()} == {"PASS"}
