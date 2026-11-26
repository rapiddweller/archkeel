// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A write of an exception-chain name (`__cause__`, ...) is no loader site when the project defines no
//! hook that the write can reach (#2090, AD-1132). The scan reads no type, so the receiver is unknown.

use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Identifier, ModModule, Stmt};

/// The exception-chain names: Python reads them to print a traceback and never calls them as a hook. A write
/// of one changes no import and no call (#2090). A read of `__traceback__` hands out frames, so only a write is clear.
pub(super) const CHAIN_WRITES: [&str; 5] = [
    "__cause__",
    "__context__",
    "__traceback__",
    "__suppress_context__",
    "__notes__",
];

/// The methods that a write or a delete of an attribute can run, or that give the replaced value a finalizer.
const HOOKS: [&str; 6] = [
    "__setattr__",
    "__delattr__",
    "__set__",
    "__delete__",
    "__set_name__",
    "__del__",
];

/// The bases whose methods (`append`, `__iadd__`) a write to `__notes__` can reach.
const LIST_BASES: [&str; 3] = ["list", "UserList", "MutableSequence"];

/// True when a module defines a hook that a write of an exception-chain name can reach: a hook method (also as a
/// string, `type(name, bases, {"__setattr__": f})`), a class with a list base, or a class member that has the name
/// of a chain attribute (a property, a descriptor). One such definition anywhere makes the exemption void.
struct Hooks(bool);

impl<'a> Visitor<'a> for Hooks {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let named = |name: &Identifier| HOOKS.contains(&Identifier::as_str(name));
        match stmt {
            Stmt::FunctionDef(def) if named(&def.name) => self.0 = true,
            Stmt::ClassDef(def) => {
                let bases = def.bases();
                self.0 |= bases.iter().any(|base| {
                    matches!(base, Expr::Name(n) if LIST_BASES.contains(&Name::as_str(&n.id)))
                });
                self.0 |= def.body.iter().any(member_of_chain);
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::StringLiteral(text) if HOOKS.contains(&text.value.to_str())) {
            self.0 = true;
        }
        visitor::walk_expr(self, expr);
    }
}

/// True when a statement of a class body binds a name of the exception chain.
fn member_of_chain(stmt: &Stmt) -> bool {
    let chain = |name: &str| CHAIN_WRITES.contains(&name);
    match stmt {
        Stmt::FunctionDef(def) => chain(Identifier::as_str(&def.name)),
        Stmt::Assign(node) => node
            .targets
            .iter()
            .any(|target| matches!(target, Expr::Name(n) if chain(Name::as_str(&n.id)))),
        Stmt::AnnAssign(node) => {
            matches!(&*node.target, Expr::Name(n) if chain(Name::as_str(&n.id)))
        }
        _ => false,
    }
}

/// True when no scanned module defines a hook that a write of an exception-chain name can reach (#2090).
pub(in crate::survey) fn clear(trees: &[&ModModule]) -> bool {
    let mut hooks = Hooks(false);
    trees.iter().for_each(|tree| hooks.visit_body(&tree.body));
    !hooks.0
}
