// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A string that Python evaluates as code (AD-1095, #1974). `typing.get_type_hints`,
//! `inspect.signature(eval_str=True)` and `ForwardRef` evaluate a string annotation in the global
//! names of its module, so `x: "__import__('app.lib')"` imports `app.lib`. The survey reads the
//! text as code: the same rules find each hazard in it, and the site stands at the string.

use ruff_python_ast::{Expr, ExprCall, ExprStringLiteral, Identifier};

/// The string of `expr` that Python can evaluate: a string in an annotation, or the first
/// argument of `ForwardRef`.
pub(super) fn evaluated(expr: &Expr, in_annotation: bool) -> Option<&ExprStringLiteral> {
    match expr {
        Expr::StringLiteral(text) if in_annotation => Some(text),
        Expr::Call(call) => forward_ref(call),
        _ => None,
    }
}

fn forward_ref(call: &ExprCall) -> Option<&ExprStringLiteral> {
    let callee = match &*call.func {
        Expr::Name(node) => node.id.as_str(),
        Expr::Attribute(node) => Identifier::as_str(&node.attr),
        _ => return None,
    };
    match call.arguments.args.first() {
        Some(Expr::StringLiteral(text)) if callee == "ForwardRef" => Some(text),
        _ => None,
    }
}

/// True for `Literal` and `typing.Literal`: its strings are values, no annotation.
pub(super) fn literal(value: &Expr) -> bool {
    match value {
        Expr::Name(node) => node.id.as_str() == "Literal",
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == "Literal",
        _ => false,
    }
}

/// The expression that the text of `string` evaluates to, if it parses.
pub(super) fn parsed(string: &ExprStringLiteral) -> Option<Expr> {
    crate::parse::expression(string.value.to_str())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_text_that_does_not_parse_has_no_expression() {
        let text = |source: &str| match crate::parse::expression(source) {
            Some(Expr::Call(_)) => "call",
            Some(_) => "other",
            None => "none",
        };
        assert_eq!(text("__import__('a.b')"), "call");
        assert_eq!(text("  List[int]  "), "other");
        assert_eq!(text("not valid code ("), "none");
        assert_eq!(text("x = 1"), "none");
        // A bracket nest over the stack bound has no tree and must not overflow the stack.
        let deep = format!("{}int{}", "(".repeat(500_000), ")".repeat(500_000));
        assert_eq!(text(&deep), "none");
    }
}
