// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Comprehension target scope for the import hazard survey, and the sites of an access by a name
//! that the scan cannot read (AD-1053, AD-1058, #1967).
//!
//! `getattr(x, name)`, `setattr(x, name, v)` and `x.__getattribute__(name)` give any attribute of
//! `x`, such as `__code__`, `__globals__` or `__builtins__`, when `name` is no literal. A place
//! that does this is a trojan horse: a place that can load code the scan does not see. It is not a
//! claim of malice. The site is a `dynamic_import` gap, and a contract can declare it by its name.
//!
//! The collector clears only what is obviously safe. A call is no site when the name is a string
//! literal, or a local that the module binds exactly once, in an outermost function, to a string
//! literal. No receiver is proven: not `self`, not a class (a decorator or a store through an alias
//! can replace it), not a module (each module has `__builtins__`). A nested function or a lambda
//! has no scope of its own.
//!
//! These forms are sites: a call of the builtin `getattr`, `setattr`, `delattr` or `vars`, or of a
//! method `__getattribute__`, `__setattr__` or `__delattr__`, with an unproven name; each call of
//! `attrgetter`, `methodcaller`, `getmembers`, `getmembers_static`, `getattr_static`,
//! `get_referents` or `get_referrers`; each import of one of these names (an alias hides the use);
//! each reference to one of them that is no direct call (`g = getattr`, `map(getattr, xs)`);
//! `x.__dict__` and `vars(x)`, except directly subscripted with a literal key. The builtin must
//! not be shadowed in the module.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::name::Name;

use crate::survey::hazards_names::module_hazard;
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
    /// The attributes that a call or a longer chain reads further: they are no value (AD-1152).
    bases: HashSet<TextRange>,
    reexports: &'n HashMap<String, Vec<String>>,
    imports: HashMap<String, Vec<String>>,
    single: &'n HashSet<String>,
    visible: &'n HashSet<String>,
    taken: HashSet<String>,
    scope: Option<Scope>,
    depth: usize,
    found: Vec<(&'static str, TextRange)>,
}

/// The sites of the module: a computed attribute name on a receiver that is not proven. `names`
/// holds the unique names, the names bound once and the visible builtins (`Binders::proof_facts`).
pub(in crate::survey) fn trojans(
    (tree, module): (&ModModule, &str),
    names: &(HashSet<String>, HashSet<String>, HashSet<String>),
    reexports: &HashMap<String, Vec<String>>,
) -> Vec<(&'static str, TextRange)> {
    // The premise of the run: code outside the scan roots writes no binding of the scan (AD-1053).
    // The name of such a file starts with `<`, which no module of the scan can (`outside.rs`).
    if module.starts_with('<') {
        return Vec::new();
    }
    let (_, single, visible) = names;
    let mut walk = Trojans {
        bases: HashSet::new(),
        reexports,
        imports: super::bind::bindings(tree),
        single,
        visible,
        taken: HashSet::new(),
        scope: None,
        depth: 0,
        found: Vec::new(),
    };
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
const LIBRARY_ACCESS: [&str; 7] = [
    "attrgetter",
    "methodcaller",
    "getmembers",
    "getmembers_static",
    "getattr_static",
    "get_referents",
    "get_referrers",
];
/// The methods that read or write an attribute of any value.
const METHOD_ACCESS: [&str; 3] = ["__getattribute__", "__setattr__", "__delattr__"];

/// The dunder names that hand out no reflection: a read of one gives a text or a list of texts.
const PLAIN_DUNDER: [&str; 7] = [
    "__name__",
    "__doc__",
    "__file__",
    "__version__",
    "__all__",
    "__module__",
    "__qualname__",
];

/// True when reading the attribute `name` by a literal still hands out reflection that no other
/// rule reads (AD-1058): a dunder name but `PLAIN_DUNDER` (`__dict__`, `__getattribute__`,
/// `__class__`, `__init__`, ...) and the name of an access form. The names of
/// `TROJAN_HORSE_STRINGS` (`__globals__`, `f_builtins`) and the trojan horse attributes have their
/// own hazard, so they are no second site.
pub(super) fn reflective(name: &str) -> bool {
    let dunder = name.len() > 4 && name.starts_with("__") && name.ends_with("__");
    let own = crate::survey::hazards_names::TROJAN_HORSE_STRINGS.contains(&name)
        || crate::survey::hazards_names::attribute_trojan_horse(&[name], 0);
    let access = BUILTIN_ACCESS
        .iter()
        .chain(&LIBRARY_ACCESS)
        .chain(&METHOD_ACCESS)
        .any(|each| *each == name);
    // A write of a literal dunder (`setattr(C, '__call__', f)`, `C.__call__ = f`) changes what a later plain
    // call, access or construction runs: it is a site like a read (AD-1058, #1979).
    (dunder && !PLAIN_DUNDER.contains(&name) && !own) || access
}

/// True when the attribute that a store or a delete names is a literal dunder that a site reads (#1979).
fn written(node: &ruff_python_ast::ExprAttribute) -> bool {
    site(Identifier::as_str(&node.attr), true)
}

/// The exception-chain names: Python reads them to print a traceback and never calls them as a hook. A write
/// of one changes no import and no call (#2090). A read of `__traceback__` hands out frames, so only a write is clear.
const CHAIN_WRITES: [&str; 5] = [
    "__cause__",
    "__context__",
    "__traceback__",
    "__suppress_context__",
    "__notes__",
];

/// True when a literal name is a site: a read by `reflective`, a write unless it is an exception-chain name.
fn site(name: &str, write: bool) -> bool {
    reflective(name) && !(write && CHAIN_WRITES.contains(&name))
}

/// `vars(x)` or `x.__dict__`: the dictionary of the attributes of any value.
fn dict_view(expr: &Expr) -> bool {
    match expr {
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == "__dict__",
        Expr::Call(call) => matches!(&*call.func, Expr::Name(n) if Name::as_str(&n.id) == "vars"),
        _ => false,
    }
}

/// A call of an access form: its form, its name and whether the form writes.
struct Access<'c> {
    kind: &'static str,
    name: &'c Expr,
    write: bool,
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
            let plain =
                matches!(&*node.value, Expr::StringLiteral(t) if !reflective(t.value.to_str()));
            if once && plain {
                literals.insert(id.to_owned());
            }
        }
        literals
    }

    /// A literal key that names a re-exported module (`getattr(util, 'cp')`, `vars(util)['cp']`):
    /// the read hands the module on as a value (AD-1152).
    fn named(&self, key: &Expr) -> bool {
        matches!(key, Expr::StringLiteral(text) if self.reexports.contains_key(text.value.to_str()))
    }

    /// `vars(m)` and `m.__dict__` of a name that an import binds to a module with hazard names.
    fn module_value(&self, view: &Expr) -> bool {
        let base = match view {
            Expr::Attribute(node) => &*node.value,
            Expr::Call(call) => call.arguments.args.first().unwrap_or(view),
            _ => return false,
        };
        let Expr::Name(name) = base else { return false };
        let origins = self.imports.get(Name::as_str(&name.id));
        origins.is_some_and(|all| all.iter().any(|origin| module_hazard(origin).is_some()))
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
    fn computed<'c>(&self, call: &'c ExprCall) -> Option<Access<'c>> {
        let args: &[Expr] = &call.arguments.args;
        let callee: &Expr = &call.func;
        let kind = self.form(callee)?;
        let whole = |write| Access {
            kind,
            name: callee,
            write,
        };
        // `x.m(name)` has the receiver `x`; `C.m(x, name)` and `getattr(x, name)` have `x`. The class of the
        // form says whether it writes: only a write can use the exception-chain exemption (#2090).
        let (bound, write) = match kind {
            "__getattribute__" => (1, false),
            "__delattr__" => (1, true),
            "__setattr__" => (2, true),
            "getattr" => (0, false),
            "setattr" | "delattr" => (0, true),
            _ => return Some(whole(false)),
        };
        match (callee, args) {
            (Expr::Attribute(node), [name, ..]) if args.len() == bound => {
                Some(Access { kind, name, write })
            }
            (_, [_, name, ..]) if args.len() > bound => Some(Access { kind, name, write }),
            _ => Some(whole(write)),
        }
    }

    /// True when the name is a literal or a local with one literal.
    fn resolved(&self, name: &Expr, write: bool) -> bool {
        match (name, &self.scope) {
            (Expr::StringLiteral(text), _) => !site(text.value.to_str(), write),
            (Expr::Name(node), Some(literals)) => {
                HashSet::contains(literals, Name::as_str(&node.id))
            }
            _ => false,
        }
    }
}

impl<'a> Trojans<'_> {
    /// A call of an access form: its site, if any. The callee is read here, so only its base and
    /// its arguments are visited; the result is true when the call was one.
    fn access_call(&mut self, call: &'a ExprCall) -> bool {
        let site = self.computed(call);
        let site = site.filter(|access| {
            !self.resolved(access.name, access.write) || (!access.write && self.named(access.name))
        });
        if let Some(access) = site {
            self.found.push((access.kind, call.range()));
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
            Stmt::ImportFrom(node) => {
                // `from inspect import getmembers as gm`: the alias hides each later use.
                let named = node
                    .names
                    .iter()
                    .filter(|alias| LIBRARY_ACCESS.contains(&Identifier::as_str(&alias.name)));
                self.found
                    .extend(named.map(|alias| ("getattr_value", alias.range())));
                self.scope = outer.clone();
            }
            _ => self.scope = outer.clone(),
        }
        visitor::walk_stmt(self, stmt);
        self.depth = depth;
        self.scope = outer;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        let further = match expr {
            Expr::Call(call) => Some(&*call.func),
            Expr::Attribute(node) => Some(&*node.value),
            _ => None,
        };
        self.bases.extend(
            further
                .filter(|inner| matches!(inner, Expr::Attribute(_)))
                .map(Ranged::range),
        );
        // A re-exported module that is read as a value flows on unseen: `cp = util.cp`.
        if matches!(expr, Expr::Attribute(node) if node.ctx == ExprContext::Load && self.reexports.contains_key(node.attr.as_str()))
            && !self.bases.contains(&expr.range())
        {
            self.found.push(("module_value", expr.range()));
        }
        match expr {
            Expr::Call(call) if self.access_call(call) => return,
            // `x.__dict__` and `vars(x)` hand out the dictionary of the attributes of any value: a
            // key that the scan cannot read reaches `__builtins__` and `__code__`. Only a direct
            // subscript with a literal key is no site; `d = vars(m)` is one (AD-1058).
            Expr::Subscript(node) if dict_view(&node.value) => {
                if !self.resolved(&node.slice, false)
                    || self.module_value(&node.value)
                    || (node.ctx == ExprContext::Load && self.named(&node.slice))
                {
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
            // `K.__call__ = f` and `del K.__call__` write a literal dunder: the same site as `setattr`.
            Expr::Attribute(node) if node.ctx != ExprContext::Load && written(node) => {
                let kind = if node.ctx == ExprContext::Del {
                    "delattr"
                } else {
                    "setattr"
                };
                self.found.push((kind, expr.range()));
            }
            // A form that is no callee is a call that the scan does not follow: `g = getattr`,
            // `map(getattr, ...)`, `partial(getattr, f)`, `ga = f.__getattribute__` (AD-1058).
            Expr::Name(_) | Expr::Attribute(_) if self.form(expr).is_some() => {
                self.found.push(("getattr_value", expr.range()));
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
