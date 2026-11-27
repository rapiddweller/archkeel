// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The statements of the scan that can change what a typing factory makes (AD-568).
//!
//! A typing alias such as `Annotated[X, m]` is a value, not a module, as long as nothing replaces
//! the factory. Python replaces a name of the `typing` module only by one of these statements, and
//! the survey withholds the proof when the scan holds any of them:
//!
//! - a store or a delete of an attribute whose name is a factory name, a name of `STDLIB_VALUES` or
//!   `__getitem__`,
//!   `__class_getitem__`, `__call__`, `__dict__`, `__class__` or `__new__`;
//! - a `__setattr__` or `__delattr__` use, unless it is `object.__setattr__(a, "name", v)` with a
//!   literal name that is none of the names above (`object.__setattr__` works on a module);
//! - a write through `vars(..)` or through the result of a `__dict__` read: a read is only an
//!   unpack `**d`, a comparison, an iteration, a subscript load, `len` or a read method;
//! - a write into `sys.modules`, unless the key is a literal other than `typing`,
//!   `typing_extensions` and the modules of `STDLIB_VALUES`.
//!
//! A `setattr` or `delattr` call is a flag of the bound module table (`Bound::attribute_write`).

use crate::module::builtin_roles::{self, Role};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, Stmt};

use crate::module::Module;

/// The standard library names whose call gives a value, never a module (Python 3.12: a path, a
/// number, a date, a logger, a container). The proof needs the name to be the one plain import
/// of its module, and a scan without a store to the name.
pub(super) const STDLIB_VALUES: &[(&str, &[&str])] = &[
    (
        "pathlib",
        &["Path", "PurePath", "PurePosixPath", "PureWindowsPath"],
    ),
    ("decimal", &["Decimal"]),
    ("fractions", &["Fraction"]),
    ("uuid", &["UUID"]),
    (
        "datetime",
        &["date", "datetime", "time", "timedelta", "timezone"],
    ),
    ("logging", &["getLogger"]),
    (
        "collections",
        &["OrderedDict", "defaultdict", "Counter", "deque"],
    ),
];

/// Whether `module.symbol` is one of `STDLIB_VALUES`.
pub(super) fn stdlib_value(module: &str, symbol: &str) -> bool {
    STDLIB_VALUES
        .iter()
        .any(|(name, symbols)| *name == module && symbols.contains(&symbol))
}

/// The typing forms that a store must not name.
const TYPING_FORMS: [&str; 6] = [
    "Annotated",
    "Optional",
    "Union",
    "Literal",
    "TypeVar",
    "NewType",
];

/// The special attributes of an object that a store must not name.
const SPECIAL: [&str; 6] = [
    "__getitem__",
    "__class_getitem__",
    "__call__",
    "__dict__",
    "__class__",
    "__new__",
];

/// The methods of a mapping that change nothing.
pub(super) const READS: [&str; 5] = ["keys", "items", "values", "get", "copy"];

/// True when a statement of one of the modules can change what a typing factory makes.
pub(super) fn withheld(modules: &[Module]) -> bool {
    let mut guard = Guard(false);
    modules
        .iter()
        .for_each(|module| guard.visit_body(&module.tree.body));
    guard.0
}

struct Guard(bool);

fn named(name: &str) -> bool {
    TYPING_FORMS.contains(&name)
        || SPECIAL.contains(&name)
        || STDLIB_VALUES
            .iter()
            .any(|(_, values)| values.contains(&name))
}

fn mapping_of(expr: &Expr) -> bool {
    match expr {
        Expr::Attribute(node) => node.attr.as_str() == "__dict__",
        Expr::Call(call) => matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "vars"),
        _ => false,
    }
}

fn literal_other_than_typing(expr: &Expr) -> bool {
    matches!(expr, Expr::StringLiteral(text)
        if !matches!(text.value.to_str(), "typing" | "typing_extensions")
            && STDLIB_VALUES.iter().all(|(module, _)| *module != text.value.to_str()))
}

fn modules_table(expr: &Expr) -> bool {
    match expr {
        Expr::Attribute(node) => node.attr.as_str() == "modules",
        Expr::Name(name) => name.id.as_str() == "modules",
        _ => false,
    }
}

impl Guard {
    /// Visit an expression that may be a mapping read; a read keeps the guard quiet.
    fn read(&mut self, expr: &Expr) {
        if mapping_of(expr) {
            match expr {
                Expr::Call(call) => self.visit_arguments(&call.arguments),
                Expr::Attribute(node) => self.visit_expr(&node.value),
                _ => {}
            }
        } else {
            self.visit_expr(expr);
        }
    }

    fn object_setattr(
        &mut self,
        call: &ruff_python_ast::ExprCall,
        node: &ruff_python_ast::ExprAttribute,
    ) -> bool {
        let on_object = matches!(&*node.value, Expr::Name(name) if name.id.as_str() == "object");
        let literal = call.arguments.args.get(1).and_then(|name| match name {
            Expr::StringLiteral(text) => Some(text.value.to_str()),
            _ => None,
        });
        if !(on_object && literal.is_some_and(|name| !named(name))) {
            self.0 = true;
        }
        for arg in call.arguments.args.iter() {
            self.visit_expr(arg);
        }
        true
    }

    /// A call: the write methods of `sys.modules`, `__setattr__` forms, readers of a mapping.
    fn call<'a>(&mut self, expr: &'a Expr, call: &'a ruff_python_ast::ExprCall) {
        self.0 |= mapping_of(expr);
        if let Expr::Attribute(node) = &*call.func {
            let method = node.attr.as_str();
            if matches!(method, "__setattr__" | "__delattr__") && self.object_setattr(call, node) {
                return;
            }
            if modules_table(&node.value)
                && matches!(
                    method,
                    "update" | "setdefault" | "pop" | "popitem" | "clear"
                )
            {
                self.0 = true;
            }
            if READS.contains(&method) && mapping_of(&node.value) {
                self.read(&node.value);
                self.visit_arguments(&call.arguments);
                return;
            }
        }
        if matches!(&*call.func, Expr::Name(name) if builtin_roles::has(name.id.as_str(), Role::MAPPING_READER))
        {
            call.arguments.args.iter().for_each(|arg| self.read(arg));
            call.arguments
                .keywords
                .iter()
                .for_each(|key| self.visit_expr(&key.value));
            return;
        }
        call.arguments.keywords.iter().for_each(|key| {
            if key.arg.is_none() {
                self.read(&key.value);
            } else {
                self.visit_expr(&key.value);
            }
        });
        self.visit_expr(&call.func);
        call.arguments
            .args
            .iter()
            .for_each(|arg| self.visit_expr(arg));
    }
}

impl<'a> Visitor<'a> for Guard {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::For(node) = stmt {
            self.read(&node.iter);
            self.visit_expr(&node.target);
            self.visit_body(&node.body);
            self.visit_body(&node.orelse);
            return;
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Attribute(node) => {
                let attr = node.attr.as_str();
                if node.ctx != ExprContext::Load && named(attr) {
                    self.0 = true;
                }
                if matches!(attr, "__setattr__" | "__delattr__") {
                    // A call with a name argument is judged in `Expr::Call`; any other use is a write.
                    self.0 = true;
                }
            }
            Expr::Subscript(node) => {
                if node.ctx != ExprContext::Load && modules_table(&node.value) {
                    self.0 |= !literal_other_than_typing(&node.slice);
                }
                if node.ctx != ExprContext::Load && mapping_of(&node.value) {
                    self.0 = true;
                }
                if node.ctx == ExprContext::Load {
                    self.read(&node.value);
                } else {
                    self.visit_expr(&node.value);
                }
                self.visit_expr(&node.slice);
                return;
            }
            Expr::Call(call) => {
                self.call(expr, call);
                return;
            }
            Expr::Compare(node) => {
                node.operands.iter().for_each(|item| self.read(item));
                return;
            }
            _ => {}
        }
        if mapping_of(expr) {
            // A mapping read that is no read form: its result may be written.
            self.0 = true;
        }
        visitor::walk_expr(self, expr);
    }
}
