// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The hazard sites of a Python file of the repository outside the scan (#1522, AD-770).
//!
//! A door can give the object of a module of the scan by its name. The file then spells the name
//! in a string, so each module that a string of the file names escapes (`named`). A name that the
//! file does not spell comes from data or from other code: the stated premise of the run covers it.
//!
//! Two forms give no module of the scan (`harmless`):
//! - `import_module(name)` or `__import__(name)` where each value that `name` can have is a text,
//!   or starts with a text, that is not a module of the scan, no package above one, and no prefix
//!   of one: `f"fixtures.demo_{x}"`, `"a" if c else "b"`. A name that starts with `.` is relative,
//!   so it is no such text.
//! - `exec`, `eval` or `compile` of a literal text whose code has no name, no attribute, no call
//!   and no subscript: `eval("1 + 1")`, `exec("pass")`.

use std::collections::HashSet;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Expr, ExprCall, FStringPartRef, InterpolatedStringElement, InterpolatedStringElements,
    Operator, Stmt,
};
use ruff_text_size::{Ranged, TextRange};

use super::super::hazards::Site;
use super::native::reached;
use crate::module::Module;
use crate::parse::parse;

/// True when the site cannot give a module of `names`.
pub(super) fn harmless(site: &Site, module: &Module, names: &HashSet<String>) -> bool {
    let Some(call) = call_at(module, site.range) else {
        return false;
    };
    let last = site.detail.rsplit('.').next().unwrap_or_default();
    match last {
        "import_module" | "__import__" => {
            let relative = last == "__import__"
                && (call.arguments.args.len() > 4
                    || call.arguments.find_keyword("level").is_some());
            let name = call
                .arguments
                .args
                .first()
                .or_else(|| call.arguments.find_keyword("name").map(|k| &k.value));
            !relative && name.is_some_and(|name| foreign(name, names))
        }
        "exec" | "eval" | "compile" => match call.arguments.args.first() {
            Some(Expr::StringLiteral(text)) => inert(text.value.to_str()),
            _ => false,
        },
        _ => false,
    }
}

/// The modules of `names` that a string of `module` reaches (`native::reached`).
pub(super) fn named(module: &Module, names: &HashSet<String>) -> Vec<String> {
    struct Strings<'n>(&'n HashSet<String>, Vec<String>);
    impl<'a> Visitor<'a> for Strings<'_> {
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::StringLiteral(text) = expr {
                self.1.extend(reached(text.value.to_str().trim(), self.0));
            }
            visitor::walk_expr(self, expr);
        }
    }
    let mut found = Strings(names, Vec::new());
    found.visit_body(&module.tree.body);
    found.1
}

/// The call whose callee is the expression at `range`.
fn call_at(module: &Module, range: TextRange) -> Option<&ExprCall> {
    struct Find<'a> {
        range: TextRange,
        found: Option<&'a ExprCall>,
    }
    impl<'a> Visitor<'a> for Find<'a> {
        fn visit_expr(&mut self, expr: &'a Expr) {
            match expr {
                Expr::Call(call) if call.func.range() == self.range => self.found = Some(call),
                _ => visitor::walk_expr(self, expr),
            }
        }
    }
    let mut find = Find { range, found: None };
    find.visit_body(&module.tree.body);
    find.found
}

/// True when each value that `expr` can have is no name of a module of `names`.
fn foreign(expr: &Expr, names: &HashSet<String>) -> bool {
    heads(expr).is_some_and(|heads| {
        heads.iter().all(|(head, exact)| {
            !head.starts_with('.') && (*exact || !head.is_empty()) && !meets(head, *exact, names)
        })
    })
}

/// True when a name that is `head`, or that starts with `head`, can name a module of `names`.
fn meets(head: &str, exact: bool, names: &HashSet<String>) -> bool {
    names.iter().any(|name| {
        let under = head == name || head.starts_with(&format!("{name}."));
        let above = if exact {
            name.starts_with(&format!("{head}."))
        } else {
            name.starts_with(head)
        };
        under || above
    })
}

/// The texts that each value of `expr` is (`true`) or starts with (`false`); `None` when a value
/// can be any text.
fn heads(expr: &Expr) -> Option<Vec<(String, bool)>> {
    match expr {
        Expr::StringLiteral(text) => Some(vec![(text.value.to_str().to_owned(), true)]),
        Expr::FString(node) => Some(vec![(fstring_head(node), false)]),
        Expr::If(node) => {
            let mut found = heads(&node.body)?;
            found.extend(heads(&node.orelse)?);
            Some(found)
        }
        Expr::BinOp(node) if matches!(node.op, Operator::Add | Operator::Mod) => {
            let left = heads(&node.left)?;
            let cut = |text: &str| match node.op {
                Operator::Mod => text.split('%').next().unwrap_or_default().to_owned(),
                _ => text.to_owned(),
            };
            Some(
                left.into_iter()
                    .map(|(text, _)| (cut(&text), false))
                    .collect(),
            )
        }
        Expr::Call(node) => match &*node.func {
            Expr::Attribute(attribute) if attribute.attr.as_str() == "format" => {
                let Expr::StringLiteral(text) = &*attribute.value else {
                    return None;
                };
                let head = text.value.to_str().split('{').next().unwrap_or_default();
                Some(vec![(head.to_owned(), false)])
            }
            _ => None,
        },
        _ => None,
    }
}

/// The literal text before the first field of an f-string.
fn fstring_head(node: &ruff_python_ast::ExprFString) -> String {
    let mut head = String::new();
    for part in node.value.iter() {
        let open = match part {
            FStringPartRef::Literal(literal) => {
                head.push_str(&literal.value);
                true
            }
            FStringPartRef::FString(fstring) => literal_elements(&mut head, &fstring.elements),
        };
        if !open {
            break;
        }
    }
    head
}

/// Add the literal elements before the first field to `head`; `false` at a field.
fn literal_elements(head: &mut String, elements: &InterpolatedStringElements) -> bool {
    for element in elements.iter() {
        match element {
            InterpolatedStringElement::Literal(literal) => head.push_str(&literal.value),
            InterpolatedStringElement::Interpolation(_) => return false,
        }
    }
    true
}

/// True when the code `text` names nothing: each statement is `pass` or an expression without a
/// name, an attribute, a call or a subscript.
fn inert(text: &str) -> bool {
    struct Names(bool);
    impl<'a> Visitor<'a> for Names {
        fn visit_expr(&mut self, expr: &'a Expr) {
            self.0 |= matches!(
                expr,
                Expr::Name(_)
                    | Expr::Attribute(_)
                    | Expr::Call(_)
                    | Expr::Subscript(_)
                    | Expr::Named(_)
                    | Expr::Lambda(_)
            );
            visitor::walk_expr(self, expr);
        }
    }
    let Ok(tree) = parse(text, PyMinor::Py314) else {
        return false;
    };
    let mut names = Names(false);
    for stmt in &tree.body {
        match stmt {
            Stmt::Pass(_) => {}
            Stmt::Expr(node) => names.visit_expr(&node.value),
            _ => return false,
        }
    }
    !names.0
}
