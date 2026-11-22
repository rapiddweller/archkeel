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

/// The names that the import statements of `body` bind to `module` or to a package above it,
/// at any depth of the compound statements.
fn bound_to(body: &[Stmt], module: &str, found: &mut Vec<String>) {
    let above = |name: &str| module == name || module.starts_with(&format!("{name}."));
    for stmt in body {
        match stmt {
            Stmt::Import(node) => {
                for alias in node.names.iter().filter(|alias| above(alias.name.as_str())) {
                    let first = alias.name.as_str().split('.').next().unwrap_or("");
                    found.push(
                        alias
                            .asname
                            .as_ref()
                            .map_or(first, |a| a.as_str())
                            .to_owned(),
                    );
                }
            }
            Stmt::ImportFrom(node) if node.level == 0 => {
                let from = node.module.as_ref().map_or("", |name| name.as_str());
                let hits = node
                    .names
                    .iter()
                    .filter(|alias| above(&format!("{from}.{}", alias.name.as_str())));
                let names = hits.map(|alias| alias.asname.as_ref().unwrap_or(&alias.name));
                found.extend(names.map(|name| name.as_str().to_owned()));
            }
            Stmt::FunctionDef(node) => bound_to(&node.body, module, found),
            Stmt::ClassDef(node) => bound_to(&node.body, module, found),
            Stmt::If(node) => {
                bound_to(&node.body, module, found);
                for clause in &node.elif_else_clauses {
                    bound_to(&clause.body, module, found);
                }
            }
            Stmt::Try(node) => {
                bound_to(&node.body, module, found);
                bound_to(&node.orelse, module, found);
                bound_to(&node.finalbody, module, found);
            }
            Stmt::With(node) => bound_to(&node.body, module, found),
            Stmt::For(node) => bound_to(&node.body, module, found),
            Stmt::While(node) => bound_to(&node.body, module, found),
            _ => {}
        }
    }
}

/// True when the module value escapes the importer: a name that is bound to it is used other than
/// as the base of an attribute (`f(model)`, `return model`, `x = model`, `[model]`). Then any
/// attribute of it can be read where the scan does not look (AD-1058).
fn escapes(body: &[Stmt], module: &str) -> bool {
    let mut names = Vec::new();
    bound_to(body, module, &mut names);
    names.iter().any(|name| {
        let (mut loads, mut bases) = (0_usize, 0_usize);
        let count = |expr: &Expr| {
            match expr {
                Expr::Name(node) if Name::as_str(&node.id) == name => loads += 1,
                Expr::Attribute(node) => {
                    let base = matches!(&*node.value, Expr::Name(n) if Name::as_str(&n.id) == name);
                    bases += usize::from(base);
                }
                _ => {}
            }
            false
        };
        any_over_body(body, count);
        loads > bases
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
    let mut found: Vec<String> = Vec::new();
    for other in modules {
        if other.name == module || !importers.contains(other.name.as_str()) {
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
        if any_over_body(&other.tree.body, named) || escapes(&other.tree.body, module) {
            found.push(other.name.clone());
        }
    }
    found.sort_unstable();
    found
}
