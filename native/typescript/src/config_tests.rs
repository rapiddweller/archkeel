// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the selected files of the reply, which the host compares with the Python collector.
// Each expected list was printed by `config.load_config(Snapshot(root), "tsconfig.json",
// ("src",))` on the same tree.

use super::*;
use crate::test_tree::Tree;

struct Loaded {
    files: Vec<String>,
    problems: Vec<String>,
    inputs: Vec<String>,
}

fn load(files: &[(&str, &str)]) -> Loaded {
    let tree = Tree::new(files);
    let mut snapshot = Snapshot::new(&tree.path());
    let files = load_config(&mut snapshot, "tsconfig.json", &["src".to_owned()]);
    Loaded {
        files,
        problems: snapshot.problems.iter().cloned().collect(),
        inputs: snapshot
            .inputs()
            .into_iter()
            .map(|input| input.path)
            .collect(),
    }
}

#[test]
fn the_default_include_skips_outputs_hidden_installed_and_shadowed_files() {
    let loaded = load(&[
        (
            "tsconfig.json",
            "{ // comment\n \"compilerOptions\": {\"outDir\": \"dist\", \"allowJs\": true,}, /* x */ }",
        ),
        ("src/a.ts", ""),
        ("src/a.js", ""),
        ("src/b.d.ts", ""),
        ("src/b.js", ""),
        ("src/c.tsx", ""),
        ("src/.hidden/x.ts", ""),
        ("src/node_modules/y.ts", ""),
        ("dist/out.js", ""),
        ("src/x.min.js", ""),
        ("src/style.css", ""),
        ("src/data.json", ""),
        ("src/tests/t.test.ts", ""),
        ("other/o.ts", ""),
    ]);
    let expected = [
        "src/a.ts",
        "src/b.d.ts",
        "src/b.js",
        "src/c.tsx",
        "src/tests/t.test.ts",
    ];
    assert_eq!(loaded.files, expected);
    assert!(loaded.problems.is_empty());
    assert_eq!(loaded.inputs, ["tsconfig.json"]);
}

#[test]
fn extends_files_and_the_config_directory_select_like_python() {
    let loaded = load(&[
        (
            "base/tsconfig.base.json",
            r#"{"include": ["${configDir}/src/**/*"], "exclude": ["src/gen"]}"#,
        ),
        (
            "tsconfig.json",
            r#"{"extends": "./base/tsconfig.base", "files": ["src/listed.ts", "src/missing.ts"]}"#,
        ),
        ("src/listed.ts", ""),
        ("src/a.ts", ""),
        ("src/gen/g.ts", ""),
        ("src/a.js", ""),
    ]);
    let expected = [
        "src/a.ts",
        "src/gen/g.ts",
        "src/listed.ts",
        "src/missing.ts",
    ];
    assert_eq!(loaded.files, expected);
    assert!(loaded.problems.is_empty());
    assert_eq!(loaded.inputs, ["base/tsconfig.base.json", "tsconfig.json"]);
}

#[test]
fn unobserved_settings_are_problems() {
    let loaded = load(&[
        (
            "tsconfig.json",
            r#"{"include": ["src/**/*.ts"], "exclude": ["src/**/*.test.ts"], "references": [], "extends": "pkg/base"}"#,
        ),
        ("src/a.ts", ""),
        ("src/a.test.ts", ""),
        ("src/deep/b.ts", ""),
    ]);
    assert_eq!(loaded.files, ["src/a.ts", "src/deep/b.ts"]);
    let expected = [
        "Project references require separately observed projects",
        "TSConfig extends through a package is not observed: pkg/base",
    ];
    assert_eq!(loaded.problems, expected);
}

#[test]
fn malformed_specs_fall_back_to_the_default_include() {
    let loaded = load(&[
        (
            "tsconfig.json",
            r#"{"include": "src", "compilerOptions": []}"#,
        ),
        ("src/a.ts", ""),
    ]);
    assert_eq!(loaded.files, ["src/a.ts"]);
    let expected = [
        "Compiler option 5024: 'compilerOptions' must be an object.",
        "Compiler option 5024: 'include' must be a list of strings.",
    ];
    assert_eq!(loaded.problems, expected);
}

#[test]
fn a_missing_config_is_a_problem_and_keeps_the_default_include() {
    let loaded = load(&[("src/a.ts", "")]);
    assert_eq!(loaded.files, ["src/a.ts"]);
    assert_eq!(loaded.problems, ["Cannot read file 'tsconfig.json'."]);
}

#[test]
fn comments_and_trailing_commas_leave_strings_unchanged() {
    let text = "{\"a\": \"// not, a comment /* */\", // c\n \"b\": [1, 2, /* c */ ], }";
    let plain = strip_jsonc(text);
    let value: Value = serde_json::from_str(&plain).unwrap();
    assert_eq!(value["a"], "// not, a comment /* */");
    assert_eq!(value["b"], serde_json::json!([1, 2]));
}

#[test]
fn a_large_hostile_config_is_stripped_in_linear_time() {
    // Before the fix, 200 kB of white space took about 10 s in a release build.
    let spaces = format!("{{\"include\": [\"src\"],{}}}", " ".repeat(200_000));
    let comments = format!("{{}}{}", "/*,".repeat(70_000));
    let started = std::time::Instant::now();
    let plain = strip_jsonc(&spaces);
    strip_jsonc(&comments);
    assert!(started.elapsed() < std::time::Duration::from_secs(2));
    let value: Value = serde_json::from_str(&plain).unwrap();
    assert_eq!(value["include"], serde_json::json!(["src"]));
}

// Consumer: a hostile `tsconfig.json`. A deep nesting is a parse problem and not a stack overflow.
#[test]
fn a_deeply_nested_config_is_a_problem_and_not_a_crash() {
    let depth = 200_000;
    let nested = format!("{}{}", "[".repeat(depth), "]".repeat(depth));
    let loaded = load(&[("tsconfig.json", &nested), ("src/a.ts", "")]);

    assert!(loaded
        .problems
        .contains(&"Cannot parse 'tsconfig.json' as JSON.".to_owned()));
}
