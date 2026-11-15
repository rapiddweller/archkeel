// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Count written typing positions and dynamic typing calls.

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprAttribute, ExprContext, Stmt};
use ruff_text_size::{Ranged, TextSize};

use super::binders::Binders;
use crate::module::Module;

pub(super) fn count(module: &Module, binders: &Binders) -> (u64, u64) {
    let unique = binders.unique();
    let imported: std::collections::HashSet<String> = module
        .tree
        .body
        .iter()
        .filter(|stmt| matches!(stmt, Stmt::Import(_)))
        .flat_map(crate::module::import_bindings)
        .filter(|name| unique.contains(name))
        .collect();
    let casts = module
        .tree
        .body
        .iter()
        .filter_map(|stmt| match stmt {
            Stmt::ImportFrom(node)
                if node
                    .module
                    .as_ref()
                    .is_some_and(|name| name.as_str() == "typing")
                    && node.level == 0 =>
            {
                Some(&node.names)
            }
            _ => None,
        })
        .flatten()
        .filter(|alias| alias.name.as_str() == "cast")
        .map(|alias| {
            alias
                .asname
                .as_ref()
                .unwrap_or(&alias.name)
                .as_str()
                .to_owned()
        })
        .collect();
    let typing_modules = module
        .tree
        .body
        .iter()
        .filter_map(|stmt| match stmt {
            Stmt::Import(node) => Some(&node.names),
            _ => None,
        })
        .flatten()
        .filter(|alias| alias.name.as_str() == "typing")
        .map(|alias| {
            alias
                .asname
                .as_ref()
                .unwrap_or(&alias.name)
                .as_str()
                .to_owned()
        })
        .collect();
    let mut walk = Typing {
        imported,
        casts,
        typing_modules,
        count: 0,
        private: 0,
        public: true,
        class: false,
        method: false,
        receiver: None,
        method_body: None,
    };
    walk.visit_body(&module.tree.body);
    (walk.count, walk.private)
}

struct Typing {
    imported: std::collections::HashSet<String>,
    casts: std::collections::HashSet<String>,
    typing_modules: std::collections::HashSet<String>,
    count: u64,
    private: u64,
    public: bool,
    class: bool,
    method: bool,
    receiver: Option<String>,
    method_body: Option<(TextSize, TextSize)>,
}

impl<'a> Visitor<'a> for Typing {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let before = self.public;
        let old_class = self.class;
        let old_method = self.method;
        let old_receiver = self.receiver.clone();
        let old_body = self.method_body;
        match stmt {
            Stmt::FunctionDef(node) => {
                self.method = self.class;
                self.class = false;
                self.receiver = node
                    .parameters
                    .posonlyargs
                    .first()
                    .or_else(|| node.parameters.args.first())
                    .map(|arg| arg.parameter.name.as_str())
                    .filter(|name| {
                        self.method
                            && node.decorator_list.is_empty()
                            && matches!(*name, "self" | "cls")
                    })
                    .map(str::to_owned);
                self.method_body = node
                    .body
                    .first()
                    .zip(node.body.last())
                    .map(|(first, last)| (first.start(), last.end()));
                self.public &= !node.name.as_str().starts_with('_');
                let all = node.parameters.iter().map(|arg| arg.as_parameter());
                let receiver = self.receiver.clone();
                for (_, parameter) in all.enumerate().filter(|(index, parameter)| {
                    !(*index == 0 && receiver.as_deref() == Some(parameter.name.as_str()))
                }) {
                    self.count += position(parameter.annotation.as_deref(), self.public);
                }
                self.count += position(node.returns.as_deref(), self.public);
            }
            Stmt::ClassDef(node) => {
                self.public &= !node.name.as_str().starts_with('_');
                self.class = true;
                self.method = false;
                self.receiver = None;
                self.method_body = None;
            }
            Stmt::AugAssign(node) => {
                if let Expr::Attribute(attr) = &*node.target {
                    self.private += u64::from(self.private_read(attr));
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
        self.public = before;
        self.class = old_class;
        self.method = old_method;
        self.receiver = old_receiver;
        self.method_body = old_body;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Attribute(attr) = expr {
            if attr.ctx == ExprContext::Load {
                self.private += u64::from(self.private_read(attr));
            }
        }
        let callee = match expr {
            Expr::Call(call) => match &*call.func {
                Expr::Name(name) => Some(name.id.as_str()),
                _ => None,
            },
            _ => None,
        };
        if let Some(name) = callee {
            self.count +=
                u64::from(matches!(name, "getattr" | "eval" | "exec") || self.casts.contains(name));
        }
        if let Expr::Call(call) = expr {
            let typing_cast = matches!(&*call.func, Expr::Attribute(attr)
                if attr.attr.as_str() == "cast" && matches!(&*attr.value, Expr::Name(name)
                    if self.typing_modules.contains(name.id.as_str())));
            self.count += u64::from(typing_cast);
        }
        visitor::walk_expr(self, expr);
    }
}

impl Typing {
    fn private_read(&self, attr: &ExprAttribute) -> bool {
        let exempt = matches!(&*attr.value, Expr::Name(name)
            if (self.receiver.as_deref() == Some(name.id.as_str())
                && self.method_body.is_some_and(|(start, end)| start <= attr.start() && attr.end() <= end))
            || self.imported.contains(name.id.as_str()));
        attr.attr.as_str().starts_with('_') && !exempt
    }
}

fn position(annotation: Option<&Expr>, public: bool) -> u64 {
    let Some(annotation) = annotation else {
        return u64::from(public);
    };
    if let Expr::StringLiteral(text) = annotation {
        return u64::from(
            text.value
                .to_str()
                .split(|ch: char| !ch.is_alphanumeric() && ch != '_')
                .any(|name| matches!(name, "object" | "Any")),
        );
    }
    let mut scan = Untyped(false);
    scan.visit_expr(annotation);
    u64::from(scan.0)
}

struct Untyped(bool);
impl<'a> Visitor<'a> for Untyped {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(name) = expr {
            self.0 |= matches!(name.id.as_str(), "object" | "Any") && name.ctx == ExprContext::Load;
        }
        if let Expr::Attribute(attribute) = expr {
            self.0 |= matches!(attribute.attr.as_str(), "object" | "Any");
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
mod tests {
    use super::count;
    use crate::survey::binders::Binders;

    #[test]
    fn counts_missing_public_positions_and_written_untyped_annotations() {
        let module = crate::test_module(
            "def public(a, b: object) -> Any:\n    pass\ndef _private(x):\n    pass\n",
            11,
        );
        let binders = Binders::of(&module.tree);
        assert_eq!(count(&module, &binders).0, 3);
    }

    #[test]
    fn counts_each_dynamic_call_and_the_private_access() {
        let module = crate::test_module("from typing import cast\ndef f(a: int) -> int:\n    getattr(a, 'x')\n    eval('1')\n    exec('x=1')\n    cast(int, a)\n    return a._hidden\n", 11);
        let binders = Binders::of(&module.tree);
        assert_eq!(count(&module, &binders), (4, 1));
    }

    #[test]
    fn augmented_assignment_reads_the_private_attribute() {
        let module = crate::test_module("def f(a):\n    a._value += 1\n", 11);
        let binders = Binders::of(&module.tree);
        assert_eq!(count(&module, &binders).1, 1);
    }

    #[test]
    fn a_plain_typing_module_import_identifies_cast() {
        let module = crate::test_module(
            "import typing as t\ndef f() -> int:\n    return t.cast(int, 1)\n",
            11,
        );
        let binders = Binders::of(&module.tree);
        assert_eq!(count(&module, &binders).0, 1);
    }

    #[test]
    fn quoted_builtin_and_any_annotations_are_untyped() {
        let module = crate::test_module("def f(x: 'object') -> 'typing.Any':\n    pass\n", 11);
        let binders = Binders::of(&module.tree);
        assert_eq!(count(&module, &binders).0, 2);
    }
}
