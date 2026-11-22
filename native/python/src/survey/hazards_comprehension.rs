// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Comprehension target scope for the import hazard survey, and the function scopes of a computed
//! attribute name (AD-1052, #1967).
//!
//! `getattr(x, name)`, `setattr(x, name, v)` and `x.__getattribute__(name)` give any attribute of
//! `x`, such as `__code__`, `__globals__` or `__self__`, when `name` is no literal. A name that the
//! scan cannot read is a trojan horse: a place that can load code the scan does not see. It is
//! not a claim of malice. The site is a `dynamic_import` gap, and a contract can declare it by
//! its name (`getattr`, `setattr`, `__getattribute__`). The site is no gap when
//! - the name is a string literal (`hazards.rs` reads it), or a local of the function that one
//!   assignment binds to a string literal;
//! - the receiver is a class of this module, the `self` or `cls` of a method that does not rebind
//!   it, a module that a plain `import` of this module binds, or a local that one assignment binds
//!   to the result of a loader call (that call is a site of its own).
//!
//! The call must use the builtin `getattr` or `setattr`, which the module does not shadow. A call
//! through another name (`g = getattr`) is not read.

use std::collections::HashSet;

use ruff_python_ast::helpers::any_over_body;
use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Comprehension, Expr, ExprCall, ExprContext, Identifier, ModModule, Stmt, StmtFunctionDef,
};
use ruff_text_size::{Ranged, TextRange};

/// The first generator, later generators, local names and result expressions.
type Parts<'a> = (
    &'a Comprehension,
    &'a [Comprehension],
    HashSet<String>,
    Vec<&'a Expr>,
);

/// The comprehension parts and its local targets; the first iterable has the enclosing scope.
pub(super) fn parts(expr: &Expr) -> Option<Parts<'_>> {
    let generators: &[Comprehension] = match expr {
        Expr::Generator(node) => &node.generators,
        Expr::DictComp(node) => &node.generators,
        Expr::SetComp(node) => &node.generators,
        Expr::ListComp(node) => &node.generators,
        _ => return None,
    };
    let (first, rest) = generators.split_first()?;
    let mut targets = Targets::default();
    for generator in generators {
        targets.visit_expr(&generator.target);
    }
    let mut values = Vec::new();
    match expr {
        Expr::Generator(node) => values.push(node.elt.as_ref()),
        Expr::DictComp(node) => {
            values.extend(node.key.as_deref());
            values.push(node.value.as_ref());
        }
        Expr::SetComp(node) => values.push(node.elt.as_ref()),
        Expr::ListComp(node) => values.push(node.elt.as_ref()),
        _ => return None,
    }
    Some((first, rest, targets.0, values))
}

#[derive(Default)]
struct Targets(HashSet<String>);

impl<'a> Visitor<'a> for Targets {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(name) = expr {
            if name.ctx == ExprContext::Store {
                self.0.insert(name.id.to_string());
            }
        }
        visitor::walk_expr(self, expr);
    }
}

/// What one outermost function proves: its own receiver, the names that hold one literal and the
/// names that hold the module that a loader call returned.
type Scope = (Option<String>, HashSet<String>, HashSet<String>);

/// The proofs of the module and the sites found so far.
struct Trojans<'n> {
    single: &'n HashSet<String>,
    visible: &'n HashSet<String>,
    taken: HashSet<String>,
    classes: HashSet<String>,
    modules: HashSet<String>,
    scope: Option<Scope>,
    depth: usize,
    class: bool,
    found: Vec<(&'static str, TextRange)>,
}

/// The sites of the module: a computed attribute name on a receiver that is not proven. `names`
/// holds the unique names, the names bound once and the visible builtins (`Binders::proof_facts`).
pub(super) fn trojans(
    (tree, module): (&ModModule, &str),
    names: &(HashSet<String>, HashSet<String>, HashSet<String>),
) -> Vec<(&'static str, TextRange)> {
    // The premise of the run: code outside the scan roots writes no binding of the scan (AD-1053).
    // The name of such a file starts with `<`, which no module of the scan can (`outside.rs`).
    if module.starts_with('<') {
        return Vec::new();
    }
    let (_, single, visible) = names;
    let mut walk = Trojans {
        single,
        visible,
        taken: HashSet::new(),
        classes: HashSet::new(),
        modules: HashSet::new(),
        scope: None,
        depth: 0,
        class: false,
        found: Vec::new(),
    };
    for stmt in &tree.body {
        match stmt {
            Stmt::ClassDef(node) if single.contains(Identifier::as_str(&node.name)) => {
                walk.classes
                    .insert(Identifier::as_str(&node.name).to_owned());
            }
            Stmt::Import(node) => {
                for alias in &node.names {
                    let first = Identifier::as_str(&alias.name)
                        .split('.')
                        .next()
                        .unwrap_or("");
                    let bound = alias.asname.as_ref().map_or(first, Identifier::as_str);
                    let once = single.contains(bound);
                    once.then(|| walk.modules.insert(bound.to_owned()));
                }
            }
            _ => {}
        }
    }
    let mut globals = Declared(HashSet::new());
    globals.visit_body(&tree.body);
    walk.taken = globals.0;
    walk.visit_body(&tree.body);
    walk.found
}

/// The assignments of a function body, without the bodies of nested functions and classes.
struct Assigns<'a>(Vec<&'a ruff_python_ast::StmtAssign>);

impl<'a> Visitor<'a> for Assigns<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {}
            Stmt::Assign(node) => self.0.push(node),
            _ => visitor::walk_stmt(self, stmt),
        }
    }
}

/// The names that a `global` or `nonlocal` statement names.
struct Declared(HashSet<String>);

impl<'a> Visitor<'a> for Declared {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let listed: &[Identifier] = match stmt {
            Stmt::Global(node) => &node.names,
            Stmt::Nonlocal(node) => &node.names,
            _ => &[],
        };
        self.0.extend(
            listed
                .iter()
                .map(|name| Identifier::as_str(name).to_owned()),
        );
        visitor::walk_stmt(self, stmt);
    }
}

/// True for the callee of a loader call: `import_module`, `x.import_module` or `__import__`.
fn loader(func: &Expr) -> bool {
    match func {
        Expr::Name(node) => matches!(Name::as_str(&node.id), "import_module" | "__import__"),
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == "import_module",
        _ => false,
    }
}

impl Trojans<'_> {
    /// The scope of an outermost function: the receiver of a method and the literal names.
    fn scope_of(&self, def: &StmtFunctionDef) -> Scope {
        let plain = !def.decorator_list.iter().any(|item| {
            matches!(&item.expression, Expr::Name(name) if Name::as_str(&name.id) == "staticmethod")
        });
        let first = def.parameters.iter_non_variadic_params().next();
        let own = first.map(|param| Identifier::as_str(&param.parameter.name).to_owned());
        let rebound = |own: &str| {
            any_over_body(&def.body, |expr| {
                matches!(expr, Expr::Name(node)
                    if Name::as_str(&node.id) == own && node.ctx != ExprContext::Load)
            })
        };
        let receiver = own.filter(|own| self.class && plain && !rebound(own));
        let mut literals = HashSet::new();
        let mut loaders: Vec<(String, usize)> = Vec::new();
        let mut assigns = Assigns(Vec::new());
        assigns.visit_body(&def.body);
        for node in assigns.0 {
            let [Expr::Name(target)] = node.targets.as_slice() else {
                continue;
            };
            let id = Name::as_str(&target.id);
            if self.taken.contains(id) {
                continue;
            }
            match &*node.value {
                Expr::StringLiteral(_) if self.single.contains(id) => {
                    literals.insert(id.to_owned());
                }
                Expr::Call(call) if loader(&call.func) => loaders.push((id.to_owned(), 1)),
                _ => {}
            }
        }
        // A local is a loaded module when each store of it in the function is a loader call.
        let stores = |id: &str| {
            let mut count = 0_usize;
            let each = |expr: &Expr| {
                count += usize::from(
                    matches!(expr, Expr::Name(n) if Name::as_str(&n.id) == id && n.ctx == ExprContext::Store),
                );
                false
            };
            any_over_body(&def.body, each);
            count
        };
        let loaded: HashSet<String> = loaders
            .iter()
            .map(|(id, _)| id.clone())
            .filter(|id| stores(id) == loaders.iter().filter(|(other, _)| other == id).count())
            .collect();
        (receiver, literals, loaded)
    }

    /// The call that reads an attribute by a computed name: its form, its receiver and its name.
    fn computed<'c>(&self, call: &'c ExprCall) -> Option<(&'static str, &'c Expr, &'c Expr)> {
        let args: &[Expr] = &call.arguments.args;
        match &*call.func {
            Expr::Name(node) => {
                let kind = match Name::as_str(&node.id) {
                    "getattr" => "getattr",
                    "setattr" => "setattr",
                    _ => return None,
                };
                let [receiver, name, ..] = args else {
                    return None;
                };
                HashSet::contains(self.visible, kind).then_some((kind, receiver, name))
            }
            Expr::Attribute(node) if Identifier::as_str(&node.attr) == "__getattribute__" => {
                let object = matches!(&*node.value, Expr::Name(base)
                    if Name::as_str(&base.id) == "object");
                match (object, args) {
                    (true, [receiver, name, ..]) => Some(("__getattribute__", receiver, name)),
                    (false, [name, ..]) => Some(("__getattribute__", &*node.value, name)),
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// True when the name is a literal or a local with one literal.
    fn resolved(&self, name: &Expr) -> bool {
        match (name, &self.scope) {
            (Expr::StringLiteral(_), _) => true,
            (Expr::Name(node), Some((_, literals, _))) => {
                HashSet::contains(literals, Name::as_str(&node.id))
            }
            _ => false,
        }
    }

    /// True when the receiver is a class or a module of this module, or the `self` of the method.
    fn known(&self, receiver: &Expr) -> bool {
        let Expr::Name(node) = receiver else {
            return false;
        };
        let id = Name::as_str(&node.id);
        let own = self.scope.as_ref().and_then(|(own, ..)| own.as_deref());
        let loaded = self
            .scope
            .as_ref()
            .is_some_and(|(_, _, held)| HashSet::contains(held, id));
        HashSet::contains(&self.classes, id)
            || HashSet::contains(&self.modules, id)
            || loaded
            || own == Some(id)
    }
}

impl<'a> Visitor<'a> for Trojans<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let (class, depth) = (self.class, self.depth);
        match stmt {
            Stmt::ClassDef(_) => self.class = true,
            Stmt::FunctionDef(def) => {
                if depth == 0 {
                    self.scope = Some(self.scope_of(def));
                }
                self.depth += 1;
                self.class = false;
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
        (self.class, self.depth) = (class, depth);
        if depth == 0 && matches!(stmt, Stmt::FunctionDef(_)) {
            self.scope = None;
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            let computed = self.computed(call);
            let site = computed
                .filter(|(_, receiver, name)| !self.resolved(name) && !self.known(receiver));
            if let Some((kind, _, _)) = site {
                self.found.push((kind, call.range()));
            }
        }
        visitor::walk_expr(self, expr);
    }
}
