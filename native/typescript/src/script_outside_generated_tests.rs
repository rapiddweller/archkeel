// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the repository guard of AD-788 and a generated copy of a scanned source (#1735
// follow-up). `src/a.ts` calls `window.open()`. `dist/a.runtime.js`, outside the scan roots,
// writes `window.open` and states that it is generated from `src/a.ts`. The statement holds only
// when the digest is the digest of the source and the generator and the check are files; then the
// copy is the code of its source and the premise says so. Otherwise the copy is read.

use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str = "window.open();\nexport {};\n";

fn copy(source: &str, digest: &str, check: &str) -> String {
    format!(
        "window.open = () => 1;\n\n// Generated from {source}; source-sha256={digest}\n\
         // Owner: tools/gen.py. Edit the source.\n// Check: {check}\n"
    )
}

/// Whether the guard withholds `open`.
fn holds(runtime: &str) -> bool {
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", A),
        ("tools/gen.py", "print(1)\n"),
        ("tools/check.py", "print(1)\n"),
        ("dist/a.runtime.js", runtime),
    ]);
    let facts = collect(&request(&tree, true), provenance());
    facts
        .gaps
        .iter()
        .any(|gap| gap.title.starts_with("Script global open "))
}

#[test]
fn a_stated_generated_copy_is_the_code_of_its_source() {
    let digest = sha256_hex(A.as_bytes());
    assert!(
        !holds(&copy("../src/a.ts", &digest, "tools/check.py")),
        "a stated copy"
    );
}

#[test]
fn a_statement_that_does_not_hold_leaves_the_copy_read() {
    let digest = sha256_hex(A.as_bytes());
    let stale = "0".repeat(64);
    for (name, runtime) in [
        (
            "stale digest",
            copy("../src/a.ts", &stale, "tools/check.py"),
        ),
        ("no check", copy("../src/a.ts", &digest, "tools/missing.py")),
        (
            "source outside the roots",
            copy(
                "../tools/gen.py",
                &sha256_hex(b"print(1)\n"),
                "tools/check.py",
            ),
        ),
        ("no statement", "window.open = () => 1;\n".to_owned()),
    ] {
        assert!(holds(&runtime), "{name}");
    }
}
