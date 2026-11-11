// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The two walks of `_stable_direct_module_bindings`.
//!
//! `Whole` reads each node of the module (`module.all_nodes`): the `global` names, the namespace
//! exposures, the roots of the member writes (`member_escape_references` without the member
//! surface), the name-to-name assignments of `member_binding_closure` and the plain imports.
//! `Scope` reads the nodes that the module itself evaluates (`_module_scope_nodes`): it counts
//! their binders (`scope_bound_names`) and finds a star import or a local namespace exposure.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::source_order::{self, SourceOrderVisitor, TraversalSignal};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Alias, AnyNodeRef, Comprehension, ExceptHandler, Expr, ExprContext, ModModule, Parameters,
    Pattern, Stmt, StmtClassDef, StmtFunctionDef,
};

use super::binders::{bind_handler, bind_pattern, declared, first_part, Bind, Binders};
use super::imports::Aliases;
use super::namespace::{exposure, reads_only, Exposure};

/// The address of a node, to find a node of the whole walk again in the scope walk.
fn address(node: AnyNodeRef) -> usize {
    node.as_ptr().as_ptr() as usize
}

/// The facts of the whole walk.
#[derive(Default)]
pub struct Whole {
    pub globals: HashSet<String>,
    /// An exposure in any scope that does more than read the names of the module.
    pub rebinds: bool,
    /// The local exposures that do more than read the names; they count at module scope only.
    pub local: HashSet<usize>,
    /// The names at the root of each attribute write or delete.
    pub roots: HashSet<String>,
    /// Each `name = other` and `name: T = other`, as (name, other).
    pub pairs: Vec<(String, String)>,
    /// Each alias of each `import` statement, as (name, asname).
    pub imports: Vec<(String, Option<String>)>,
}

impl Whole {
    pub fn of(tree: &ModModule, aliases: &Aliases, binders: &Binders) -> Self {
        let mut walk = WholeWalk {
            aliases,
            binders,
            parents: Vec::new(),
            found: Self::default(),
        };
        walk.visit_body(&tree.body);
        walk.found
    }
}

struct WholeWalk<'a, 'f> {
    aliases: &'f Aliases,
    binders: &'f Binders,
    parents: Vec<AnyNodeRef<'a>>,
    found: Whole,
}

impl<'a> WholeWalk<'a, '_> {
    fn exposure(&mut self, node: AnyNodeRef<'a>) {
        let kind = exposure(node, self.aliases);
        if kind == Exposure::None || reads_only(node, &self.parents, self.aliases, self.binders) {
            return;
        }
        match kind {
            Exposure::Global => self.found.rebinds = true,
            _ => drop(self.found.local.insert(address(node))),
        }
    }

    fn statement(&mut self, statement: &Stmt) {
        match statement {
            Stmt::Global(node) => {
                let names = node.names.iter().map(|name| name.id.to_string());
                self.found.globals.extend(names);
            }
            Stmt::Import(node) => {
                for alias in &node.names {
                    let asname = alias.asname.as_ref().map(|name| name.id.to_string());
                    self.found.imports.push((alias.name.id.to_string(), asname));
                }
            }
            Stmt::Assign(node) => {
                for target in &node.targets {
                    self.pair(target, &node.value);
                }
            }
            Stmt::AnnAssign(node) => {
                if let Some(value) = &node.value {
                    self.pair(&node.target, value);
                }
            }
            _ => {}
        }
    }

    fn pair(&mut self, target: &Expr, value: &Expr) {
        if let (Expr::Name(target), Expr::Name(value)) = (target, value) {
            let pair = (target.id.to_string(), value.id.to_string());
            self.found.pairs.push(pair);
        }
    }
}

impl<'a> SourceOrderVisitor<'a> for WholeWalk<'a, '_> {
    fn enter_node(&mut self, node: AnyNodeRef<'a>) -> TraversalSignal {
        self.exposure(node);
        match node {
            AnyNodeRef::ExprAttribute(attribute)
                if matches!(attribute.ctx, ExprContext::Store | ExprContext::Del) =>
            {
                let mut roots = Roots(&mut self.found.roots);
                roots.visit_expr(&attribute.value);
            }
            _ => {}
        }
        self.parents.push(node);
        TraversalSignal::Traverse
    }

    fn leave_node(&mut self, _node: AnyNodeRef<'a>) {
        self.parents.pop();
    }

    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.statement(stmt);
        source_order::walk_stmt(self, stmt);
    }
}

/// The names that `member_escape_references` yields below the value of one attribute write: a
/// name ends the path, an attribute passes on to its value, a call ends it without a name.
struct Roots<'r>(&'r mut HashSet<String>);

impl<'a> Visitor<'a> for Roots<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) => drop(self.0.insert(node.id.to_string())),
            Expr::Attribute(node) => self.visit_expr(&node.value),
            Expr::Call(_) => {}
            _ => visitor::walk_expr(self, expr),
        }
    }
}

/// The facts of the module scope walk.
pub struct Scope<'a> {
    /// `Counter(scope_bound_names)`.
    pub counts: HashMap<&'a str, usize>,
    pub star: bool,
    /// A local exposure of the whole walk is evaluated at module scope.
    pub exposed: bool,
}

impl<'a> Scope<'a> {
    pub fn of(tree: &'a ModModule, local: &HashSet<usize>) -> Self {
        let mut walk = ScopeWalk {
            local,
            found: Scope {
                counts: HashMap::new(),
                star: false,
                exposed: false,
            },
        };
        walk.visit_body(&tree.body);
        walk.found
    }
}

struct ScopeWalk<'a, 'l> {
    local: &'l HashSet<usize>,
    found: Scope<'a>,
}

impl<'a> ScopeWalk<'a, '_> {
    fn bind(&mut self, name: &'a str) {
        *self.found.counts.entry(name).or_default() += 1;
    }

    fn check(&mut self, node: AnyNodeRef) {
        if !self.local.is_empty() && self.local.contains(&address(node)) {
            self.found.exposed = true;
        }
    }

    /// `source._import_bindings`, as slices of the tree.
    fn imports(&mut self, names: &'a [Alias], dotted: bool) {
        for alias in names.iter().filter(|alias| alias.name.as_str() != "*") {
            let name = match &alias.asname {
                Some(asname) => asname.as_str(),
                None if dotted => first_part(alias.name.as_str()),
                None => alias.name.as_str(),
            };
            self.bind(name);
        }
    }

    /// A function header: decorators, defaults, annotations and the return annotation.
    fn function(&mut self, node: &'a StmtFunctionDef) {
        self.bind(node.name.as_str());
        for decorator in &node.decorator_list {
            self.visit_expr(&decorator.expression);
        }
        let parameters = &node.parameters;
        let all = parameters.posonlyargs.iter().chain(&parameters.args);
        for parameter in all.chain(&parameters.kwonlyargs) {
            if let Some(default) = &parameter.default {
                self.visit_expr(default);
            }
            if let Some(annotation) = &parameter.parameter.annotation {
                self.visit_expr(annotation);
            }
        }
        for parameter in [&parameters.vararg, &parameters.kwarg]
            .into_iter()
            .flatten()
        {
            if let Some(annotation) = &parameter.annotation {
                self.visit_expr(annotation);
            }
        }
        if let Some(returns) = &node.returns {
            self.visit_expr(returns);
        }
    }

    /// A class header: decorators, bases and keyword values.
    fn class(&mut self, node: &'a StmtClassDef) {
        self.bind(node.name.as_str());
        for decorator in &node.decorator_list {
            self.visit_expr(&decorator.expression);
        }
        if let Some(arguments) = &node.arguments {
            for base in &arguments.args {
                self.visit_expr(base);
            }
            for keyword in &arguments.keywords {
                self.visit_expr(&keyword.value);
            }
        }
    }

    /// The defaults of a lambda; its parameters and its body are not module scope.
    fn lambda_defaults(&mut self, parameters: &'a Parameters) {
        let all = parameters.posonlyargs.iter().chain(&parameters.args);
        for parameter in all.chain(&parameters.kwonlyargs) {
            if let Some(default) = &parameter.default {
                self.visit_expr(default);
            }
        }
    }

    /// The iterables and conditions of the generators; their targets are not module scope.
    fn generators(&mut self, generators: &'a [Comprehension]) {
        for generator in generators {
            self.visit_expr(&generator.iter);
            for condition in &generator.ifs {
                self.visit_expr(condition);
            }
        }
    }
}

impl<'a> Visitor<'a> for ScopeWalk<'a, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.check(AnyNodeRef::from(stmt));
        match stmt {
            Stmt::FunctionDef(node) => self.function(node),
            Stmt::ClassDef(node) => self.class(node),
            Stmt::Import(node) => self.imports(&node.names, true),
            Stmt::ImportFrom(node) => {
                if node.names.iter().any(|alias| alias.name.as_str() == "*") {
                    self.found.star = true;
                }
                self.imports(&node.names, false);
            }
            Stmt::Global(_) | Stmt::Nonlocal(_) => {
                declared(stmt)
                    .iter()
                    .for_each(|name| self.bind(name.as_str()));
            }
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        self.check(AnyNodeRef::from(expr));
        match expr {
            Expr::Name(node) => {
                if matches!(node.ctx, ExprContext::Store | ExprContext::Del) {
                    self.bind(node.id.as_str());
                }
            }
            Expr::Lambda(node) => {
                if let Some(parameters) = &node.parameters {
                    self.lambda_defaults(parameters);
                }
            }
            Expr::ListComp(node) => {
                self.visit_expr(&node.elt);
                self.generators(&node.generators);
            }
            Expr::SetComp(node) => {
                self.visit_expr(&node.elt);
                self.generators(&node.generators);
            }
            Expr::Generator(node) => {
                self.visit_expr(&node.elt);
                self.generators(&node.generators);
            }
            Expr::DictComp(node) => {
                if let Some(key) = &node.key {
                    self.visit_expr(key);
                }
                self.visit_expr(&node.value);
                self.generators(&node.generators);
            }
            _ => visitor::walk_expr(self, expr),
        }
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        bind_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        bind_pattern(self, pattern);
    }
}

impl<'a> Bind<'a> for ScopeWalk<'a, '_> {
    fn bind_name(&mut self, name: &'a str) {
        self.bind(name);
    }
}
