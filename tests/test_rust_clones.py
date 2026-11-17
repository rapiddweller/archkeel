# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-327: the clone check of the Rust code finds a copy, also a renamed one, and ratchets."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from frozen_native import frozen_root as frozen_root

ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools/rust_clones.py"
WINDOW = 20

ORIGINAL = """
fn total(items: &[Item]) -> u64 {
    let mut sum = 0;
    for item in items {
        if item.active && item.weight > 3 {
            sum += item.weight * 2;
        } else {
            sum += item.weight;
        }
    }
    sum
}
"""
RENAMED = ORIGINAL.replace("total", "count").replace("items", "rows").replace("sum", "acc")
UNRELATED = """
fn main() { println!("{}", std::env::args().count()); let x = vec![1, 2, 3]; drop(x); }
"""


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location("rust_clones", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rust_clones"] = module
    spec.loader.exec_module(module)
    return module


clones = load()


def scratch(tmp_path: Path, files: dict[str, str]) -> Path:
    native = tmp_path / "native"
    for name, text in files.items():
        (native / name).parent.mkdir(parents=True, exist_ok=True)
        (native / name).write_text(text, encoding="utf-8")
    return native


def run(native: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--native", str(native), "--window", str(WINDOW), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_planted_clone_fails_the_gate(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": ORIGINAL + UNRELATED})
    result = run(native)
    assert result.returncode == 1
    assert "New clone" in result.stderr
    assert "a/src/one.rs" in result.stderr and "a/src/two.rs" in result.stderr


def test_renamed_identifiers_still_fail_in_the_default_mode_only(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": RENAMED})
    assert run(native).returncode == 1
    assert run(native, "--exact").returncode == 0


def test_comments_and_white_space_do_not_hide_a_clone(tmp_path: Path) -> None:
    spaced = "// a note\n" + ORIGINAL.replace("\n    ", "\n\n        /* x */ ")
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": spaced})
    assert run(native, "--exact").returncode == 1


def rows(prefix: str, count: int) -> str:
    return "".join(f'    ("{prefix}{i}", K::V{i}),\n' for i in range(count))


def test_unrelated_code_passes(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": UNRELATED})
    assert run(native).returncode == 0


def test_a_duplicated_table_of_rows_of_one_shape_is_skipped(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": rows("a", 40), "a/src/two.rs": rows("b", 40)})
    assert run(native).returncode == 0


def kinds(name: str, body: str) -> dict[str, str]:
    """Two files that hold `body` and own, apart from it, code that differs."""
    return {
        "a/src/one.rs": body + f"fn first() -> u8 {{ {name}(1) }}\n",
        "a/src/two.rs": body + "fn second() -> u8 { 9 }\n",
    }


def test_a_const_table_of_literals_and_paths_is_not_a_clone(tmp_path: Path) -> None:
    table = "const T: &[(&str, K)] = &[\n" + rows("n", 40) + "];\n"
    assert run(scratch(tmp_path, kinds("a", table))).returncode == 0
    strings = (
        "pub const NAMES: [&str; 40] = [\n" + "".join(f'    "w{i}",\n' for i in range(40)) + "];\n"
    )
    assert run(scratch(tmp_path / "b", kinds("a", strings))).returncode == 0


def test_a_const_with_a_call_in_its_rows_is_logic(tmp_path: Path) -> None:
    table = "const T: &[K] = &[\n" + "".join(f"    K::new({i}),\n" for i in range(40)) + "];\n"
    assert run(scratch(tmp_path, kinds("a", table))).returncode == 1


def test_a_use_list_is_not_a_clone(tmp_path: Path) -> None:
    names = ", ".join(f"Name{i}" for i in range(40))
    uses = f"use crate::model::{{{names}}};\nuse crate::more::Other;\n"
    assert run(scratch(tmp_path, kinds("a", uses))).returncode == 0


def arms(prefix: str, count: int, extra: str = "") -> str:
    lines = "".join(f'        E::V{i} => "{prefix}{i}",\n' for i in range(count))
    return f"fn word(e: E) -> &'static str {{\n    match e {{\n{lines}{extra}    }}\n}}\n"


def test_a_match_of_variants_and_words_is_not_a_clone(tmp_path: Path) -> None:
    assert run(scratch(tmp_path, kinds("a", arms("x", 30)))).returncode == 0
    reverse = (
        "fn kind(w: &str) -> E {\n    match w {\n"
        + "".join(f'        "w{i}" | "v{i}" => E::V{i},\n' for i in range(30))
        + "        _ => E::Other,\n    }\n}\n"
    )
    assert run(scratch(tmp_path / "b", kinds("a", reverse))).returncode == 0


def test_a_match_of_variants_and_tuples_of_words_is_not_a_clone(tmp_path: Path) -> None:
    lines = "".join(f'        E::V{i} => ("N{i}", "t{i}"),\n' for i in range(30))
    body = f"fn pair(e: E) -> (&'static str, &'static str) {{\n    match e {{\n{lines}    }}\n}}\n"
    assert run(scratch(tmp_path, kinds("a", body))).returncode == 0


def test_declarations_of_words_and_names_are_not_clones(tmp_path: Path) -> None:
    words = (
        "closed! {\n    pub enum E {\n"
        + "".join(f'        V{i} = "v{i}",\n' for i in range(30))
        + "    }\n}\n"
    )
    assert run(scratch(tmp_path, kinds("a", words))).returncode == 0
    mods = "".join(f"mod m{i};\n" for i in range(40))
    assert run(scratch(tmp_path / "b", kinds("a", mods))).returncode == 0
    fields = (
        "#[derive(Clone)]\nstruct S {\n"
        + "".join(f"    f{i}: Vec<String>,\n" for i in range(30))
        + "}\n"
    )
    assert run(scratch(tmp_path / "c", kinds("a", fields))).returncode == 0


def test_a_struct_declaration_with_restricted_visibility_is_not_a_clone(tmp_path: Path) -> None:
    """AD-584: `pub(crate)` on the struct and on its fields is no logic (two crates, same shape)."""
    fields = (
        "#[derive(Clone, Debug)]\npub(crate) struct S {\n"
        + "".join(f"    pub(crate) f{i}: Option<String>,\n" for i in range(12))
        + "    pub(super) last: usize,\n}\n"
    )
    assert run(scratch(tmp_path, kinds("a", fields))).returncode == 0
    call = fields.replace("Option<String>,", "Option<String>,\n    pub(crate) g: f(1),", 1)
    assert run(scratch(tmp_path / "b", kinds("a", call))).returncode == 1


def test_two_identical_function_bodies_stay_clones_beside_struct_declarations() -> None:
    declaration = (
        "pub(crate) struct S {\n"
        + "".join(f"    pub(crate) f{i}: Option<String>,\n" for i in range(12))
        + "}\n"
    )

    def body(name: str) -> str:
        lines = "".join(f'    out.put("k{i}", &item.k{i})?;\n' for i in range(14))
        return f"fn {name}(out: &mut W, item: &Item) -> R {{\n{lines}    Ok(())\n}}\n"

    assert clones.find_blocks({"a.rs": declaration, "b.rs": declaration}) == []
    both = {"a.rs": declaration + body("one"), "b.rs": declaration + body("two")}
    found = clones.find_blocks(both)
    assert found, "the two function bodies are still reported"
    declaration_lines = declaration.count("\n")
    assert all(block.first_lines[0] > declaration_lines for block in found)


def test_a_macro_call_with_a_call_in_its_body_is_logic(tmp_path: Path) -> None:
    body = "closed! {\n" + "".join(f"    V{i} = make({i}),\n" for i in range(40)) + "}\n"
    assert run(scratch(tmp_path, kinds("a", body))).returncode == 1


def test_a_match_with_a_guard_or_an_expression_arm_is_logic(tmp_path: Path) -> None:
    guarded = arms("x", 30, '        E::Z if flag() => "z",\n')
    assert run(scratch(tmp_path, kinds("a", guarded))).returncode == 1
    computed = arms("x", 30, "        E::Z => name_of(1),\n")
    assert run(scratch(tmp_path / "b", kinds("a", computed))).returncode == 1


def test_logic_in_a_file_with_tables_is_still_found(tmp_path: Path) -> None:
    table = "const T: &[(&str, K)] = &[\n" + rows("n", 40) + "];\n"
    native = scratch(
        tmp_path,
        {"a/src/one.rs": table + ORIGINAL, "a/src/two.rs": ORIGINAL + table},
    )
    result = run(native)
    assert result.returncode == 1 and "New clone" in result.stderr


def test_fourteen_equal_lines_inside_two_function_bodies_are_reported() -> None:
    def body(name: str) -> str:
        lines = "".join(f'    out.put("k{i}", &item.k{i})?;\n' for i in range(14))
        return f"fn {name}(out: &mut W, item: &Item) -> R {{\n{lines}    Ok(())\n}}\n"

    found = clones.find_blocks({"a.rs": body("one"), "b.rs": body("two")})
    assert ("a.rs", "b.rs") in {(block.first, block.second) for block in found}


def test_a_clone_between_a_test_file_and_production_code_is_production(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one_tests.rs": ORIGINAL, "a/src/two.rs": ORIGINAL})
    assert "1 in production, 0 in tests" in run(native).stdout or run(native).returncode == 1


def test_a_clone_in_a_test_file_is_a_warning(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one_tests.rs": ORIGINAL, "a/src/two_tests.rs": ORIGINAL})
    result = run(native)
    assert result.returncode == 0
    assert "0 in production, 1 in tests" in result.stdout
    assert "warning (test code)" in run(native, "--list").stdout


def test_the_baseline_allows_a_clone_and_a_gone_clone_lowers_it(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": ORIGINAL})
    block = clones.find_blocks(clones.read_sources(native), window=WINDOW)[0]
    baseline = native / "clone_baseline.json"
    entry = {"files": [block.first, block.second], "tokens": block.tokens, "reason": "fixture"}
    baseline.write_text(json.dumps({block.key: entry}), encoding="utf-8")
    assert run(native).returncode == 0
    (native / "a/src/two.rs").write_text(UNRELATED, encoding="utf-8")
    gone = run(native)
    assert gone.returncode == 1 and "is gone" in gone.stderr
    assert run(native, "--lower").returncode == 0
    assert json.loads(baseline.read_text(encoding="utf-8")) == {}
    assert run(native).returncode == 0


def test_a_grown_clone_fails_and_a_shrunk_clone_asks_for_a_lower_count(tmp_path: Path) -> None:
    native = scratch(tmp_path, {"a/src/one.rs": ORIGINAL, "a/src/two.rs": ORIGINAL})
    block = clones.find_blocks(clones.read_sources(native), window=WINDOW)[0]
    entry = {"files": [], "reason": "fixture"}
    grown = clones.ratchet_problems([block], {block.key: {**entry, "tokens": block.tokens - 1}})
    shrunk = clones.ratchet_problems([block], {block.key: {**entry, "tokens": block.tokens + 5}})
    assert "grew" in grown[0] and "shrank" in shrunk[0]
    assert (
        clones.lowered([block], {block.key: {**entry, "tokens": block.tokens + 5}})[block.key][
            "tokens"
        ]
        == block.tokens
    )


def test_a_clone_inside_an_inline_test_module_is_a_test_block() -> None:
    inline = f"#[cfg(test)]\nmod tests {{\n{ORIGINAL}\n}}\n"
    found = clones.find_blocks({"a.rs": inline, "b.rs": inline}, window=WINDOW)
    assert found and all(block.is_test for block in found)


def test_a_production_clone_after_an_inline_test_module_is_production() -> None:
    inline = f'#[cfg(test)]\nmod tests {{ fn t() {{ let _ = "}}"; }} }}\n{ORIGINAL}'
    found = clones.find_blocks({"a.rs": inline, "b.rs": inline}, window=WINDOW)
    assert found and not any(block.is_test for block in found)


def three_copies() -> dict[str, str]:
    return {"one.rs": ORIGINAL, "three.rs": ORIGINAL + UNRELATED + ORIGINAL}


def test_each_neighbouring_pair_of_copies_is_one_block() -> None:
    found = clones.find_blocks(three_copies(), window=WINDOW)
    assert sorted((block.first, block.second) for block in found) == [
        ("one.rs", "three.rs"),
        ("three.rs", "three.rs"),
    ]


def test_a_copy_added_to_a_file_pair_in_the_baseline_fails() -> None:
    sources = three_copies()
    baseline = {
        block.key: {"tokens": block.tokens} for block in clones.find_blocks(sources, window=WINDOW)
    }
    assert clones.ratchet_problems(clones.find_blocks(sources, window=WINDOW), baseline) == []
    sources["three.rs"] += UNRELATED + ORIGINAL
    problems = clones.ratchet_problems(clones.find_blocks(sources, window=WINDOW), baseline)
    assert len(problems) == 1 and "grew" in problems[0]


def test_a_second_copy_in_one_baselined_pair_of_files_fails() -> None:
    sources = {"a.rs": ORIGINAL, "b.rs": ORIGINAL}
    baseline = {
        block.key: {"tokens": block.tokens} for block in clones.find_blocks(sources, window=WINDOW)
    }
    sources["b.rs"] += UNRELATED + ORIGINAL
    found = clones.find_blocks(sources, window=WINDOW)
    assert len(clones.ratchet_problems(found, baseline)) == 1


def test_the_real_workspace_matches_its_baseline(frozen_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), "--native", str(frozen_root / "native")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "entry", json.loads((ROOT / "native/clone_baseline.json").read_text("utf-8")).items()
)
def test_each_baseline_entry_has_a_reason(entry: tuple[str, dict[str, str]]) -> None:
    assert len(entry[1]["reason"]) > 20
