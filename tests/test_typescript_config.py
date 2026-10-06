# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TSConfig reading: file selection, option chains and every refusal to guess."""

import json
import os
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.config import Config, Snapshot, load_config


def _config(
    root: Path,
    files: dict[str, str],
    tsconfig: str = "{}",
    roots: tuple[str, ...] = (".",),
    name: str = "tsconfig.json",
) -> tuple[Config, Snapshot]:
    for rel, text in {name: tsconfig, **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    snapshot = Snapshot(str(root))
    return load_config(snapshot, name, roots), snapshot


def _selected(
    root: Path, paths: list[str], config: dict[str, object], **kwargs: object
) -> list[str]:
    selected, _ = _config(root, dict.fromkeys(paths, ""), json.dumps(config), **kwargs)  # type: ignore[arg-type]
    return list(selected.files)


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
def test_discovery_visits_a_symlinked_directory_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _config(tmp_path, {"src/main.ts": "export {};"})
    (tmp_path / "src/loop").symlink_to(".", target_is_directory=True)
    snapshot = Snapshot(str(tmp_path))
    entries = snapshot.entries
    visited: list[str] = []

    def bounded_entries(rel: str) -> tuple[list[str], list[str]]:
        visited.append(rel)
        assert len(visited) <= 3, visited
        return entries(rel)

    monkeypatch.setattr(snapshot, "entries", bounded_entries)
    config = load_config(snapshot, "tsconfig.json", ("src",))
    assert config.files == ("src/main.ts",)


_TREE = [
    "src/a.ts",
    "src/b.tsx",
    "src/c.d.ts",
    "src/d.mts",
    "src/e.cts",
    "src/f.js",
    "src/f.ts",
    "src/g.js",
    "src/g.d.ts",
    "src/h.min.js",
    "src/gen/i.ts",
    "src/legacy/j.ts",
    "src/deep/k/l.ts",
    "src/deep/k/l.test.ts",
    "src/.hidden/m.ts",
    "src/.dot.ts",
    "src/node_modules/n/index.d.ts",
    "lib/o.ts",
    "node_modules/q/index.d.ts",
    "top.ts",
]


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {},
            [
                "lib/o.ts",
                "src/a.ts",
                "src/b.tsx",
                "src/c.d.ts",
                "src/d.mts",
                "src/deep/k/l.test.ts",
                "src/deep/k/l.ts",
                "src/e.cts",
                "src/f.ts",
                "src/g.d.ts",
                "src/gen/i.ts",
                "src/legacy/j.ts",
                "top.ts",
            ],
        ),
        (
            {"include": ["src/*.ts"]},
            ["src/a.ts", "src/c.d.ts", "src/f.ts", "src/g.d.ts"],
        ),
        ({"include": ["src/**/*.tsx"]}, ["src/b.tsx"]),
        ({"include": ["src/?.ts"]}, ["src/a.ts", "src/f.ts"]),
        # Neither a dotted directory nor a dotted file is matched by a wildcard or by its name.
        ({"include": ["src/.hidden"]}, []),
        (
            {"include": ["src"], "exclude": ["**/*.test.ts", "src/legacy", "src/gen"]},
            [
                "src/a.ts",
                "src/b.tsx",
                "src/c.d.ts",
                "src/d.mts",
                "src/deep/k/l.ts",
                "src/e.cts",
                "src/f.ts",
                "src/g.d.ts",
            ],
        ),
        ({"files": ["top.ts", "src/missing.ts"]}, ["src/missing.ts", "top.ts"]),
        ({"files": ["top.ts"], "include": ["lib"]}, ["lib/o.ts", "top.ts"]),
        ({"include": ["lib"], "exclude": []}, ["lib/o.ts"]),
        ({"include": ["node_modules/q"]}, []),
        ({"include": ["../outside/*.ts", "lib"]}, ["lib/o.ts"]),
    ],
)
def test_include_exclude_and_files_select_what_the_compiler_selects(
    tmp_path: Path, config: dict[str, object], expected: list[str]
) -> None:
    assert (
        _selected(tmp_path, _TREE, {"compilerOptions": {"module": "CommonJS"}, **config})
        == expected
    )


def test_javascript_joins_the_selection_only_with_allow_js_and_loses_to_its_typescript_twin(
    tmp_path: Path,
) -> None:
    files = ["src/f.js", "src/f.ts", "src/g.js", "src/g.d.ts", "src/h.js", "src/h.min.js"]
    selected = _selected(
        tmp_path,
        files,
        {"compilerOptions": {"module": "CommonJS", "allowJs": True}, "include": ["src"]},
    )
    # `f.ts` shadows `f.js`; a declaration file does not shadow its JavaScript; `*.min.js` is out.
    assert selected == ["src/f.ts", "src/g.d.ts", "src/g.js", "src/h.js"]


def test_installed_dependencies_and_unselected_roots_are_never_selected(tmp_path: Path) -> None:
    explicit = {"compilerOptions": {"module": "CommonJS"}, "include": ["src", "node_modules/q"]}
    config, snapshot = _config(
        tmp_path,
        dict.fromkeys(_TREE, ""),
        json.dumps(explicit),
        roots=("src", "node_modules/q/index.d.ts"),
    )
    assert "node_modules/q/index.d.ts" not in config.files
    assert "Installed dependency cannot be a selected source root" in snapshot.problems
    assert all(path.startswith("src/") for path in config.files)


def test_an_explicit_file_root_is_selected_beyond_include_and_exclude(tmp_path: Path) -> None:
    files = {"src/main.ts": "", "standalone.ts": ""}
    tsconfig = json.dumps({"include": ["src"], "exclude": ["standalone.*"]})
    config, _ = _config(tmp_path, files, tsconfig, roots=("standalone.ts",))
    assert config.files == ("standalone.ts",)


def test_a_missing_root_and_an_empty_selection_are_problems(tmp_path: Path) -> None:
    config, snapshot = _config(
        tmp_path, {"src/a.ts": ""}, '{"include": ["src"]}', roots=("absent",)
    )
    assert config.files == ()
    assert {"Missing or unsafe source root", "No selected source files"} <= snapshot.problems
    _, none = _config(tmp_path / "empty", {}, '{"include": ["nowhere"]}')
    assert "No inputs were found in config file." in none.problems


@pytest.mark.parametrize(
    ("text", "module", "resolution"),
    [
        ('{"compilerOptions": {"module": "CommonJS",}}', "commonjs", "node10"),
        ('{// comment\n "compilerOptions": {/* x */ "moduleResolution": "Node"}}', None, "node10"),
        ("﻿{}", None, "node10"),
        ('{"compilerOptions": {"module": "ES2022"}}', "es2022", "classic"),
        ('{"compilerOptions": {"module": "NodeNext"}}', "nodenext", "nodenext"),
        ('{"compilerOptions": {"module": "Node18"}}', "node18", "node16"),
        ('{"compilerOptions": {"module": "Preserve"}}', "preserve", "bundler"),
        ('{"compilerOptions": {"target": "ES2020"}}', None, "classic"),
        ('{"compilerOptions": {"target": "ES5"}}', None, "node10"),
        (
            '{"compilerOptions": {"module": "NodeNext", "moduleResolution": "NodeNext"}}',
            "nodenext",
            "nodenext",
        ),
    ],
)
def test_option_defaults_follow_the_compiler(
    tmp_path: Path, text: str, module: str | None, resolution: str
) -> None:
    config, _ = _config(tmp_path, {"src/a.ts": ""}, text)
    assert (config.options.module, config.options.resolution) == (module, resolution)
    assert config.partial is False


@pytest.mark.parametrize(
    ("options", "problem"),
    [
        ({"module": "CommonJS", "moduleResolution": "NodeNext"}, "5110"),
        ({"module": "ESNext", "moduleResolution": "NodeNext"}, "5110"),
        ({"module": "NodeNext", "moduleResolution": "Node"}, "5110"),
        ({"module": "CommonJS", "moduleResolution": "Bundler"}, "5095"),
        ({"Module": "CommonJS"}, "Unknown compiler option 'Module'"),
        ({"modul": "CommonJS"}, "Unknown compiler option 'modul'"),
        ({"module": "foo"}, "6046"),
        ({"moduleResolution": 3}, "6046"),
        ({"target": "ES2999"}, "6046"),
        ({"paths": {"a*b*": ["x"]}}, "5061"),
        ({"paths": []}, "5024"),
    ],
)
def test_invalid_options_are_problems_not_defaults(
    tmp_path: Path, options: dict[str, object], problem: str
) -> None:
    _, snapshot = _config(tmp_path, {"src/a.ts": ""}, json.dumps({"compilerOptions": options}))
    assert any(problem in item for item in snapshot.problems), snapshot.problems


def test_option_values_are_matched_without_regard_to_case_but_names_are_not(tmp_path: Path) -> None:
    config, snapshot = _config(
        tmp_path,
        {"src/a.ts": ""},
        json.dumps({"compilerOptions": {"module": "nodenext", "moduleResolution": "NODENEXT"}}),
    )
    assert config.options.resolution == "nodenext"
    assert snapshot.problems == set()


def test_a_relative_extends_chain_merges_options_and_inherits_file_specs(tmp_path: Path) -> None:
    files = {
        "configs/base.json": json.dumps(
            {
                "compilerOptions": {"module": "CommonJS", "moduleResolution": "Node"},
                "include": ["../src"],
            }
        ),
        "src/a.ts": "",
        "other/b.ts": "",
    }
    config, snapshot = _config(tmp_path, files, '{"extends": "./configs/base"}')
    # `include` is relative to the config that wrote it; the `.json` suffix may be omitted.
    assert config.files == ("src/a.ts",)
    assert config.options.resolution == "node10"
    assert snapshot.problems == set()
    assert config.partial is False


def test_own_settings_win_and_a_later_extends_entry_wins_over_an_earlier(tmp_path: Path) -> None:
    files = {
        "a.json": json.dumps(
            {"compilerOptions": {"module": "CommonJS", "target": "ES2020"}, "include": ["x"]}
        ),
        "b.json": json.dumps({"compilerOptions": {"module": "NodeNext"}}),
        "src/a.ts": "",
    }
    config, _ = _config(
        tmp_path,
        files,
        '{"extends": ["./a.json", "./b.json"], "compilerOptions": {"target": "ES5"}, '
        '"include": ["src"]}',
    )
    assert (config.options.module, config.options.target) == ("nodenext", "es5")
    assert config.files == ("src/a.ts",)


def test_paths_are_relative_to_the_config_that_sets_them_unless_base_url_does(
    tmp_path: Path,
) -> None:
    files = {
        "configs/paths.json": json.dumps({"compilerOptions": {"paths": {"@l/*": ["../lib/*"]}}}),
        "configs/url.json": json.dumps({"compilerOptions": {"baseUrl": "../src"}}),
    }
    config, _ = _config(tmp_path, files, '{"extends": "./configs/paths.json"}')
    assert (config.options.base_url, config.options.paths_base) == (None, "configs")
    both, _ = _config(
        tmp_path / "two", files, '{"extends": ["./configs/paths.json", "./configs/url.json"]}'
    )
    assert (both.options.base_url, both.options.paths_base) == ("src", "src")


def test_config_dir_names_the_directory_of_the_root_config(tmp_path: Path) -> None:
    files = {
        "configs/base.json": json.dumps({"include": ["${configDir}/src"]}),
        "src/a.ts": "",
        "configs/b.ts": "",
    }
    config, _ = _config(tmp_path, files, '{"extends": "./configs/base.json"}')
    assert config.files == ("src/a.ts",)


@pytest.mark.parametrize(
    ("tsconfig", "files", "problem"),
    [
        ('{"extends": "@tsconfig/node20/tsconfig.json"}', {}, "through a package"),
        (
            '{"extends": "@tsconfig/node20/tsconfig.json"}',
            {"node_modules/@tsconfig/node20/tsconfig.json": "{}"},
            "through a package",
        ),
        ('{"extends": "./absent"}', {}, "not found"),
        ('{"extends": "./a.json"}', {"a.json": '{"extends": "./tsconfig.json"}'}, "Circularity"),
        ('{"extends": [1]}', {}, "5024"),
        ('{"extends": "./a.json"}', {"a.json": "{broken"}, "Cannot parse"),
    ],
)
def test_an_extends_that_cannot_be_followed_makes_the_whole_config_partial(
    tmp_path: Path, tsconfig: str, files: dict[str, str], problem: str
) -> None:
    config, snapshot = _config(tmp_path, {"src/a.ts": "", **files}, tsconfig)
    assert config.partial is True
    assert any(problem in item for item in snapshot.problems), snapshot.problems


def test_project_references_are_a_problem_and_unreadable_config_is_partial(tmp_path: Path) -> None:
    _, snapshot = _config(
        tmp_path, {"src/a.ts": ""}, '{"references": [{"path": "../x"}], "include": ["src"]}'
    )
    assert "Project references require separately observed projects" in snapshot.problems
    config, missing = _config(tmp_path / "m", {"src/a.ts": ""}, "{}", name="other.json")
    broken = load_config(Snapshot(str(tmp_path / "m")), "absent.json", (".",))
    assert broken.partial is True
    assert config.partial is False
    assert missing.problems == set()


def test_settings_that_change_resolution_and_are_not_modelled_are_named(tmp_path: Path) -> None:
    config, _ = _config(
        tmp_path,
        {"src/a.ts": ""},
        json.dumps(
            {
                "compilerOptions": {
                    "rootDirs": ["a"],
                    "preserveSymlinks": True,
                    "customConditions": [],
                }
            }
        ),
    )
    assert config.options.unmodeled == ("rootDirs", "preserveSymlinks")


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
def test_the_snapshot_never_reads_or_digests_a_path_that_leaves_it(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.ts").write_text("export const secret = 1;")
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)
    (root / "src/link.ts").symlink_to(outside / "secret.ts")
    (root / "src/ok.ts").write_text("")
    (root / "tsconfig.json").write_text('{"include": ["src"]}')
    snapshot = Snapshot(str(root))
    config = load_config(snapshot, "tsconfig.json", ("src",))
    assert snapshot.read("src/link.ts") is None
    assert snapshot.read("../outside/secret.ts") is None
    assert "src/link.ts" not in snapshot.inputs
    assert config.files == ("src/ok.ts",)
    assert {
        "Resolver symlink outside snapshot",
        "Resolver input outside snapshot",
    } <= snapshot.problems


def test_every_read_is_digested_with_the_exact_bytes(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"\xff\xfe raw")
    snapshot = Snapshot(str(tmp_path))
    assert snapshot.read("a.bin") == b"\xff\xfe raw"
    digest, role = snapshot.inputs["a.bin"]
    assert (len(digest), role) == (64, "resolution")
    snapshot.select("a.bin")
    assert snapshot.inputs["a.bin"][1] == "selected"
