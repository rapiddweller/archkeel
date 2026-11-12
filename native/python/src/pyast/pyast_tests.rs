// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

fn kinds(source: &str, minor: u32) -> Vec<&'static str> {
    let module = crate::parse::parse(source, minor).expect("the probe parses");
    module
        .body
        .iter()
        .flat_map(|stmt| walk(Node::Stmt(stmt), minor).map(|node| node.kind()))
        .collect()
}

#[test]
fn the_walk_is_breadth_first_with_contexts_and_operators() {
    assert_eq!(
        kinds("a, (b, c) = d + 1\n", 12),
        [
            "Assign", "Tuple", "BinOp", "Name", "Tuple", "Store", "Name", "Add", "Constant",
            "Store", "Name", "Name", "Store", "Load", "Store", "Store"
        ]
    );
}

#[test]
fn an_elif_is_an_if_in_the_orelse() {
    assert_eq!(
        kinds("if a:\n    pass\nelif b:\n    pass\nelse:\n    x\n", 12),
        ["If", "Name", "Pass", "If", "Load", "Name", "Pass", "Expr", "Load", "Name", "Load"]
    );
}

#[test]
fn the_type_params_are_fields_from_3_12() {
    assert_eq!(
        kinds("def f[T: int = str](): pass\n", 13),
        [
            "FunctionDef",
            "arguments",
            "Pass",
            "TypeVar",
            "Name",
            "Name",
            "Load",
            "Load"
        ]
    );
    assert_eq!(
        kinds("def f[T: int](): pass\n", 12),
        [
            "FunctionDef",
            "arguments",
            "Pass",
            "TypeVar",
            "Name",
            "Load"
        ]
    );
}

#[test]
fn an_fstring_joins_its_text_parts() {
    assert_eq!(
        kinds("'a' f'b{x=}' 'c'\n", 12),
        [
            "Expr",
            "JoinedStr",
            "Constant",
            "FormattedValue",
            "Constant",
            "Name",
            "Load"
        ]
    );
}
