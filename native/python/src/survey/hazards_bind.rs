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
use crate::survey::hazards_names::star;

/// The qualified names that the import statements of a module bind, in any scope.
pub(in crate::survey) fn bindings(tree: &ModModule) -> HashMap<String, Vec<String>> {
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
                    "*" => star(module),
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

/// A loader call with a name that is no literal: `import_module(name)`, `__import__(name)`.
fn computed_loader(call: &ExprCall) -> bool {
    let func = match &*call.func {
        Expr::Name(node) => Name::as_str(&node.id),
        Expr::Attribute(node) => Identifier::as_str(&node.attr),
        _ => return false,
    };
    let first = call.arguments.args.first();
    matches!(func, "import_module" | "__import__") && !matches!(first, Some(Expr::StringLiteral(_)))
}

/// The modules of the scan that can reach the name `binding` of the module `module` (AD-1058). To
/// obtain the binding from outside its module, the scan must contain the NAME in one of these
/// forms: an attribute of that name on any value, a string literal that is the name or that ends
/// with `.name` or starts with `name.`, an import of the name (`from x import name`), or a star
/// import of the module or of a module that imports it (through the resolved records). Any other
/// way is a computed access, and each of these is a site already: a read of any attribute by a
/// name that is no literal (`getattr`, `vars`, `__dict__`, `getmembers`) and a loader call with a
/// computed name refuse the declaration too. Inside the module itself, any load of the name that is
/// no attribute base refuses it, and so does a string of that name (`__all__`). A plain `import name` of the standard module is no
/// use of the binding. A module of `covers` is accepted by the model, not here.
pub(in crate::survey) fn exposed(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    (module, binding): (&str, &Option<String>),
) -> Vec<String> {
    let Some(binding) = binding.as_deref() else {
        return Vec::new();
    };
    // The module and each module that imports it: a star import of one of them gives the name.
    let mut reach: HashSet<&str> = HashSet::from([module]);
    let all: Vec<&archkeel_facts::data::ImportData> = imports
        .iter()
        .map(|record| ImportFact::data(&record.data))
        .collect();
    loop {
        let more: Vec<&str> = (all.iter())
            .filter(|data| reach.contains(data.target_module.as_str()))
            .map(|data| data.source_module.as_str())
            .filter(|source| !reach.contains(source))
            .collect();
        if more.is_empty() {
            break;
        }
        reach.extend(more);
    }
    let from_import = |data: &archkeel_facts::data::ImportData| {
        let symbol = data.symbol.as_deref();
        symbol == Some(binding)
            || (symbol == Some("*") && reach.contains(data.target_module.as_str()))
    };
    let by_record: HashSet<&str> = all
        .iter()
        .copied()
        .filter(|data| from_import(data))
        .map(|data| data.source_module.as_str())
        .collect();
    let (dotted, prefix) = (format!(".{binding}"), format!("{binding}."));
    let named = |expr: &Expr| match expr {
        Expr::Attribute(node) => {
            let attr = Identifier::as_str(&node.attr);
            attr == binding || ANY_ATTRIBUTE_READ.contains(&attr)
        }
        Expr::StringLiteral(text) => {
            let text = text.value.to_str();
            text == binding || text.ends_with(&dotted) || text.starts_with(&prefix)
        }
        Expr::Call(call) => computed_read(call) || computed_loader(call),
        _ => false,
    };
    let mut found: Vec<String> = Vec::new();
    // Inside the module: the name is only the base of an attribute (`pickle.loads(...)`) or a callee. Each
    // other load hands the value out under another name (`HELPER = pickle`, `return pickle`,
    // `class K: p = pickle`, `__all__ = ['pickle']`), and the scan would not see the name outside.
    let (mut loads, mut bases) = (0_usize, 0_usize);
    let own = |expr: &Expr| {
        match expr {
            Expr::Name(node) => loads += usize::from(Name::as_str(&node.id) == binding),
            Expr::StringLiteral(text) => loads += usize::from(text.value.to_str() == binding),
            // A call of the name (`import_module(x)`) hands out no value.
            Expr::Call(call) => {
                bases += usize::from(
                    matches!(&*call.func, Expr::Name(n) if Name::as_str(&n.id) == binding),
                );
            }
            Expr::Attribute(node) => {
                bases += usize::from(
                    matches!(&*node.value, Expr::Name(n) if Name::as_str(&n.id) == binding),
                );
            }
            _ => {}
        }
        false
    };
    if let Some(home) = modules.iter().find(|home| home.name == module) {
        any_over_body(&home.tree.body, own);
    }
    if loads > bases {
        found.push(module.to_owned());
    }
    for other in modules {
        let used =
            by_record.contains(other.name.as_str()) || any_over_body(&other.tree.body, named);
        if other.name != module && used {
            found.push(other.name.clone());
        }
    }
    found.sort_unstable();
    found
}

/// The exception-chain names: Python reads them to print a traceback and never calls them as a hook. A write
/// of one changes no import and no call (#2090). A read of `__traceback__` hands out frames, so only a write is clear.
pub(in crate::survey) const CHAIN_WRITES: [&str; 5] = [
    "__cause__",
    "__context__",
    "__traceback__",
    "__suppress_context__",
    "__notes__",
];

/// The methods that a write or a delete of an attribute can run, or that give the replaced value a finalizer.
const HOOKS: [&str; 6] = [
    "__setattr__",
    "__delattr__",
    "__set__",
    "__delete__",
    "__set_name__",
    "__del__",
];

/// The bases whose methods (`append`, `__iadd__`) a write to `__notes__` can reach.
const LIST_BASES: [&str; 3] = ["list", "UserList", "MutableSequence"];

/// True when a module defines a hook that a write of an exception-chain name can reach: a hook method (also as a
/// string, `type(name, bases, {"__setattr__": f})`), a class with a list base, or a class member that has the name
/// of a chain attribute (a property, a descriptor). One such definition anywhere makes the exemption void.
struct Hooks(bool);

impl<'a> Visitor<'a> for Hooks {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let named = |name: &Identifier| HOOKS.contains(&Identifier::as_str(name));
        match stmt {
            Stmt::FunctionDef(def) if named(&def.name) => self.0 = true,
            Stmt::ClassDef(def) => {
                let bases = def.bases();
                self.0 |= bases.iter().any(|base| {
                    matches!(base, Expr::Name(n) if LIST_BASES.contains(&Name::as_str(&n.id)))
                });
                self.0 |= def.body.iter().any(member_of_chain);
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::StringLiteral(text) if HOOKS.contains(&text.value.to_str())) {
            self.0 = true;
        }
        visitor::walk_expr(self, expr);
    }
}

/// True when a statement of a class body binds a name of the exception chain.
fn member_of_chain(stmt: &Stmt) -> bool {
    let chain = |name: &str| CHAIN_WRITES.contains(&name);
    match stmt {
        Stmt::FunctionDef(def) => chain(Identifier::as_str(&def.name)),
        Stmt::Assign(node) => node
            .targets
            .iter()
            .any(|target| matches!(target, Expr::Name(n) if chain(Name::as_str(&n.id)))),
        Stmt::AnnAssign(node) => {
            matches!(&*node.target, Expr::Name(n) if chain(Name::as_str(&n.id)))
        }
        _ => false,
    }
}

/// True when no scanned module defines a hook that a write of an exception-chain name can reach (#2090).
pub(in crate::survey) fn chain_clear(trees: &[&ModModule]) -> bool {
    let mut hooks = Hooks(false);
    trees.iter().for_each(|tree| hooks.visit_body(&tree.body));
    !hooks.0
}

#[cfg(test)]
#[path = "hazards_bind_tests.rs"]
mod tests;
