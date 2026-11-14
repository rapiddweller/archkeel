// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites that can import a module that no `import` statement names (AD-450).
//!
//! A dynamic import is a call of an import function, or of `exec` or `eval`. An import-system
//! change writes to `sys.path`, `sys.meta_path`, `sys.path_hooks`, `sys.modules` or a package
//! `__path__`, or calls `site.addsitedir` or `pkgutil.extend_path`. The walk reads each node of
//! the module, also in functions and classes. It finds names, not bindings: a local function
//! with one of these names is a site too, which is the stricter reading.

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

/// The named gaps of the sites.
pub const DYNAMIC: &str = "dynamic_import";
pub const IMPORT_SYSTEM: &str = "import_system_change";

/// The functions that import a module from a value, as a name or as an attribute.
const IMPORT_FUNCTIONS: [&str; 8] = [
    "__import__",
    "import_module",
    "load_module",
    "exec_module",
    "module_from_spec",
    "spec_from_file_location",
    "run_module",
    "run_path",
];

/// The builtins that run text: a dynamic import only as a plain name, not as an attribute
/// (`model.eval()` is no import).
const TEXT_RUNNERS: [&str; 2] = ["exec", "eval"];

/// The functions that change where the import system looks.
const PATH_FUNCTIONS: [&str; 2] = ["addsitedir", "extend_path"];

/// The attributes of `sys` whose change moves the result of an import.
const SYS_STATE: [&str; 4] = ["path", "meta_path", "path_hooks", "modules"];

/// The methods that change a list or a dict of the import state.
const MUTATORS: [&str; 9] = [
    "append",
    "insert",
    "extend",
    "remove",
    "pop",
    "clear",
    "update",
    "setdefault",
    "popitem",
];

/// One site: its gap, a short text and its range.
pub struct Site {
    pub kind: &'static str,
    pub detail: String,
    pub range: TextRange,
}

/// The sites of a module, in source order.
pub fn sites(tree: &ModModule) -> Vec<Site> {
    let mut walk = Walk { found: Vec::new() };
    walk.visit_body(&tree.body);
    walk.found
}

struct Walk {
    found: Vec<Site>,
}

impl Walk {
    fn push(&mut self, kind: &'static str, detail: &str, node: &impl Ranged) {
        self.found.push(Site {
            kind,
            detail: detail.to_owned(),
            range: node.range(),
        });
    }

    /// A write to the import state: `sys.<state>`, an item or attribute of it, or `__path__`.
    fn target(&mut self, target: &Expr) {
        if let Some(name) = import_state(target) {
            self.push(IMPORT_SYSTEM, &name, target);
        }
    }
}

/// The name of the import state that `expr` is or is a part of.
fn import_state(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(node) if node.id.as_str() == "__path__" => Some("__path__".to_owned()),
        Expr::Attribute(node) if node.attr.as_str() == "__path__" => Some("__path__".to_owned()),
        Expr::Attribute(node) => match &*node.value {
            Expr::Name(base)
                if base.id.as_str() == "sys" && SYS_STATE.contains(&node.attr.as_str()) =>
            {
                Some(format!("sys.{}", node.attr.as_str()))
            }
            other => import_state(other),
        },
        Expr::Subscript(node) => import_state(&node.value),
        _ => None,
    }
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Assign(node) => node.targets.iter().for_each(|target| self.target(target)),
            Stmt::AugAssign(node) => self.target(&node.target),
            Stmt::AnnAssign(node) => self.target(&node.target),
            Stmt::Delete(node) => node.targets.iter().for_each(|target| self.target(target)),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            self.call(&call.func, expr);
        }
        visitor::walk_expr(self, expr);
    }
}

impl Walk {
    /// A call of `function`: a dynamic import, a path function or a change of the import state.
    fn call(&mut self, function: &Expr, expr: &Expr) {
        let (name, attribute, receiver) = match function {
            Expr::Name(node) => (node.id.as_str(), false, None),
            Expr::Attribute(node) => (node.attr.as_str(), true, Some(&*node.value)),
            _ => return,
        };
        let runner = !attribute && TEXT_RUNNERS.contains(&name);
        if IMPORT_FUNCTIONS.contains(&name) || runner {
            self.push(DYNAMIC, name, expr);
        } else if PATH_FUNCTIONS.contains(&name) {
            self.push(IMPORT_SYSTEM, name, expr);
        } else if let Some(state) = receiver
            .filter(|_| MUTATORS.contains(&name))
            .and_then(import_state)
        {
            // A change of the import state, such as `sys.path.insert(0, x)`.
            self.push(IMPORT_SYSTEM, &format!("{state}.{name}"), expr);
        }
    }
}

#[cfg(test)]
#[path = "hazards_tests.rs"]
mod tests;
