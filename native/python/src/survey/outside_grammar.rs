// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed grammar of a read-only outside script and the loader calls of an outside file
//! (#1963, AD-1211).
//!
//! A script outside the scan roots holds nothing only when each statement and each expression
//! is in a small allow-list (`closed`). Anything else keeps the hold of AD-770. A call of a
//! loader or a resource API (`api_calls`) is a site for each module that a text of the file
//! names; with an argument that is not a text written in the source it is a site for every
//! module of the scan, because the name can be any of them.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    CmpOp, ElifElseClause, Expr, ExprCall, ExprCompare, Identifier, Keyword, Stmt, UnaryOp,
};
use ruff_text_size::Ranged;

use super::super::hazards_names::IMPORT_FUNCTIONS;
use super::sites::{foreign, text_of};
use crate::module::Module;

/// The dotted name of a name or a chain of attributes on a name.
fn chain(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(name) => Some(name.id.to_string()),
        Expr::Attribute(node) => Some(format!(
            "{}.{}",
            chain(&node.value)?,
            Identifier::as_str(&node.attr)
        )),
        _ => None,
    }
}

/// True when each argument is a text written in the source and none is a keyword.
fn texts(call: &ExprCall) -> bool {
    let keywords: &[Keyword] = &call.arguments.keywords;
    keywords.is_empty() && call.arguments.args.iter().all(|arg| text_of(arg).is_some())
}

/// The calls that load a module, read a resource or run code by a name, besides the import
/// functions of `hazards_names` (`IMPORT_FUNCTIONS`). A name that is not a text written in the
/// source can be any module of the scan (#1963, AD-1211).
const NAME_APIS: [&str; 3] = ["find_spec", "distribution", "exec"];

/// The import functions that take an object and no name: they are no site here.
fn takes_a_name(api: &str) -> bool {
    !matches!(api, "load_module" | "exec_module" | "module_from_spec")
}

/// The calls that are an API only through `importlib`: the names are common.
const IMPORTLIB_APIS: [&str; 2] = ["files", "version"];

/// True when the name that the call hands to the API is not a text written in the source. The
/// name is the first argument; `import_module`, `__import__` and `find_spec` read the others too
/// (`package=`). A location (`spec_from_file_location("x", path)`) or the globals of an `exec`
/// name no module.
fn names_computed(call: &ExprCall, api: &str) -> bool {
    if matches!(api, "import_module" | "__import__" | "find_spec") {
        return !texts(call);
    }
    let keywords: &[Keyword] = &call.arguments.keywords;
    match call.arguments.args.first() {
        Some(first) => text_of(first).is_none(),
        None => keywords.iter().any(|k| text_of(&k.value).is_none()),
    }
}

/// One call of an outside file to a loader or a resource API.
pub(super) struct ApiCall {
    pub name: String,
    pub line: i64,
    /// An argument is not a text written in the source: the name can be any module.
    pub computed: bool,
}

/// The loader and resource calls of a file, by the name of the callee. A file that imports from
/// `importlib` also has `files` and `version` as such calls (an alias hides the chain).
pub(super) fn api_calls(module: &Module, names: &HashSet<String>) -> Vec<ApiCall> {
    struct Calls<'m> {
        module: &'m Module,
        names: &'m HashSet<String>,
        importlib: bool,
        found: Vec<ApiCall>,
    }
    impl<'a> Visitor<'a> for Calls<'_> {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            match stmt {
                Stmt::Import(node) => {
                    let mut named = node.names.iter();
                    self.importlib |=
                        named.any(|a| Identifier::as_str(&a.name).starts_with("importlib"));
                }
                Stmt::ImportFrom(node) => {
                    let from = node.module.as_ref().map_or("", Identifier::as_str);
                    self.importlib |= from.starts_with("importlib");
                }
                _ => {}
            }
            visitor::walk_stmt(self, stmt);
        }
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::Call(call) = expr {
                self.record(call);
            }
            visitor::walk_expr(self, expr);
        }
    }
    impl Calls<'_> {
        fn record(&mut self, call: &ExprCall) {
            let Some(name) = self.api(call) else {
                return;
            };
            let line = self.module.location(&call.range()).line;
            let computed = names_computed(call, &name) && !self.foreign_name(call, &name);
            // A name written in the source is judged by the site rules of AD-770 and AD-1049 for the
            // calls that were sites before; only the calls that are new sites are added here.
            let runpy = chain(&call.func).is_some_and(|t| t.starts_with("runpy."));
            // The calls that were no site before: a text as name names the modules that a text of
            // the file names. The other calls keep the site rules of AD-770 and AD-1049.
            let new_site = IMPORTLIB_APIS.contains(&String::as_str(&name))
                || matches!(
                    String::as_str(&name),
                    "distribution" | "run_module" | "run_path"
                )
                || runpy;
            if !computed && !new_site {
                return;
            }
            self.found.push(ApiCall {
                name,
                line,
                computed,
            });
        }

        /// A name that every value of which is provably no module of the scan (`f"tools.{x}"`,
        /// `"a" if c else "b"`) is no site: AD-770.
        fn foreign_name(&self, call: &ExprCall, api: &str) -> bool {
            let [only] = &*call.arguments.args else {
                return false;
            };
            let single = call.arguments.keywords.is_empty();
            single && matches!(api, "import_module" | "__import__") && foreign(only, self.names)
        }

        fn api(&self, call: &ExprCall) -> Option<String> {
            let text = chain(&call.func);
            let last = match &*call.func {
                Expr::Name(name) => name.id.to_string(),
                Expr::Attribute(node) => Identifier::as_str(&node.attr).to_owned(),
                _ => return None,
            };
            let runpy = text.as_deref().is_some_and(|t| t.starts_with("runpy."));
            let common = IMPORTLIB_APIS.contains(&String::as_str(&last)) && self.importlib;
            let named = NAME_APIS.contains(&String::as_str(&last))
                || (IMPORT_FUNCTIONS.contains(&String::as_str(&last)) && takes_a_name(&last));
            (named || runpy || common).then_some(last)
        }
    }
    let mut calls = Calls {
        module,
        names,
        importlib: false,
        found: Vec::new(),
    };
    calls.visit_body(&module.tree.body);
    calls.found
}

/// The only module that `import` may bind, without an alias: `sys` is built in, so no file beside
/// the script can shadow it. Any other import (`importlib.metadata` imports `csv`, a sibling
/// `csv.py` runs instead) can run code of the repository (Codex #2144).
const IMPORTS: [&str; 1] = ["sys"];

/// The names that no assignment may bind.
const RESERVED: [&str; 2] = ["print", "sys"];

#[derive(Default)]
struct Grammar {
    /// The names that an assignment bound to a plain value: each is bound once.
    bound: HashSet<String>,
}

/// True when the whole file is in the closed grammar of a script that reads nothing but its own
/// texts and `sys.modules` (#1963, AD-1211): `import sys` without an alias, a name assigned once
/// from a plain value, `print` of plain values to the standard output with no keyword, `assert`
/// and `if` over a plain test, and nothing else. A plain value is a text, a number, a bool or
/// `None` written in the source, a name bound to one, `not` and `and`/`or` of plain values, and
/// `text in sys.modules`. The file imports nothing else (a file beside the script can shadow
/// `csv`, `contextlib` or any package that `importlib` imports), calls nothing else, writes no
/// path and defines nothing: it can write no binding of the scan and change no file of it.
pub(super) fn closed(module: &Module) -> bool {
    let mut grammar = Grammar::default();
    module.tree.body.iter().all(|stmt| grammar.stmt(stmt))
}

impl Grammar {
    fn stmt(&mut self, stmt: &Stmt) -> bool {
        match stmt {
            Stmt::Pass(_) => true,
            Stmt::Import(node) => node
                .names
                .iter()
                .all(|a| a.asname.is_none() && IMPORTS.contains(&Identifier::as_str(&a.name))),
            Stmt::Expr(node) => self.statement_expr(&node.value),
            Stmt::Assign(node) => self.assign(&node.targets, &node.value),
            Stmt::Assert(node) => {
                let msg = node.msg.as_deref().is_none_or(|m| text_of(m).is_some());
                self.plain(&node.test) && msg
            }
            Stmt::If(node) => {
                self.plain(&node.test)
                    && node.body.iter().all(|s| self.stmt(s))
                    && node.elif_else_clauses.iter().all(|c| self.clause(c))
            }
            _ => false,
        }
    }

    fn clause(&mut self, clause: &ElifElseClause) -> bool {
        let test = clause.test.as_ref().is_none_or(|t| self.plain(t));
        test && clause.body.iter().all(|s| self.stmt(s))
    }

    /// `print(plain, ...)`, or a bare plain value.
    fn statement_expr(&self, expr: &Expr) -> bool {
        let Expr::Call(call) = expr else {
            return self.plain(expr);
        };
        let keywords: &[Keyword] = &call.arguments.keywords;
        let printed = matches!(&*call.func, Expr::Name(n) if n.id.as_str() == "print");
        printed && keywords.is_empty() && call.arguments.args.iter().all(|a| self.plain(a))
    }

    fn assign(&mut self, targets: &[Expr], value: &Expr) -> bool {
        let [Expr::Name(target)] = targets else {
            return false;
        };
        let name = target.id.to_string();
        let free = !RESERVED.contains(&String::as_str(&name)) && !self.bound.contains(&name);
        let ok = free && self.plain(value);
        if ok {
            self.bound.insert(name);
        }
        ok
    }

    fn plain(&self, expr: &Expr) -> bool {
        match expr {
            Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::NoneLiteral(_) => true,
            Expr::StringLiteral(_) | Expr::FString(_) => text_of(expr).is_some(),
            Expr::Name(name) => self.bound.contains(name.id.as_str()),
            Expr::UnaryOp(node) => matches!(node.op, UnaryOp::Not) && self.plain(&node.operand),
            Expr::BoolOp(node) => node.values.iter().all(|v| self.plain(v)),
            Expr::Compare(node) => Self::sys_modules_test(node),
            _ => false,
        }
    }

    /// `text in sys.modules`, `text not in sys.modules`.
    fn sys_modules_test(node: &ExprCompare) -> bool {
        let ([left, right], [op]) = (&*node.operands, &*node.ops) else {
            return false;
        };
        matches!(op, CmpOp::In | CmpOp::NotIn)
            && text_of(left).is_some()
            && chain(right).as_deref() == Some("sys.modules")
    }
}
