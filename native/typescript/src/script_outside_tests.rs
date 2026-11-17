// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the proof that a global of the scan is the native one (#1546). `src/a.ts` calls
// `window.open()` and `Math.max()`. A file of the repository outside the scan root `src` replaces
// a global: in a browser that loads it, `a` then calls code that the scan does not see. The guard
// must withhold the proof of that global and name the file and the line; other globals keep their
// proof. A test file, a declaration, an installed package and a hidden directory are not read.

use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "window.open();\nexport const m = Math.max(1, 2);\n";
const B: &str = "export function hidden() {}\n";

/// The gaps of the project that withhold a global for a file outside the scan roots, with the
/// global and the cited places.
fn withheld(outside: &[(&str, &str)]) -> Vec<String> {
    let mut files = vec![("tsconfig.json", "{}"), ("src/a.ts", A), ("src/b.ts", B)];
    files.extend_from_slice(outside);
    let tree = Tree::new(&files);
    let facts = collect(&request(&tree, true), provenance());
    facts
        .gaps
        .iter()
        .filter(|gap| {
            gap.title
                .contains("replaced by a file outside the scan roots")
        })
        .map(|gap| gap.title.clone())
        .collect()
}

fn holds(outside: &[(&str, &str)], name: &str) -> bool {
    withheld(outside)
        .iter()
        .any(|title| title.starts_with(&format!("Script global {name} ")))
}

#[test]
fn the_plant_of_1546_withholds_open() {
    let boot = "import { hidden } from './src/b';\nwindow.open = hidden as any;\n";
    assert!(holds(&[("boot.ts", boot)], "open"));
    assert!(!holds(&[("boot.ts", boot)], "Math"), "Math keeps its proof");
    assert!(withheld(&[]).is_empty(), "no outside file, no gap");
}

#[test]
fn each_form_that_replaces_a_global_withholds_it() {
    let forms = [
        ("globalThis.open = () => 1;", "open"),
        ("self['open'] = () => 1;", "open"),
        ("window.self.open = () => 1;", "open"),
        ("open = () => 1;", "open"),
        (
            "Object.defineProperty(window, 'open', { value: 1 });",
            "open",
        ),
        ("Object.assign(window, { open: 1 });", "open"),
        ("Reflect.set(globalThis, 'open', 1);", "open"),
        ("window.__defineGetter__('open', () => 1);", "open"),
        ("function open() {}", "open"),
        ("var open = 1;", "open"),
    ];
    for (code, name) in forms {
        assert!(holds(&[("boot.js", code)], name), "{code}");
    }
    let page = "<html><body>\n<script>\nwindow.open = () => 1;\n</script></body></html>\n";
    assert!(holds(&[("index.html", page)], "open"), "an inline script");
}

#[test]
fn a_write_whose_name_the_guard_cannot_read_withholds_every_global() {
    let code = "const k = ['op', 'en'].join('');\nwindow[k] = () => 1;\n";
    assert!(holds(&[("boot.js", code)], "open"));
    assert!(holds(&[("boot.js", code)], "Math"));
}

#[test]
fn a_file_that_replaces_no_global_keeps_the_proof() {
    let quiet = [
        (
            "vite.config.ts",
            "import { x } from 'vite';\nexport default { x };\n",
        ),
        (
            "tools/build.mjs",
            "export function open() {}\nconst m = { open: 1 };\nm.open = 2;\n",
        ),
        (
            "tools/env.js",
            "process.env.NODE_ENV = 'production';\ndocument.title = t;\n",
        ),
        (
            "tools/local.js",
            "let open = 1;\nfunction f() { open = 2; }\nexport { f };\n",
        ),
        (
            "page.html",
            "<script src=\"app.js\"></script>\n<script type=\"text/template\">open = 1</script>\n",
        ),
        (
            "module.html",
            "<script type=\"module\">\nconst open = 1;\n</script>\n",
        ),
    ];
    for (rel, code) in quiet {
        assert!(
            withheld(&[(rel, code)]).is_empty(),
            "{rel}: {:?}",
            withheld(&[(rel, code)])
        );
    }
}

#[test]
fn a_test_file_a_declaration_and_an_installed_package_are_not_read() {
    let write = "window.open = () => 1;\n";
    for rel in [
        "tests/setup.ts",
        "boot.test.ts",
        "types/global.d.ts",
        "node_modules/lib/index.js",
        ".storybook/preview.js",
    ] {
        assert!(withheld(&[(rel, write)]).is_empty(), "{rel}");
    }
}

#[test]
fn the_gap_cites_the_use_and_the_write() {
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", A),
        ("src/b.ts", B),
        (
            "boot.ts",
            "import { hidden } from './src/b';\nwindow.open = hidden as any;\n",
        ),
    ]);
    let facts = collect(&request(&tree, true), provenance());
    let gap = facts
        .gaps
        .iter()
        .find(|gap| gap.title.starts_with("Script global open is replaced"))
        .expect("a gap for open");
    let cited: Vec<String> = gap
        .evidence_ids
        .iter()
        .filter_map(|id| facts.evidence.iter().find(|e| &e.id == id))
        .map(|e| format!("{}:{}", e.file, e.line))
        .collect();
    assert!(cited.contains(&"boot.ts:2".to_owned()), "{cited:?}");
    assert!(
        cited.iter().any(|at| at.starts_with("src/a.ts:")),
        "{cited:?}"
    );
}
