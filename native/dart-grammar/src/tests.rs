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
