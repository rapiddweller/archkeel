// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the proof that a standard global of the scan is the native one (#1668 review). File A
// calls `Math.max`, `JSON.parse` and `console.log`. Another file writes a member of one of these
// globals with a function of the scan: then A calls that function, which the scan does not see
// as an edge. Truth: node v26 runs `Math.max = () => 777; Math.max(1, 2)` and gives 777. The
// write must withhold the proof of that global, in a scanned file and in a repository file
// outside the scan roots; a literal value (no function of the scan) and a local object keep it.

use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "export const m = Math.max(1, 2);\nexport const j = JSON.parse('1');\n\
                 console.log(m, j);\n";

/// The project has a gap that holds the global `name`.
fn holds(files: &[(&str, &str)], name: &str) -> bool {
    let mut all = vec![("tsconfig.json", "{}"), ("src/a.ts", A)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    let facts = collect(&request(&tree, true), provenance());
    facts.gaps.iter().any(|gap| {
        gap.title.starts_with(&format!("Script global {name} "))
            || gap
                .title
                .starts_with("A form that can write any global keeps every")
    })
}

const PATCHES: [(&str, &str); 6] = [
    ("Math.max = hidden as any;", "Math"),
    ("JSON.parse = hidden as any;", "JSON"),
    ("console.log = hidden;", "console"),
    ("(Math as any)['max'] = hidden;", "Math"),
    ("Object.assign(Math, { max: hidden });", "Math"),
    (
        "Object.defineProperty(JSON, 'parse', { value: hidden });",
        "JSON",
    ),
];

#[test]
fn a_scanned_member_patch_of_a_standard_global_withholds_its_proof() {
    for (patch, name) in PATCHES {
        let b = format!("export function hidden(): any {{ return 1; }}\n{patch}\n");
        assert!(holds(&[("src/b.ts", &b)], name), "{patch}");
    }
}

#[test]
fn an_outside_member_patch_of_a_standard_global_withholds_its_proof() {
    for (patch, name) in PATCHES {
        let boot = format!(
            "import {{ hidden }} from './src/b';\n{}\n",
            patch.replace(" as any", "")
        );
        let files = [
            ("src/b.ts", "export function hidden(): any { return 1; }\n"),
            ("boot.ts", boot.as_str()),
        ];
        assert!(holds(&files, name), "{patch}");
    }
}

#[test]
fn a_literal_or_a_local_object_keeps_the_proof() {
    for b in [
        "export const t = 1;\ndocument.title = 'x';\n",
        "export const o: any = { max: 1 };\no.max = () => 2;\n",
        "export function f(Math: any) { Math.max = () => 2; }\n",
    ] {
        assert!(!holds(&[("src/b.ts", b)], "Math"), "{b}");
    }
}
