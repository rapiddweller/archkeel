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
//! - the receiver is a class of this module, a module that a plain `import` of this module binds,
//!   or a local that one assignment binds to the result of a loader call (that call is a site of
//!   its own). A name counts only when the module binds it exactly once, so no parameter, pattern,
//!   `except` target, loop target or nested name can rebind it.
//!
//! `self` and `cls` are no proof: `C.get(f, name)` calls a method with any first argument. A nested
//! function or a lambda has no proof of its own. The call must use the builtin `getattr` or
//! `setattr`, which the module does not shadow, or the method `__getattribute__` or `__setattr__`
//! of any class (`C.__getattribute__(x, name)` has the receiver `x`). A call through another name
//! (`g = getattr`) is not read.

use std::collections::HashSet;

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

/// What one outermost function proves: the names that hold one literal.
type Scope = HashSet<String>;

/// The proofs of the module and the sites found so far.
struct Trojans<'n> {
    single: &'n HashSet<String>,
    visible: &'n HashSet<String>,
    taken: HashSet<String>,
    classes: HashSet<String>,
    scope: Option<Scope>,
    depth: usize,
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
        scope: None,
        depth: 0,
        found: Vec::new(),
    };
    for stmt in &tree.body {
        if let Stmt::ClassDef(node) = stmt {
            if single.contains(Identifier::as_str(&node.name)) {
                walk.classes
                    .insert(Identifier::as_str(&node.name).to_owned());
            }
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

/// The builtins that read, write or list attributes by a name (`vars` lists them).
const BUILTIN_ACCESS: [&str; 4] = ["getattr", "setattr", "delattr", "vars"];
/// The functions of the standard library that read attributes by a name that the scan does not
/// follow, or hand out every attribute of a value, a code object among them.
const LIBRARY_ACCESS: [&str; 6] = [
    "attrgetter",
    "methodcaller",
    "getmembers",
    "getmembers_static",
    "get_referents",
    "get_referrers",
];
/// The methods that read or write an attribute of any value.
const METHOD_ACCESS: [&str; 3] = ["__getattribute__", "__setattr__", "__delattr__"];

/// `vars(x)` or `x.__dict__`: the dictionary of the attributes of any value.
fn dict_view(expr: &Expr) -> bool {
    match expr {
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == "__dict__",
        Expr::Call(call) => matches!(&*call.func, Expr::Name(n) if Name::as_str(&n.id) == "vars"),
        _ => false,
    }
}

impl Trojans<'_> {
    /// The scope of an outermost function: the names that hold one literal.
    fn scope_of(&self, def: &StmtFunctionDef) -> Scope {
        let mut literals = HashSet::new();
        let mut assigns = Assigns(Vec::new());
        assigns.visit_body(&def.body);
        for node in assigns.0 {
            let [Expr::Name(target)] = node.targets.as_slice() else {
                continue;
            };
            let id = Name::as_str(&target.id);
            // The module binds the name once: this assignment is its only binder.
            let once = !self.taken.contains(id) && self.single.contains(id);
            if once && matches!(&*node.value, Expr::StringLiteral(_)) {
                literals.insert(id.to_owned());
            }
        }
        literals
    }

    /// The access form that `expr` names: a visible builtin, a function of the library, or a
    /// method that reads or writes an attribute of any value.
    fn form(&self, expr: &Expr) -> Option<&'static str> {
        let (name, local) = match expr {
            Expr::Name(node) => (Name::as_str(&node.id), true),
            Expr::Attribute(node) => (Identifier::as_str(&node.attr), false),
            _ => return None,
        };
        let found = |list: &'static [&'static str]| list.iter().find(|each| **each == name);
        let builtin = found(&BUILTIN_ACCESS).filter(|_| local && self.visible.contains(name));
        let library = found(&LIBRARY_ACCESS);
        builtin
            .or(library)
            .or(found(&METHOD_ACCESS).filter(|_| !local))
            .copied()
    }

    /// The call that reads an attribute by a computed name: its form, its receiver and its name.
    /// A form that has no receiver to prove gives the callee for both.
    fn computed<'c>(&self, call: &'c ExprCall) -> Option<(&'static str, &'c Expr, &'c Expr)> {
        let args: &[Expr] = &call.arguments.args;
        let callee: &Expr = &call.func;
        let kind = self.form(callee)?;
        // `x.m(name)` has the receiver `x`; `C.m(x, name)` and `getattr(x, name)` have `x`.
        let bound = match kind {
            "__getattribute__" | "__delattr__" => 1,
            "__setattr__" => 2,
            "getattr" | "setattr" | "delattr" => 0,
            "vars" => return Some((kind, callee, callee)),
            _ => return Some((kind, callee, callee)),
        };
        match (callee, args) {
            (Expr::Attribute(node), [name, ..]) if args.len() == bound => {
                Some((kind, &*node.value, name))
            }
            (_, [receiver, name, ..]) if args.len() > bound => Some((kind, receiver, name)),
            _ => Some((kind, callee, callee)),
        }
    }

    /// True when the name is a literal or a local with one literal.
    fn resolved(&self, name: &Expr) -> bool {
        match (name, &self.scope) {
            (Expr::StringLiteral(_), _) => true,
            (Expr::Name(node), Some(literals)) => {
                HashSet::contains(literals, Name::as_str(&node.id))
            }
            _ => false,
        }
    }

    /// True when the receiver is a class of this module. A module is no proof: each module has
    /// `__builtins__` and `__loader__` (AD-1058).
    fn known(&self, receiver: &Expr) -> bool {
        matches!(receiver, Expr::Name(node) if HashSet::contains(&self.classes, Name::as_str(&node.id)))
    }
}

impl<'a> Trojans<'_> {
    /// A call of an access form: its site, if any. The callee is read here, so only its base and
    /// its arguments are visited; the result is true when the call was one.
    fn access_call(&mut self, call: &'a ExprCall) -> bool {
        let site = self.computed(call);
        let site = site.filter(|(_, receiver, name)| !self.resolved(name) && !self.known(receiver));
        if let Some((kind, _, _)) = site {
            self.found.push((kind, call.range()));
        }
        if self.form(&call.func).is_none() {
            return false;
        }
        if let Expr::Attribute(node) = &*call.func {
            self.visit_expr(&node.value);
        }
        for arg in &call.arguments.args {
            self.visit_expr(arg);
        }
        for key in &call.arguments.keywords {
            self.visit_expr(&key.value);
        }
        true
    }
}

impl<'a> Visitor<'a> for Trojans<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let outer = self.scope.take();
        let depth = self.depth;
        match stmt {
            Stmt::FunctionDef(def) => {
                self.depth += 1;
                // Only an outermost function has a proof; a nested one has none (it can rebind).
                self.scope = (depth == 0).then(|| self.scope_of(def));
            }
            _ => self.scope = outer.clone(),
        }
        visitor::walk_stmt(self, stmt);
        self.depth = depth;
        self.scope = outer;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Call(call) if self.access_call(call) => return,
            // `x.__dict__` and `vars(x)` hand out the dictionary of the attributes of any value: a
            // key that the scan cannot read reaches `__builtins__` and `__code__`. Only a direct
            // subscript with a literal key is no site; `d = vars(m)` is one (AD-1058).
            Expr::Subscript(node) if dict_view(&node.value) => {
                if !self.resolved(&node.slice) {
                    self.found.push(("__dict__", node.range()));
                }
                match &*node.value {
                    Expr::Attribute(inner) => self.visit_expr(&inner.value),
                    Expr::Call(inner) => {
                        inner.arguments.args.iter().for_each(|a| self.visit_expr(a))
                    }
                    _ => {}
                }
                return self.visit_expr(&node.slice);
            }
            Expr::Attribute(node) if Identifier::as_str(&node.attr) == "__dict__" => {
                self.found.push(("__dict__", expr.range()));
            }
            // A form that is no callee is a call that the scan does not follow: `g = getattr`,
            // `map(getattr, ...)`, `partial(getattr, f)`, `ga = f.__getattribute__` (AD-1058).
            Expr::Name(_) | Expr::Attribute(_) if self.form(expr).is_some() => {
                self.found.push(("value", expr.range()));
            }
            _ => {}
        }
        let outer = self.scope.take();
        // A lambda has no proof: its parameters can rebind a name.
        self.scope = if matches!(expr, Expr::Lambda(_)) {
            None
        } else {
            outer.clone()
        };
        visitor::walk_expr(self, expr);
        self.scope = outer;
    }
}
