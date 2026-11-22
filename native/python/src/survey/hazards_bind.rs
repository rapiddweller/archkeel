// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that the import statements of a module bind, for the trojan horse check (AD-450, AD-472).

use std::collections::{HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::helpers::any_over_body;
use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, Identifier, ModModule, Stmt};

use crate::module::Module;

use super::reflect;

/// The qualified names that the import statements of a module bind, in any scope.
pub(super) fn bindings(tree: &ModModule) -> HashMap<String, Vec<String>> {
    struct Imports(HashMap<String, Vec<String>>);
    impl<'a> Visitor<'a> for Imports {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            for (name, origin) in bound(stmt) {
                self.0.entry(name).or_default().push(origin);
            }
            visitor::walk_stmt(self, stmt);
        }
    }
    let mut walk = Imports(HashMap::new());
    walk.visit_body(&tree.body);
    reflect::aliases(tree, &mut walk.0);
    walk.0
}

/// The names that one import statement binds and their qualified origins. A relative import
/// names a module of the project and binds nothing here.
fn bound(stmt: &Stmt) -> Vec<(String, String)> {
    match stmt {
        Stmt::Import(node) => node
            .names
            .iter()
            .map(|alias| {
                let name = alias.name.as_str();
                match &alias.asname {
                    Some(asname) => (asname.to_string(), name.to_owned()),
                    None => {
                        let first = name.split('.').next().unwrap_or(name);
                        (first.to_owned(), first.to_owned())
                    }
                }
            })
            .collect(),
        Stmt::ImportFrom(node) if node.level == 0 => {
            let module = node.module.as_ref().map_or("", |module| module.as_str());
            node.names
                .iter()
                .map(|alias| {
                    let name = alias.name.as_str();
                    let local = alias.asname.as_ref().map_or(name, |asname| asname.as_str());
                    (local.to_owned(), format!("{module}.{name}"))
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// The names that an import statement imports, as qualified names, for the trojan horse check: each
/// module of `import a.b`, and each name of `from m import n`. A star import names its module.
pub(super) fn imported(stmt: &Stmt) -> Vec<String> {
    match stmt {
        // A plain `import importlib` binds the module of the accepted literal call (AD-472);
        // each use of the name is still read. Each other import of `importlib` is a reference.
        Stmt::Import(node) => node
            .names
            .iter()
            .filter(|a| a.asname.is_some() || a.name.as_str() != "importlib")
            .map(|a| a.name.to_string())
            .collect(),
        Stmt::ImportFrom(node) if node.level == 0 => {
            let module = node.module.as_ref().map_or("", |module| module.as_str());
            node.names
                .iter()
                .map(|alias| match alias.name.as_str() {
                    "*" => module.to_owned(),
                    name => format!("{module}.{name}"),
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

/// The local name that `from m import n [as a]` binds for the qualified name `m.n`, if the
/// statement binds it (AD-664).
pub(super) fn local_of(stmt: &Stmt, qualified: &str) -> Option<String> {
    if let Stmt::Import(node) = stmt {
        // `import a.b` binds `a`; `import a.b as c` binds `c` (AD-1052).
        return node.names.iter().find_map(|alias| {
            let name = alias.name.as_str();
            let first = name.split('.').next().unwrap_or(name);
            (name == qualified).then(|| {
                alias
                    .asname
                    .as_ref()
                    .map_or(first, |asname| asname.as_str())
                    .to_owned()
            })
        });
    }
    let Stmt::ImportFrom(node) = stmt else {
        return None;
    };
    let module = node.module.as_ref().map_or("", |module| module.as_str());
    node.names.iter().find_map(|alias| {
        let name = alias.name.as_str();
        (format!("{module}.{name}") == qualified).then(|| {
            alias
                .asname
                .as_ref()
                .map_or(name, |asname| asname.as_str())
                .to_owned()
        })
    })
}

/// The attributes that read any attribute of a value: `m.__dict__[n]`, `C.__getattribute__(m, n)`,
/// `inspect.getmembers(m)` and `operator.attrgetter(n)`.
const ANY_ATTRIBUTE_READ: [&str; 4] = ["__dict__", "__getattribute__", "getmembers", "attrgetter"];

/// `vars(x)`, or `getattr`, `setattr` or `delattr` with a name that is no literal.
fn computed_read(call: &ExprCall) -> bool {
    let Expr::Name(func) = &*call.func else {
        return false;
    };
    let args: &[Expr] = &call.arguments.args;
    match Name::as_str(&func.id) {
        "vars" => true,
        "getattr" | "setattr" | "delattr" => !matches!(args.get(1), Some(Expr::StringLiteral(_))),
        _ => false,
    }
}

/// The dotted name that the expression `expr` has when it is the name `binding` or an attribute
/// chain on it: `binding` stands for the object `object`.
fn chain(expr: &Expr, binding: &str, object: &str) -> Option<String> {
    match expr {
        Expr::Name(node) => (Name::as_str(&node.id) == binding).then(|| object.to_owned()),
        Expr::Attribute(node) => {
            let base = chain(&node.value, binding, object)?;
            Some(format!("{base}.{}", Identifier::as_str(&node.attr)))
        }
        _ => None,
    }
}

/// True when `path` is the module or a package above it: its value holds the module.
fn holds(path: &str, module: &str) -> bool {
    module == path || module.starts_with(&format!("{path}."))
}

/// The names that the resolved import records bind to the module or to a package above it, for
/// each module of the scan, with the object that each name stands for (`import a.b.c` binds `a`;
/// `from a import b` binds `b` to `a.b`). A relative import, an `except` or `match` body and an
/// `async` block need no syntax: the records are resolved. A module that imports such a name from
/// another module (`from page import model`) holds the value too, so the names follow the
/// re-exports until no new module is reached.
fn bound_to(
    imports: &[Record<ImportFact>],
    module: &str,
) -> HashMap<String, Vec<(String, String)>> {
    let mut found: HashMap<String, Vec<(String, String)>> = HashMap::new();
    let all: Vec<&archkeel_facts::data::ImportData> = imports
        .iter()
        .map(|record| ImportFact::data(&record.data))
        .collect();
    for data in &all {
        let Some(binding) = data.binding.as_deref() else {
            continue;
        };
        let target = data.target_module.as_str();
        let first = target.split('.').next().unwrap_or(target);
        let object = match data.symbol.as_deref() {
            Some(symbol) => format!("{target}.{symbol}"),
            None if binding == first => first.to_owned(),
            None => target.to_owned(),
        };
        if holds(&object, module) {
            let names = found
                .entry(data.source_module.as_str().to_owned())
                .or_default();
            names.push((binding.to_owned(), object));
        }
    }
    loop {
        let mut more: Vec<(String, (String, String))> = Vec::new();
        for data in &all {
            let (Some(binding), Some(symbol)) = (data.binding.as_deref(), data.symbol.as_deref())
            else {
                continue;
            };
            let held = found.get(data.target_module.as_str());
            let same = held.iter().flat_map(|names| names.iter());
            let mut same = same;
            let name = same.find(|(held, _)| held == symbol || symbol == "*");
            let source = data.source_module.as_str();
            let new = |(_, object): &(String, String)| (binding.to_owned(), object.clone());
            let seen = |pair: &(String, String)| {
                found.get(source).is_some_and(|names| names.contains(pair))
            };
            if let Some(pair) = name.map(new).filter(|pair| !seen(pair)) {
                more.push((source.to_owned(), pair));
            }
        }
        if more.is_empty() {
            return found;
        }
        for (source, pair) in more {
            found.entry(source).or_default().push(pair);
        }
    }
}

/// True when the module value escapes the importer: a name that is bound to the module or to a
/// package above it is used where its chain ends at the module or above (`f(model)`, `return
/// app.service.model`, `m = svc.model`, `[model]`). Only a chain that goes on past the module
/// is an attribute read that the scan sees (AD-1058).
fn escapes(body: &[Stmt], bound: &[(String, String)], module: &str) -> bool {
    bound.iter().any(|(binding, object)| {
        let (mut all, mut bases) = (0_usize, 0_usize);
        let count = |expr: &Expr| {
            let held =
                |expr: &Expr| chain(expr, binding, object).is_some_and(|p| holds(&p, module));
            all += usize::from(held(expr));
            if let Expr::Attribute(node) = expr {
                bases += usize::from(held(&node.value));
            }
            false
        };
        any_over_body(body, count);
        all > bases
    })
}

/// The modules of the scan that can reach the name `binding` of the module `module` without a
/// record that names it: an attribute or a text of that name, in a module that imports `module`
/// or a package above it (`import m` then `m.pickle.loads`). A from-import and a star import are
/// records of the imports. A module that can read any attribute of a value by a name that the scan
/// cannot read (`getattr(m, 'pick' + 'le')`, `vars(m)`, `m.__dict__`) is exposed to every bound name
/// (AD-1058); a name built at run time through a text outside these forms stays the premise of
/// the run.
pub(in crate::survey) fn exposed(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    (module, binding): (&str, &Option<String>),
) -> Vec<String> {
    let Some(binding) = binding.as_deref() else {
        return Vec::new();
    };
    let above = |target: &str| module == target || module.starts_with(&format!("{target}."));
    let importers: HashSet<&str> = imports
        .iter()
        .map(|record| ImportFact::data(&record.data))
        .filter(|data| above(data.target_module.as_str()))
        .map(|data| data.source_module.as_str())
        .collect();
    let held = bound_to(imports, module);
    let mut found: Vec<String> = Vec::new();
    for other in modules {
        let names = held.get(other.name.as_str());
        if other.name == module || !(importers.contains(other.name.as_str()) || names.is_some()) {
            continue;
        }
        let named = |expr: &Expr| match expr {
            Expr::Attribute(node) => {
                let attr = Identifier::as_str(&node.attr);
                attr == binding || ANY_ATTRIBUTE_READ.contains(&attr)
            }
            Expr::StringLiteral(text) => text.value.to_str() == binding,
            Expr::Call(call) => computed_read(call),
            _ => false,
        };
        if any_over_body(&other.tree.body, named)
            || escapes(&other.tree.body, names.map_or(&[], Vec::as_slice), module)
        {
            found.push(other.name.clone());
        }
    }
    found.sort_unstable();
    found
}
