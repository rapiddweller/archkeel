// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text of a written type, in the form that `ast.unparse` writes (AD-550).
//!
//! An exact exception of a rule matches this text, so it must equal the reference text for the
//! forms that annotations use: names, dotted names, subscripts, a chain of `|`, `None`, `...`, a
//! plain string, an integer, a boolean and a list of those. Any other form has no text here, and
//! the shape of it is `Unreadable`: the collector never guesses a text.

use ruff_python_ast::{Expr, Number, Operator, UnaryOp};

/// The text of `expr`, or `None` for a form that this writer does not write.
pub(super) fn render(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(node) => Some(node.id.to_string()),
        Expr::Attribute(node) => Some(format!("{}.{}", render(&node.value)?, node.attr.as_str())),
        Expr::NoneLiteral(_) => Some("None".to_owned()),
        Expr::EllipsisLiteral(_) => Some("...".to_owned()),
        Expr::BooleanLiteral(node) => Some(if node.value { "True" } else { "False" }.to_owned()),
        Expr::NumberLiteral(node) => match &node.value {
            Number::Int(value) => Some(value.to_string()),
            _ => None,
        },
        Expr::UnaryOp(node) if node.op == UnaryOp::USub => match &*node.operand {
            Expr::NumberLiteral(inner) => match &inner.value {
                Number::Int(value) => Some(format!("-{value}")),
                _ => None,
            },
            _ => None,
        },
        Expr::StringLiteral(node) => quote(node.value.to_str()),
        Expr::Subscript(node) => {
            let head = render(&node.value)?;
            let inner = match &*node.slice {
                Expr::Tuple(items) if items.elts.len() > 1 => join(&items.elts)?,
                Expr::Tuple(_) => return None,
                other => render(other)?,
            };
            Some(format!("{head}[{inner}]"))
        }
        Expr::List(node) => Some(format!("[{}]", join(&node.elts)?)),
        Expr::BinOp(node) if node.op == Operator::BitOr => {
            let left = render(&node.left)?;
            let right = render(&node.right)?;
            // `a | (b | c)` keeps its parentheses: the operator is left associative.
            Some(match &*node.right {
                Expr::BinOp(_) => format!("{left} | ({right})"),
                _ => format!("{left} | {right}"),
            })
        }
        _ => None,
    }
}

fn join(items: &[Expr]) -> Option<String> {
    let parts: Option<Vec<String>> = items.iter().map(render).collect();
    Some(parts?.join(", "))
}

/// A string with no character that `repr` escapes or switches the quote for.
fn quote(value: &str) -> Option<String> {
    let plain = value
        .chars()
        .all(|c| c.is_ascii_graphic() && !matches!(c, '\'' | '"' | '\\') || c == ' ');
    plain.then(|| format!("'{value}'"))
}
