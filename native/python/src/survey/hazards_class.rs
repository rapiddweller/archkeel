// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The classes of the scan whose instances cannot be a module object (AD-1540, #2142).
//!
//! A read of a re-exported module name (`x.cp`) is a site when `x` can be the project module that
//! holds the loader (AD-1152). `self` of a method is not that module when its class is proven
//! here: a module-level class, bound once, whose bases are proven classes of the scan or known
//! plain bases, with no metaclass and no `__new__`. A class that has no such proof, and each
//! class that a class without a proof extends, stays unproven: `ModuleType` is the one base that
//! can give an instance that is a module (`sys.modules[name].__class__ = K`).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ModModule, Stmt, StmtClassDef};

use crate::module::Module;

/// The qualified names (`app.models.Foo`) of the proven classes.
pub(in crate::survey) type Classes = HashSet<String>;

/// The bases that give an instance no module: the builtins and the common plain library bases.
const PLAIN_BASES: [&str; 25] = [
    "object",
    "ABC",
    "Generic",
    "Protocol",
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "IntFlag",
    "NamedTuple",
    "TypedDict",
    "BaseModel",
    "Exception",
    "BaseException",
    "ValueError",
    "RuntimeError",
    "TypeError",
    "KeyError",
    "OSError",
    "dict",
    "list",
    "set",
    "tuple",
    "str",
    "int",
];

/// What one class names as its bases.
enum Base {
    Plain,
    Class(String),
    Unknown,
}

struct Def {
    bases: Vec<Base>,
    plain: bool,
}

/// The proven classes of all modules; `imports` holds the import bindings of each module.
pub(in crate::survey) fn instances(
    modules: &[Module],
    imports: &[&HashMap<String, Vec<String>>],
) -> Classes {
    let mut defs: HashMap<String, Def> = HashMap::new();
    let mut taken: HashSet<String> = HashSet::new();
    for (module, imports) in modules.iter().zip(imports) {
        let local: HashSet<&str> = top_level(&module.tree)
            .map(|def| def.name.as_str())
            .collect();
        for def in top_level(&module.tree) {
            let qualified = format!("{}.{}", module.name, def.name.as_str());
            let facts = facts(def, &module.name, &local, imports);
            if defs.insert(qualified.clone(), facts).is_some() {
                // The name is bound twice in the module: neither binding is proven.
                taken.insert(qualified);
            }
        }
        // A class that is no statement of the module body: it and its bases get no proof.
        for def in nested(&module.tree) {
            taken.insert(format!("{}.{}", module.name, def.name.as_str()));
            let bases = facts(def, &module.name, &local, imports).bases;
            taken.extend(bases.into_iter().filter_map(Base::class));
        }
    }
    let mut proven: Classes = defs
        .iter()
        .filter(|(name, def)| def.plain && !taken.contains(*name))
        .map(|(name, _)| name.clone())
        .collect();
    // The greatest fixpoint: a class is proven while its bases are, and its subclasses are.
    loop {
        let before = proven.len();
        let broken: Vec<String> = proven
            .iter()
            .filter(|name| {
                !defs[*name].bases.iter().all(|base| match base {
                    Base::Plain => true,
                    Base::Class(other) => proven.contains(other) || plain_import(other, &defs),
                    Base::Unknown => false,
                })
            })
            .cloned()
            .collect();
        proven.retain(|name| !broken.contains(name));
        let loose: Vec<String> = defs
            .iter()
            .filter(|(name, _)| !proven.contains(*name))
            .flat_map(|(_, def)| &def.bases)
            .filter_map(|base| match base {
                Base::Class(other) if defs.contains_key(other) => Some(other.clone()),
                _ => None,
            })
            .collect();
        proven.retain(|name| !loose.contains(name));
        if proven.len() == before {
            return proven;
        }
    }
}

/// An imported base that no module of the scan defines and that has a plain name (`enum.Enum`).
fn plain_import(origin: &str, defs: &HashMap<String, Def>) -> bool {
    !defs.contains_key(origin)
        && origin
            .rsplit('.')
            .next()
            .is_some_and(|last| PLAIN_BASES.contains(&last))
}

fn top_level(tree: &ModModule) -> impl Iterator<Item = &StmtClassDef> {
    tree.body.iter().filter_map(|stmt| match stmt {
        Stmt::ClassDef(def) => Some(def),
        _ => None,
    })
}

impl Base {
    fn class(self) -> Option<String> {
        match self {
            Base::Class(name) => Some(name),
            _ => None,
        }
    }
}

/// The classes that are no statement of the module body.
fn nested(tree: &ModModule) -> Vec<&StmtClassDef> {
    let mut found = Nested(Vec::new());
    for stmt in &tree.body {
        match stmt {
            Stmt::ClassDef(def) => found.visit_body(&def.body),
            _ => found.visit_stmt(stmt),
        }
    }
    found.0
}

/// The classes below a statement.
struct Nested<'a>(Vec<&'a StmtClassDef>);

impl<'a> Visitor<'a> for Nested<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::ClassDef(def) = stmt {
            self.0.push(def);
        }
        visitor::walk_stmt(self, stmt);
    }
}

fn facts(
    def: &StmtClassDef,
    module: &str,
    local: &HashSet<&str>,
    imports: &HashMap<String, Vec<String>>,
) -> Def {
    let bases: Vec<&Expr> = def
        .arguments
        .iter()
        .flat_map(|arguments| arguments.args.iter())
        .collect();
    // A keyword is a metaclass or another class argument: no proof.
    let keyword = def
        .arguments
        .iter()
        .any(|arguments| !arguments.keywords.is_empty());
    let shaped = def.body.iter().any(|stmt| match stmt {
        Stmt::FunctionDef(node) => node.name.as_str() == "__new__",
        _ => false,
    });
    Def {
        bases: bases
            .into_iter()
            .map(|base| resolve(base, module, local, imports))
            .collect(),
        plain: !keyword && !shaped && def.type_params.is_none() && decorated(def),
    }
}

/// A class decorator can return any value; these are the ones that return the class.
fn decorated(def: &StmtClassDef) -> bool {
    def.decorator_list.iter().all(|decorator| {
        let name = match &decorator.expression {
            Expr::Call(call) => &*call.func,
            other => other,
        };
        let last = match name {
            Expr::Name(node) => node.id.as_str(),
            Expr::Attribute(node) => node.attr.as_str(),
            _ => return false,
        };
        ["dataclass", "final", "total_ordering", "unique"].contains(&last)
    })
}

fn resolve(
    base: &Expr,
    module: &str,
    local: &HashSet<&str>,
    imports: &HashMap<String, Vec<String>>,
) -> Base {
    match base {
        Expr::Subscript(node) => resolve(&node.value, module, local, imports),
        Expr::Attribute(node) if PLAIN_BASES.contains(&node.attr.as_str()) => Base::Plain,
        Expr::Name(node) => {
            let id = node.id.as_str();
            match imports.get(id).map(Vec::as_slice) {
                Some([origin]) => Base::Class(origin.clone()),
                Some(_) => Base::Unknown,
                None if local.contains(id) => Base::Class(format!("{module}.{id}")),
                None if PLAIN_BASES.contains(&id) => Base::Plain,
                None => Base::Unknown,
            }
        }
        _ => Base::Unknown,
    }
}
