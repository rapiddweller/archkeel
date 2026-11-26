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

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    CmpOp, ElifElseClause, Expr, ExprCall, ExprCompare, FStringPartRef, Identifier, Keyword,
    Operator, Stmt, UnaryOp,
};
use ruff_text_size::Ranged;

use super::sites::literal_elements;
use crate::module::Module;

/// The text of a string written in the source. An f-string without a field is that text:
/// `f"app"` names `app` like `"app"` does.
pub(super) fn text_of(expr: &Expr) -> Option<String> {
    match expr {
        Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
        Expr::FString(node) => {
            let mut text = String::new();
            for part in node.value.iter() {
                let plain = match part {
                    FStringPartRef::Literal(literal) => {
                        text.push_str(&literal.value);
                        true
                    }
                    FStringPartRef::FString(fstring) => {
                        literal_elements(&mut text, &fstring.elements)
                    }
                };
                if !plain {
                    return None;
                }
            }
            Some(text)
        }
        _ => None,
    }
}

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

/// The calls that load a module, read a resource or run code by a name. A name that is not a
/// text written in the source can be any module of the scan (#1963, AD-1211).
const NAME_APIS: [&str; 8] = [
    "import_module",
    "__import__",
    "spec_from_file_location",
    "find_spec",
    "distribution",
    "exec",
    "run_module",
    "run_path",
];

/// The calls that were no site before: with a text as name they are a site for the modules that
/// a text of the file names.
const NEW_SITES: [&str; 3] = ["files", "version", "distribution"];

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
pub(super) fn api_calls(module: &Module) -> Vec<ApiCall> {
    struct Calls<'m> {
        module: &'m Module,
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
            let computed = names_computed(call, &name);
            // A name written in the source is judged by the site rules of AD-770 and AD-1049 for the
            // calls that were sites before; only the calls that are new sites are added here.
            let runpy = chain(&call.func).is_some_and(|t| t.starts_with("runpy."));
            let new_site = NEW_SITES.contains(&String::as_str(&name))
                || matches!(String::as_str(&name), "run_module" | "run_path")
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

        fn api(&self, call: &ExprCall) -> Option<String> {
            let text = chain(&call.func);
            let last = match &*call.func {
                Expr::Name(name) => name.id.to_string(),
                Expr::Attribute(node) => Identifier::as_str(&node.attr).to_owned(),
                _ => return None,
            };
            let runpy = text.as_deref().is_some_and(|t| t.starts_with("runpy."));
            let common = IMPORTLIB_APIS.contains(&String::as_str(&last)) && self.importlib;
            (NAME_APIS.contains(&String::as_str(&last)) || runpy || common).then_some(last)
        }
    }
    let mut calls = Calls {
        module,
        importlib: false,
        found: Vec::new(),
    };
    calls.visit_body(&module.tree.body);
    calls.found
}

/// What a name or an expression of the closed grammar stands for.
#[derive(Clone, Copy, PartialEq)]
enum Value {
    /// A text, a number, a bool or `None`: no method of it runs code of the file.
    Plain,
    /// The path that `importlib.resources.files(text)` gives.
    Path,
    /// The spec that `importlib.util.find_spec(text)` gives; only a test against `None` uses it.
    Spec,
}

/// The names that `from importlib... import` may bind, by module.
const FROM_IMPORTS: [(&str, &str); 3] = [
    ("importlib.metadata", "version"),
    ("importlib.resources", "files"),
    ("importlib.util", "find_spec"),
];

/// The modules that `import` may bind, without an alias.
const IMPORTS: [&str; 5] = [
    "sys",
    "importlib",
    "importlib.metadata",
    "importlib.resources",
    "importlib.util",
];

/// The calls on a path that give a text or a bool.
const PATH_READS: [&str; 5] = ["read_text", "read_bytes", "is_file", "is_dir", "exists"];

/// The names that no assignment may bind.
const RESERVED: [&str; 6] = ["print", "sys", "importlib", "version", "files", "find_spec"];

#[derive(Default)]
struct Grammar {
    bound: HashMap<String, Value>,
    from: HashSet<String>,
}

/// True when the whole file is in the closed grammar of a read-only script (#1963, AD-1211):
/// `import` of `sys` and of `importlib.metadata`, `importlib.resources` and `importlib.util`
/// without an alias, `from` of `version`, `files` and `find_spec`, a name that is assigned once
/// from a read, `print` of texts and reads to the standard output, `assert` and `if` over a test
/// of a read, and nothing else. A read is `version(text)`, `files(text)` with `.joinpath(text)`
/// or `/ text` and a path read, `text in sys.modules`, and `find_spec(text) is None`. Each value
/// that reaches a call is a text written in the source, so no object runs its own code. The file
/// writes no path, defines nothing and calls nothing else: it cannot write a binding of the scan
/// or change a file of it.
pub(super) fn closed(module: &Module) -> bool {
    let mut grammar = Grammar::default();
    module.tree.body.iter().all(|stmt| grammar.stmt(stmt))
}

/// `joinpath(text)` keeps a path; a read gives a text.
fn path_call(attr: &str) -> Option<Value> {
    match attr {
        "joinpath" => Some(Value::Path),
        _ => PATH_READS.contains(&attr).then_some(Value::Plain),
    }
}

impl Grammar {
    fn stmt(&mut self, stmt: &Stmt) -> bool {
        match stmt {
            Stmt::Pass(_) => true,
            Stmt::Import(node) => node
                .names
                .iter()
                .all(|a| a.asname.is_none() && IMPORTS.contains(&Identifier::as_str(&a.name))),
            Stmt::ImportFrom(node) => self.import_from(node),
            Stmt::Expr(node) => self.statement_expr(&node.value),
            Stmt::Assign(node) => self.assign(&node.targets, &node.value),
            Stmt::Assert(node) => {
                let msg = node.msg.as_deref().is_none_or(|m| text_of(m).is_some());
                self.value(&node.test) == Some(Value::Plain) && msg
            }
            Stmt::If(node) => {
                self.value(&node.test) == Some(Value::Plain)
                    && node.body.iter().all(|s| self.stmt(s))
                    && node.elif_else_clauses.iter().all(|c| self.clause(c))
            }
            _ => false,
        }
    }

    fn clause(&mut self, clause: &ElifElseClause) -> bool {
        let test = clause
            .test
            .as_ref()
            .is_none_or(|t| self.value(t) == Some(Value::Plain));
        test && clause.body.iter().all(|s| self.stmt(s))
    }

    fn import_from(&mut self, node: &ruff_python_ast::StmtImportFrom) -> bool {
        let from = node.module.as_ref().map_or("", Identifier::as_str);
        let allowed = |name: &str| FROM_IMPORTS.contains(&(from, name));
        let ok = node.level == 0
            && node
                .names
                .iter()
                .all(|a| a.asname.is_none() && allowed(Identifier::as_str(&a.name)));
        for alias in &node.names {
            self.from.insert(Identifier::as_str(&alias.name).to_owned());
        }
        ok
    }

    /// `print(...)` or a bare read.
    fn statement_expr(&self, expr: &Expr) -> bool {
        let Expr::Call(call) = expr else {
            return matches!(self.value(expr), Some(Value::Plain | Value::Path));
        };
        let printed = matches!(&*call.func, Expr::Name(n) if n.id.as_str() == "print");
        if !printed {
            return matches!(self.value(expr), Some(Value::Plain | Value::Path));
        }
        let keywords: &[Keyword] = &call.arguments.keywords;
        let shown = |a: &Expr| matches!(self.value(a), Some(Value::Plain | Value::Path));
        keywords.is_empty() && call.arguments.args.iter().all(shown)
    }

    fn assign(&mut self, targets: &[Expr], value: &Expr) -> bool {
        let [Expr::Name(target)] = targets else {
            return false;
        };
        let name = target.id.to_string();
        let free = !RESERVED.contains(&String::as_str(&name)) && !self.bound.contains_key(&name);
        match self.value(value) {
            Some(kind @ (Value::Plain | Value::Path)) if free => {
                self.bound.insert(name, kind);
                true
            }
            _ => false,
        }
    }

    fn value(&self, expr: &Expr) -> Option<Value> {
        match expr {
            Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::NoneLiteral(_) => {
                Some(Value::Plain)
            }
            Expr::StringLiteral(_) | Expr::FString(_) => text_of(expr).map(|_| Value::Plain),
            Expr::Name(name) => self.bound.get(name.id.as_str()).copied(),
            Expr::BinOp(node) if matches!(node.op, Operator::Div) => {
                let path = self.value(&node.left) == Some(Value::Path);
                (path && text_of(&node.right).is_some()).then_some(Value::Path)
            }
            Expr::UnaryOp(node) if matches!(node.op, UnaryOp::Not) => {
                (self.value(&node.operand) == Some(Value::Plain)).then_some(Value::Plain)
            }
            Expr::BoolOp(node) => {
                let plain = node
                    .values
                    .iter()
                    .all(|v| self.value(v) == Some(Value::Plain));
                plain.then_some(Value::Plain)
            }
            Expr::Compare(node) => self.compare(node),
            Expr::Call(call) => self.call(call),
            _ => None,
        }
    }

    /// `text in sys.modules`, `text not in sys.modules`, `find_spec(text) is None`.
    fn compare(&self, node: &ExprCompare) -> Option<Value> {
        let [left, right] = &*node.operands else {
            return None;
        };
        let [op] = &*node.ops else {
            return None;
        };
        let tested = matches!(op, CmpOp::In | CmpOp::NotIn)
            && text_of(left).is_some()
            && chain(right).as_deref() == Some("sys.modules");
        let spec = matches!(op, CmpOp::Is | CmpOp::IsNot)
            && right.is_none_literal_expr()
            && self.value(left) == Some(Value::Spec);
        (tested || spec).then_some(Value::Plain)
    }

    fn call(&self, call: &ExprCall) -> Option<Value> {
        if !texts(call) {
            return None;
        }
        if let Expr::Attribute(node) = &*call.func {
            if self.value(&node.value) == Some(Value::Path) {
                return path_call(Identifier::as_str(&node.attr));
            }
        }
        let name = chain(&call.func)?;
        let bare = |from: &str| self.from.contains(from) && !name.contains('.');
        match String::as_str(&name) {
            "importlib.metadata.version" => Some(Value::Plain),
            "importlib.resources.files" => Some(Value::Path),
            "importlib.util.find_spec" => Some(Value::Spec),
            _ if bare("version") && name == "version" => Some(Value::Plain),
            _ if bare("files") && name == "files" => Some(Value::Path),
            _ if bare("find_spec") && name == "find_spec" => Some(Value::Spec),
            _ => None,
        }
    }
}
