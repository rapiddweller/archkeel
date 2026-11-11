// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::parse::parse;
use crate::survey::imports::Alias;

fn expression(text: &str) -> Expr {
    let tree = parse(text, 13).expect("valid source");
    let statement = tree
        .body
        .first()
        .and_then(|statement| statement.as_expr_stmt());
    (*statement.expect("an expression statement").value).clone()
}

fn aliases() -> Aliases {
    let alias = |target: &str, module| Alias {
        target: target.to_owned(),
        module,
    };
    Aliases::from([
        ("b".to_owned(), alias("builtins", true)),
        ("e".to_owned(), alias("builtins.eval", false)),
    ])
}

#[test]
fn a_name_path_resolves_through_the_module_aliases() {
    let found = |text: &str| resolve(&expression(text), &aliases());
    assert_eq!(found("e").as_deref(), Some("builtins.eval"));
    assert_eq!(found("b.globals").as_deref(), Some("builtins.globals"));
    assert_eq!(found("x.b").as_deref(), Some("x.b"));
}

#[test]
fn a_node_that_is_no_name_path_resolves_to_nothing() {
    for text in ["f().eval", "x[0].globals", "'globals'", "(lambda: 0)"] {
        assert_eq!(resolve(&expression(text), &aliases()), None, "{text}");
    }
}
