// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The walk that finds the uses of a module binding that can change the module (AD-566, #2117):
//! each use that escapes a module is kept with its kind and its place.

use std::collections::HashMap;

use archkeel_facts::vocab::RouteWithheld;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprAttribute, ExprContext};

use super::super::uses_scan::Scan;
use crate::module::Module;

/// The attributes of a module that are its namespace.
pub(super) const NAMESPACE: [&str; 4] = ["__dict__", "__all__", "__setattr__", "__delattr__"];

/// What one imported name is in a module.
pub(super) enum Binding {
    /// `import a.b` (the name `a`), `import a.b as c`, `from a import b` where `a.b` is a module.
    Module(String),
    /// `from a import x` where `a.x` is no module of the scan: the origin of the name.
    Attribute(String, String),
}

/// The first use that escapes each module: the kind of the use and where it is (#2117).
pub(crate) type Escapes = HashMap<String, (RouteWithheld, String)>;

pub(super) struct Uses<'s, 'm> {
    pub(super) module: &'m Module,
    pub(super) scan: &'s Scan<'m>,
    pub(super) names: Option<&'s HashMap<&'m str, Vec<Binding>>>,
    pub(super) found: &'s mut Escapes,
}

impl Uses<'_, '_> {
    /// The modules that the expression denotes (the module itself, not a name inside it), and
    /// whether each of them is certain (a module binding) or unknown (an imported name).
    fn denotes(&self, expr: &Expr) -> Vec<String> {
        match expr {
            Expr::Name(node) => {
                let kinds = self.names.and_then(|names| names.get(node.id.as_str()));
                kinds
                    .into_iter()
                    .flatten()
                    .filter_map(|kind| self.name(kind))
                    .collect()
            }
            Expr::Attribute(node) => self
                .exact(&node.value)
                .into_iter()
                .map(|module| format!("{module}.{}", node.attr.as_str()))
                .filter(|child| self.scan.modules.contains(child.as_str()))
                .collect(),
            Expr::Call(_) => literal_import(expr)
                .filter(|name| self.scan.modules.contains(name.as_str()))
                .into_iter()
                .collect(),
            _ => Vec::new(),
        }
    }

    /// The modules that a binding may denote; a proven non-module denotes none.
    fn name(&self, kind: &Binding) -> Option<String> {
        match kind {
            Binding::Module(module) => Some(module.clone()),
            Binding::Attribute(anchor, symbol) => {
                (!self.scan.callable(anchor, symbol, 0)).then(|| anchor.clone())
            }
        }
    }

    /// The modules that a chain certainly denotes: bindings of a module, not of an unknown name.
    fn exact(&self, expr: &Expr) -> Vec<String> {
        match expr {
            Expr::Name(node) => {
                let kinds = self.names.and_then(|names| names.get(node.id.as_str()));
                let modules = kinds.into_iter().flatten();
                modules
                    .filter_map(|kind| match kind {
                        Binding::Module(module) => Some(module.clone()),
                        Binding::Attribute(..) => None,
                    })
                    .collect()
            }
            _ => self.denotes(expr),
        }
    }

    /// True when `expr` is a name that an import binds from another module.
    fn by_import(&self, expr: &Expr) -> bool {
        let Expr::Name(node) = expr else { return false };
        let kinds = self.names.and_then(|names| names.get(node.id.as_str()));
        kinds.is_some_and(|kinds| {
            kinds
                .iter()
                .any(|kind| matches!(kind, Binding::Attribute(..)))
        })
    }

    /// Record the use `at` that hands each of `modules` on, and each module below it.
    fn escape(&mut self, modules: Vec<String>, kind: RouteWithheld, line: i64) {
        let place = format!("{}:{line}", self.module.rel);
        for module in modules {
            for below in self.scan.below(&module) {
                let use_of = (kind, format!("{module} <- {place}"));
                self.found.entry(below).or_insert(use_of);
            }
        }
    }
}

impl Uses<'_, '_> {
    /// An attribute of a module binding: true when the use is decided (harmless or escaped).
    fn attribute(&mut self, node: &ExprAttribute, expr: &Expr) -> bool {
        let base = self.denotes(&node.value);
        if base.is_empty() {
            return false;
        }
        let load = node.ctx == ExprContext::Load && !NAMESPACE.contains(&node.attr.as_str());
        let child = self.denotes(expr);
        // The one harmless use: a direct load of a name that is no module. A load of a child
        // module is a bare use of that module; each other use escapes the base.
        if !load {
            let namespace = NAMESPACE.contains(&node.attr.as_str());
            let kind = if namespace && node.ctx == ExprContext::Load {
                RouteWithheld::EscapedNamespace
            } else {
                RouteWithheld::EscapedWrite
            };
            self.escape(base, kind, self.module.location(node).line);
        } else if !child.is_empty() {
            self.escape(
                child,
                RouteWithheld::EscapedChildModule,
                self.module.location(node).line,
            );
        }
        true
    }
}

impl<'a> Visitor<'a> for Uses<'_, '_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Attribute(node) = expr {
            if self.attribute(node, expr) {
                return;
            }
        }
        let bare = self.denotes(expr);
        if !bare.is_empty() {
            let by_name = self.by_import(expr);
            let kind = if by_name {
                RouteWithheld::EscapedName
            } else {
                RouteWithheld::EscapedValue
            };
            self.escape(bare, kind, self.module.location(expr).line);
        }
        visitor::walk_expr(self, expr);
    }
}

/// The module that `importlib.import_module("m")` or `__import__("m")` names.
pub(super) fn literal_import(expr: &Expr) -> Option<String> {
    let Expr::Call(call) = expr else {
        return None;
    };
    let name = match &*call.func {
        Expr::Name(node) => node.id.to_string(),
        Expr::Attribute(node) => node.attr.to_string(),
        _ => return None,
    };
    if name != "import_module" && name != "__import__" {
        return None;
    }
    match call.arguments.args.first()? {
        Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
        _ => None,
    }
}
