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

/// The gaps of a project whose `src/a.ts` is `a`, with the files `more`.
fn titles(a: &str, more: &[(&str, &str)]) -> Vec<String> {
    let mut all = vec![("tsconfig.json", "{}"), ("src/a.ts", a)];
    all.extend_from_slice(more);
    let tree = Tree::new(&all);
    let facts = collect(&request(&tree, true), provenance());
    facts.gaps.iter().map(|gap| gap.title.clone()).collect()
}

#[test]
fn a_patch_withholds_the_uses_of_its_member_and_of_the_whole_global_only() {
    let b =
        "export function hidden(): any { return 1; }\nMath.max = hidden;\ndocument.title = t;\n\
             declare const t: string;\n";
    let other = titles("export const m = Math.min(1, 2);\n", &[("src/b.ts", b)]);
    assert!(
        !other.iter().any(|t| t.starts_with("Script global Math ")),
        "{other:?}"
    );
    let whole = titles(
        "declare function keep(x: any): void;\nkeep(Math);\n",
        &[("src/b.ts", b)],
    );
    assert!(
        whole
            .iter()
            .any(|t| t == "Script global Math is patched by a member write"),
        "{whole:?}"
    );
    let read = titles(
        "export const n = document.getElementById('x');\n",
        &[("src/b.ts", b)],
    );
    assert!(
        !read
            .iter()
            .any(|t| t.starts_with("Script global document ")),
        "{read:?}"
    );
    let deep = "declare const v: string;\ndocument.body.style.overflow = v;\nexport {};\n";
    let sibling = titles("document.body.append('x');\n", &[("src/b.ts", deep)]);
    assert!(
        !sibling
            .iter()
            .any(|t| t.starts_with("Script global document ")),
        "{sibling:?}"
    );
    let below = titles(
        "export const o = document.body.style.overflow;\n",
        &[("src/b.ts", deep)],
    );
    assert!(
        below
            .iter()
            .any(|t| t.starts_with("Script global document is patched")),
        "{below:?}"
    );
    let title = titles("export const s = document.title;\n", &[("src/b.ts", b)]);
    assert!(
        title
            .iter()
            .any(|t| t.starts_with("Script global document is patched")),
        "{title:?}"
    );
}

#[test]
fn a_long_call_chain_is_scanned_in_linear_time() {
    // Before the fix, each link copied its whole subtree: 50,000 links took minutes in a debug build.
    let chain = format!("export const v = a{};\n", ".b()".repeat(50_000));
    let start = std::time::Instant::now();
    holds(&[("src/b.ts", &chain)], "Math");
    assert!(start.elapsed().as_secs() < 60, "{:?}", start.elapsed());
}

// AD-1470: a member write whose value can be no function patches no call. A literal was already
// such a value (#1674); a choice of literals and an assignment of one are too. A value from a
// call, a name or a member stays a possible function, and so does one branch of a choice.
const READS_THEME: &str = "export const t = document.documentElement.dataset.theme;\n\
                           export const e = new Error('x');\n";
const HIDDEN: &str = "export function hidden(): any { return 1; }\n";

fn holds_document(files: &[(&str, &str)]) -> bool {
    titles(READS_THEME, files)
        .iter()
        .any(|title| title.starts_with("Script global document "))
}

fn holds_error(files: &[(&str, &str)]) -> bool {
    titles(READS_THEME, files)
        .iter()
        .any(|title| title.starts_with("Script global Error "))
}

#[test]
fn a_choice_of_literals_patches_no_call_in_a_scanned_file_and_outside() {
    let toggle = "declare const dark: boolean;\n\
                  document.documentElement.dataset.theme = dark ? 'light' : 'dark';\nexport {};\n";
    assert!(!holds_document(&[("src/b.ts", toggle)]), "scanned");
    assert!(
        !holds_document(&[(
            "boot.js",
            &toggle
                .replace("declare const dark: boolean;\n", "var dark = 1;\n")
                .replace("export {};\n", "")
        )]),
        "outside"
    );
    let nested = "declare const a: boolean, b: boolean;\n\
                  document.documentElement.dataset.theme = a ? 'x' : (b ? 'y' : 'z');\nexport {};\n";
    assert!(!holds_document(&[("src/b.ts", nested)]), "a nested choice");
}

#[test]
fn an_assignment_chain_of_a_literal_patches_no_call_outside() {
    // The ELK form: the member of `Error` gets a number twice in one statement.
    let chain = "Error.stackTraceLimit = Error.stackTraceLimit = 64;\n";
    assert!(!holds_error(&[("boot.js", chain)]));
    assert!(!holds_error(&[(
        "boot.js",
        "Error.stackTraceLimit = 64;\n"
    )]));
}

#[test]
fn a_possible_function_still_withholds_the_proof() {
    for patch in [
        "document.documentElement.dataset.theme = pick();",
        "document.documentElement.dataset.theme = dark ? 'light' : hidden;",
        "document.documentElement.dataset.theme = dark ? hidden : 'dark';",
        "document.documentElement.dataset.theme = other.theme;",
        "document.documentElement.dataset.theme = (dark ? 'a' : 'b') || hidden;",
        "document.documentElement.dataset.theme = value = hidden;",
    ] {
        let b = format!(
            "{HIDDEN}declare const dark: boolean, other: any, value: any;\n\
             declare function pick(): any;\n{patch}\nexport {{}};\n"
        );
        assert!(holds_document(&[("src/b.ts", &b)]), "scanned: {patch}");
        let outside = format!("import {{ hidden }} from './src/b';\n{patch}\n");
        let files = [("src/b.ts", HIDDEN), ("boot.ts", outside.as_str())];
        assert!(holds_document(&files), "outside: {patch}");
    }
}

#[test]
fn a_path_that_any_other_write_gives_a_function_stays_withheld_outside() {
    let mixed = "import { hidden } from './src/b';\nError.stackTraceLimit = 64;\n\
                 Error.stackTraceLimit = hidden;\n";
    assert!(holds_error(&[("src/b.ts", HIDDEN), ("boot.ts", mixed)]));
    let other_member = "import { hidden } from './src/b';\nError.stackTraceLimit = 64;\n\
                        Error.captureStackTrace = hidden;\n";
    assert!(holds_error(&[
        ("src/b.ts", HIDDEN),
        ("boot.ts", other_member)
    ]));
}
