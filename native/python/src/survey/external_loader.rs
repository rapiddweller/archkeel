// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A call of a value from a module outside the scan and the standard library, with a string that
//! names a module of the scan (#1519, #1521, AD-760). Such a callee can be a loader
//! (`plugin.load("app.lib")`, `namespace()[key]("app.lib")`), and the scan cannot read it: the
//! edges that leave the module of the call are not complete. A string names a module when it is a
//! dotted path (or `module:attribute`) whose longest prefix is a module of the scan. A prefix that
//! is the module of the call or a package above it adds no edge: Python imports those already.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::module::Module;

/// The gap of such a call: the edges that leave its module are not complete.
pub(super) const EXTERNAL_LOADER: &str = "external_loader";

/// One call: the module index, the range, and the module of the scan that its string names.
pub(super) type Site = (usize, TextRange, String);

/// The calls of each module whose callee comes from a module outside the scan and the standard
/// library, with a string that names another module of the scan.
pub(super) fn find(modules: &[Module], stdlib: &HashSet<&str>, namespace: &str) -> Vec<Site> {
    let names: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    let project = namespace.split('.').next().unwrap_or(namespace);
    let mut found = Vec::new();
    for (index, module) in modules.iter().enumerate() {
        let mut walk = Walk {
            external: HashMap::new(),
            names: &names,
            own: &module.name,
            calls: Vec::new(),
        };
        let mut binds = Binds {
            stdlib,
            project,
            found: &mut walk.external,
        };
        binds.visit_body(&module.tree.body);
        if walk.external.is_empty() {
            continue;
        }
        walk.visit_body(&module.tree.body);
        found.extend(
            walk.calls
                .into_iter()
                .map(|(range, target)| (index, range, target)),
        );
    }
    found
}

/// The names that an import of a module outside the scan and the standard library binds, in any
/// scope of the file: a local name of the same spelling can only add a gap.
struct Binds<'s> {
    stdlib: &'s HashSet<&'s str>,
    project: &'s str,
    found: &'s mut HashMap<String, ()>,
}

impl Binds<'_> {
    fn external(&self, origin: &str) -> bool {
        let top = origin.split('.').next().unwrap_or(origin);
        !top.is_empty() && top != self.project && !self.stdlib.contains(top)
    }
}

impl<'a> Visitor<'a> for Binds<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let bound: Vec<String> = match stmt {
            Stmt::Import(node) => (node.names.iter())
                .filter(|alias| self.external(alias.name.as_str()))
                .map(|alias| {
                    alias.asname.as_ref().map_or_else(
                        || alias.name.split('.').next().unwrap_or_default().to_owned(),
                        ToString::to_string,
                    )
                })
                .collect(),
            Stmt::ImportFrom(node)
                if node.level == 0
                    && self.external(node.module.as_ref().map_or("", |m| m.as_str())) =>
            {
                (node.names.iter())
                    .map(|alias| alias.asname.as_ref().unwrap_or(&alias.name).to_string())
                    .collect()
            }
            _ => return visitor::walk_stmt(self, stmt),
        };
        self.found.extend(bound.into_iter().map(|name| (name, ())));
    }
}

struct Walk<'s> {
    external: HashMap<String, ()>,
    names: &'s HashSet<&'s str>,
    own: &'s str,
    calls: Vec<(TextRange, String)>,
}

impl Walk<'_> {
    /// True when the callee goes back to an external binding through attributes, calls and
    /// subscripts.
    fn external_callee(&self, mut expr: &Expr) -> bool {
        loop {
            expr = match expr {
                Expr::Attribute(node) => &node.value,
                Expr::Call(node) => &node.func,
                Expr::Subscript(node) => &node.value,
                Expr::Name(node) => return self.external.contains_key(node.id.as_str()),
                _ => return false,
            };
        }
    }

    /// The module of the scan that `text` names, unless it is the module of the call or above it.
    fn target(&self, text: &str) -> Option<String> {
        let path = text.split(':').next().unwrap_or(text);
        let valid = |part: &str| {
            part.chars()
                .next()
                .is_some_and(|c| c.is_alphabetic() || c == '_')
                && part.chars().all(|c| c.is_alphanumeric() || c == '_')
        };
        let parts: Vec<&str> = path.split('.').collect();
        if !parts.iter().all(|part| valid(part)) {
            return None;
        }
        let module = (1..=parts.len())
            .rev()
            .map(|count| parts[..count].join("."))
            .find(|prefix| self.names.contains(prefix.as_str()))?;
        let above = self.own == module || self.own.starts_with(&format!("{module}."));
        (!above).then_some(module)
    }
}

impl Walk<'_> {
    /// A call of an external callee: each string argument that names another module of the scan.
    fn call(&mut self, node: &ruff_python_ast::ExprCall, range: TextRange) {
        if !self.external_callee(&node.func) {
            return;
        }
        let arguments =
            (node.arguments.args.iter()).chain(node.arguments.keywords.iter().map(|k| &k.value));
        let texts = arguments.filter_map(|argument| match argument {
            Expr::StringLiteral(text) => Some(text.value.to_str()),
            _ => None,
        });
        let modules: Vec<String> = texts.filter_map(|text| self.target(text)).collect();
        self.calls
            .extend(modules.into_iter().map(|module| (range, module)));
    }
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(node) = expr {
            self.call(node, expr.range());
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "external_loader_tests.rs"]
mod tests;
