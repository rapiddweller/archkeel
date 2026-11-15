// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use tree_sitter::{Language, Parser};

fn parse(text: &str) -> tree_sitter::Tree {
    let mut parser = Parser::new();
    parser.set_language(&super::LANGUAGE.into()).unwrap();
    parser.parse(text, None).unwrap()
}

#[test]
fn the_language_has_the_abi_of_the_vendored_parser() {
    // `parser.c` of tree-sitter-dart 0.1.0 defines LANGUAGE_VERSION 15.
    let language: Language = super::LANGUAGE.into();
    assert_eq!(language.abi_version(), 15);
}

#[test]
fn a_flutter_widget_parses_without_an_error() {
    let text = "import 'package:flutter/widgets.dart';\n\
        class Shop extends StatelessWidget {\n\
          const Shop({super.key});\n\
          @override\n\
          Widget build(BuildContext context) => const Text('shop');\n\
        }\n";
    let tree = parse(text);
    let root = tree.root_node();
    assert_eq!(root.kind(), "program");
    assert!(!root.has_error(), "{}", root.to_sexp());
}

#[test]
fn the_external_scanner_reads_a_block_comment_and_a_template() {
    let tree = parse("/** doc */\nvar a = 'x ${b} y';\n");
    let sexp = tree.root_node().to_sexp();
    assert!(sexp.contains("(documentation_comment)"), "{sexp}");
    assert!(sexp.contains("(template_substitution"), "{sexp}");
}

#[test]
fn the_runtime_has_the_abi_that_was_measured() {
    // AD-342: a runtime bump that moves the parser ABI must show here, and the vendored grammar
    // must be measured again with the new runtime before this number changes.
    assert_eq!(tree_sitter::LANGUAGE_VERSION, 15);
    assert_eq!(tree_sitter::MIN_COMPATIBLE_LANGUAGE_VERSION, 13);
}

#[test]
fn a_source_that_the_grammar_cannot_parse_has_an_error_or_a_missing_node() {
    // AD-342: the collector turns each error and missing node into a named gap, never a PASS.
    for text in [
        "class A {\n",
        "class class class;\n",
        "void f( {\n",
        "import 'a.dart'\nclass B {}\n",
    ] {
        assert!(parse(text).root_node().has_error(), "{text}");
    }
}

/// The digest of the file, as the table of `vendor/README.md` writes it.
fn digest(path: &std::path::Path) -> String {
    use sha2::{Digest, Sha256};
    let bytes = std::fs::read(path).unwrap();
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn the_vendored_files_are_the_files_of_the_recorded_release() {
    // AD-342: the grammar is gated by this test. A changed byte, a new file or a missing file
    // fails it; a new release needs a new table in the same change.
    let vendor = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("vendor");
    let readme = std::fs::read_to_string(vendor.join("README.md")).unwrap();
    let mut recorded: Vec<(String, String)> = readme
        .lines()
        .filter_map(|line| {
            let cells: Vec<&str> = line.split('|').map(str::trim).collect();
            let path = cells.get(1)?.strip_prefix('`')?.strip_suffix('`')?;
            let sha = cells.get(2)?.strip_prefix('`')?.strip_suffix('`')?;
            (sha.len() == 64).then(|| (path.to_owned(), sha.to_owned()))
        })
        .collect();
    recorded.sort();
    assert_eq!(recorded.len(), 8, "{recorded:?}");
    let mut found: Vec<(String, String)> = Vec::new();
    let mut pending = vec![vendor.clone()];
    while let Some(directory) = pending.pop() {
        for entry in std::fs::read_dir(&directory).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                pending.push(path);
            } else if path.file_name().is_some_and(|name| name != "README.md") {
                let relative = path
                    .strip_prefix(&vendor)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                found.push((relative, digest(&path)));
            }
        }
    }
    found.sort();
    assert_eq!(found, recorded);
}
