// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A string that Python evaluates as code (AD-1095, #1974). `typing.get_type_hints`,
//! `inspect.signature(eval_str=True)` and `ForwardRef` evaluate a string annotation in the global
//! names of its module, so `x: "__import__('app.lib')"` imports `app.lib`. The survey reads the
//! text as code: the same rules find each hazard in it, and the site stands at the string.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ExprStringLiteral, Identifier, ModModule, Operator, Stmt};

use crate::parse::Unread;

#[path = "hazards_annotation_class.rs"]
pub(in crate::survey::hazards) mod class;
#[path = "hazards_annotation_forms.rs"]
mod forms;
#[path = "hazards_annotation_imports.rs"]
mod imports;

pub(in crate::survey::hazards) use forms::literal;

/// What `expr` evaluates as code: a string in an annotation, the first argument of `ForwardRef`,
/// or a name in an annotation that the module assigns a string.
pub(super) enum Text<'a> {
    None,
    Literal(&'a ExprStringLiteral),
    Held(Vec<ExprStringLiteral>),
    Opaque,
}

pub(super) fn evaluated<'a>(expr: &'a Expr, in_annotation: bool, strings: &Strings) -> Text<'a> {
    match expr {
        Expr::StringLiteral(text) if in_annotation => Text::Literal(text),
        Expr::Call(call) => forward_ref(call).map_or(Text::None, Text::Literal),
        Expr::Name(_) | Expr::Attribute(_) if in_annotation => {
            match strings.held(forms::last(expr).unwrap_or_default()) {
                Held::None => Text::None,
                Held::Texts(texts) => Text::Held(texts.to_vec()),
                Held::Opaque => Text::Opaque,
            }
        }
        _ => Text::None,
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

/// The expression that the text of `string` evaluates to. A text over the parser bound is a gap
/// (`Unread::Bound`): CPython can evaluate it.
pub(super) fn parsed(string: &ExprStringLiteral) -> Result<Expr, Unread> {
    crate::parse::expression(string.value.to_str())
}

/// True for a store to `__annotations__` (`K.__annotations__ = ..`, `f.__annotations__[k] = ..`,
/// `__annotations__[k] = ..`) or a call that changes it. `get_type_hints` evaluates a string
/// that such a write puts there, and no annotation position holds the string.
pub(super) fn writes_annotations(stmt: &Stmt) -> bool {
    fn target(expr: &Expr) -> bool {
        match expr {
            Expr::Subscript(node) => target(&node.value),
            Expr::Attribute(node) => Identifier::as_str(&node.attr) == "__annotations__",
            Expr::Name(node) => node.id.as_str() == "__annotations__",
            Expr::Tuple(node) => node.elts.iter().any(target),
            Expr::List(node) => node.elts.iter().any(target),
            Expr::Starred(node) => target(&node.value),
            _ => false,
        }
    }
    match stmt {
        Stmt::Assign(node) => node.targets.iter().any(target),
        Stmt::AugAssign(node) => target(&node.target),
        Stmt::AnnAssign(node) => node.value.is_some() && target(&node.target),
        Stmt::Delete(node) => node.targets.iter().any(target),
        Stmt::Expr(node) => match &*node.value {
            Expr::Call(call) => match &*call.func {
                Expr::Attribute(method) => target(&method.value),
                _ => false,
            },
            _ => false,
        },
        _ => false,
    }
}

/// The strings that a name holds, over the whole module (any scope: a gap is safe, a miss is not).
pub(super) struct Strings {
    texts: HashMap<String, Vec<ExprStringLiteral>>,
    /// A name that holds a string that the survey cannot read: an f-string, a join, a format.
    opaque: HashSet<String>,
}

const MAX_TEXTS: usize = 8;

fn names_a_held(texts: &[ExprStringLiteral], held: &HashSet<&String>) -> bool {
    let mut names = Names {
        found: HashSet::new(),
        depth: 0,
        deep: false,
    };
    for text in texts {
        match parsed(text) {
            Ok(code) => names.visit_expr(&code),
            Err(Unread::Bound) => names.deep = true,
            Err(Unread::Syntax) => {}
        }
    }
    names.deep || names.found.iter().any(|name| held.contains(name))
}

/// The names of a text and of the strings in it, to the depth of a nest of strings.
struct Names {
    found: HashSet<String>,
    depth: usize,
    deep: bool,
}

impl<'a> Visitor<'a> for Names {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) => {
                self.found.insert(node.id.to_string());
            }
            Expr::Attribute(node) => {
                self.found.insert(node.attr.to_string());
                visitor::walk_expr(self, expr);
            }
            Expr::StringLiteral(text) => match parsed(text) {
                Ok(code) if self.depth < 8 => {
                    self.depth += 1;
                    self.visit_expr(&code);
                    self.depth -= 1;
                }
                Ok(_) | Err(Unread::Bound) => self.deep = true,
                Err(Unread::Syntax) => {}
            },
            _ => visitor::walk_expr(self, expr),
        }
    }
}

pub(super) enum Held<'a> {
    None,
    Texts(&'a [ExprStringLiteral]),
    Opaque,
}

impl Strings {
    pub(super) fn of(tree: &ModModule) -> Self {
        let mut found = Self {
            texts: HashMap::new(),
            opaque: HashSet::new(),
        };
        found.visit_body(&tree.body);
        found.close();
        found
    }

    /// A held text that names a held name is opaque: the walk would expand `J = "list[J]"` for
    /// ever, and a chain of names needs no proof here (a gap is safe). The names are those of the
    /// parsed tree, so a normalized identifier (`Ｊ` for `J`) counts, and so does a name inside a
    /// nested string.
    fn close(&mut self) {
        let held: HashSet<&String> = self.texts.keys().chain(&self.opaque).collect();
        let chained: Vec<String> = self
            .texts
            .iter()
            .filter(|(_, texts)| names_a_held(texts, &held))
            .map(|(id, _)| id.clone())
            .collect();
        self.opaque.extend(chained);
    }

    pub(super) fn held(&self, id: &str) -> Held<'_> {
        if self.opaque.contains(id) {
            return Held::Opaque;
        }
        match self.texts.get(id) {
            Some(texts) => Held::Texts(texts),
            None => Held::None,
        }
    }

    fn bind(&mut self, target: &Expr, value: &Expr) {
        let Some(id) = forms::last(target) else {
            return;
        };
        let id = id.to_owned();
        if self.opaque.contains(&id) {
            return;
        }
        match value {
            Expr::StringLiteral(text) => {
                let list = self.texts.entry(id.clone()).or_default();
                if !list.iter().any(|t| t.value.to_str() == text.value.to_str()) {
                    list.push(text.clone());
                }
                // A name with many texts costs a parse for each text at each annotation.
                if list.len() > MAX_TEXTS {
                    self.texts.remove(&id);
                    self.opaque.insert(id);
                }
            }
            Expr::FString(_) => {
                self.opaque.insert(id);
            }
            Expr::BinOp(node) if matches!(node.op, Operator::Add | Operator::Mod) => {
                self.opaque.insert(id);
            }
            Expr::Call(call) => {
                if matches!(&*call.func, Expr::Attribute(f) if matches!(f.attr.as_str(), "format" | "join"))
                {
                    self.opaque.insert(id);
                }
            }
            _ => {}
        }
    }
}

impl<'a> Visitor<'a> for Strings {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        forms::assigned(stmt, |target, value| self.bind(target, value));
        visitor::walk_stmt(self, stmt);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_text_that_does_not_parse_has_no_expression() {
        let text = |source: &str| match crate::parse::expression(source) {
            Ok(Expr::Call(_)) => "call",
            Ok(_) => "other",
            Err(Unread::Syntax) => "none",
            Err(Unread::Bound) => "bound",
        };
        assert_eq!(text("__import__('a.b')"), "call");
        assert_eq!(text("  List[int]  "), "other");
        assert_eq!(text("not valid code ("), "none");
        assert_eq!(text("x = 1"), "none");
        // A bracket nest over the stack bound has no tree and must not overflow the stack.
        let deep = format!("{}int{}", "(".repeat(500_000), ")".repeat(500_000));
        assert_eq!(text(&deep), "bound");
        let nest = format!("{}int{}", "[".repeat(150), "]".repeat(150));
        assert_eq!(text(&nest), "bound");
    }
}
