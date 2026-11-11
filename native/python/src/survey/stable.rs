// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `source._stable_direct_module_bindings` with the import effects: the names that one top-level
//! statement binds once, that no other binder at module scope binds, that no `global` names,
//! and that no namespace exposure or member write can change.
//!
//! The member analysis is `_member_binding_roots` with `member_surface=False`: the roots of the
//! attribute writes, closed over the name-to-name assignments, and each import alias of a module
//! that a written plain import names.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::Visitor;
use ruff_python_ast::{Expr, ExprContext, Stmt};

use super::binders::{import_bindings, Binders};
use super::imports::Aliases;
use super::module::Module;
use super::walks::{Scope, Whole};

/// The stable bindings of one module, sorted. `minor` is the minor version of the interpreter.
pub fn bindings(module: &Module, binders: &Binders, aliases: &Aliases, minor: u32) -> Vec<String> {
    let direct = direct(&module.tree.body, minor);
    let whole = Whole::of(&module.tree, aliases, binders);
    if whole.rebinds {
        return Vec::new();
    }
    let scope = Scope::of(&module.tree, &whole.local);
    if scope.star || scope.exposed {
        return Vec::new();
    }
    let changed = changed_members(&whole, aliases);
    let mut names: Vec<String> = direct
        .into_iter()
        .filter(|(name, count)| {
            *count == 1
                && scope.counts.get(name.as_str()) == Some(&1)
                && !whole.globals.contains(name)
                && !changed.contains(name)
        })
        .map(|(name, _)| name)
        .collect();
    names.sort();
    names
}

/// How often each top-level definition, type alias, import or assignment binds a name.
fn direct(body: &[Stmt], minor: u32) -> HashMap<String, usize> {
    let mut direct: HashMap<String, usize> = HashMap::new();
    let mut add = |name: String| *direct.entry(name).or_default() += 1;
    for statement in body {
        match statement {
            Stmt::FunctionDef(node) => add(node.name.id.to_string()),
            Stmt::ClassDef(node) => add(node.name.id.to_string()),
            Stmt::TypeAlias(node) if minor >= 12 && !has_parameters(node) => {
                if let Expr::Name(name) = &*node.name {
                    add(name.id.to_string());
                }
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                import_bindings(statement).into_iter().for_each(&mut add)
            }
            Stmt::Assign(node) => {
                for target in &node.targets {
                    target_names(target).into_iter().for_each(&mut add);
                }
            }
            Stmt::AnnAssign(node) => target_names(&node.target).into_iter().for_each(&mut add),
            _ => {}
        }
    }
    direct
}

fn has_parameters(node: &ruff_python_ast::StmtTypeAlias) -> bool {
    node.type_params
        .as_ref()
        .is_some_and(|params| !params.type_params.is_empty())
}

/// `_bound_names(ast.walk(target))`: the stored or deleted names and the lambda parameters in
/// one assignment target.
fn target_names(target: &Expr) -> Vec<String> {
    struct Names(Vec<String>);
    impl<'a> Visitor<'a> for Names {
        fn visit_expr(&mut self, expr: &'a Expr) {
            match expr {
                Expr::Name(node) if matches!(node.ctx, ExprContext::Store | ExprContext::Del) => {
                    self.0.push(node.id.to_string());
                }
                _ => {}
            }
            ruff_python_ast::visitor::walk_expr(self, expr);
        }

        fn visit_parameter(&mut self, parameter: &'a ruff_python_ast::Parameter) {
            self.0.push(parameter.name.id.to_string());
            ruff_python_ast::visitor::walk_parameter(self, parameter);
        }
    }
    let mut names = Names(Vec::new());
    names.visit_expr(target);
    names.0
}

/// `_member_binding_roots(module, all_nodes, member_surface=False)`.
fn changed_members(whole: &Whole, aliases: &Aliases) -> HashSet<String> {
    let changed = closure(&whole.roots, &whole.pairs);
    let mut origins: HashSet<&str> = HashSet::new();
    for (name, asname) in &whole.imports {
        let root = name.split('.').next().unwrap_or(name);
        let binding = asname.as_deref().unwrap_or(root);
        if changed.contains(binding) {
            origins.insert(if asname.is_some() { name } else { root });
        }
    }
    let mut changed = changed;
    for (name, alias) in aliases {
        let origin = if alias.module {
            alias.target.as_str()
        } else {
            alias
                .target
                .rsplit_once('.')
                .map_or("", |(origin, _)| origin)
        };
        if origins.contains(origin) {
            changed.insert(name.clone());
        }
    }
    changed
}

/// `member_binding_closure` without the member surface: each name that an assignment of one
/// name to another connects to a root.
fn closure(roots: &HashSet<String>, pairs: &[(String, String)]) -> HashSet<String> {
    let mut changed = roots.clone();
    if changed.is_empty() {
        return changed;
    }
    let mut adjacent: HashMap<&str, Vec<&str>> = HashMap::new();
    for (name, value) in pairs {
        adjacent.entry(name).or_default().push(value);
        adjacent.entry(value).or_default().push(name);
    }
    let mut pending: Vec<String> = changed.iter().cloned().collect();
    while let Some(current) = pending.pop() {
        for value in adjacent.get(current.as_str()).into_iter().flatten() {
            if changed.insert((*value).to_owned()) {
                pending.push((*value).to_owned());
            }
        }
    }
    changed
}

#[cfg(test)]
#[path = "stable_tests.rs"]
mod tests;
