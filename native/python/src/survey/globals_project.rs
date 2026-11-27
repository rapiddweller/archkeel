// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of the scan that the proof of a read of `__globals__` reads: the sole functions of
//! each module, the imports, and who a call reaches (AD-530).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};

use super::globals_locals::{stores, Locals};
use super::package_body::anchor;
use crate::module::Module;

/// The builtins that give a scalar or a verdict and never a container of their argument: a dict
/// that reaches one cannot come back as a dict. Any other builtin, such as `list`, `dict`, `iter`
/// or `vars`, is an unknown callee.
pub(super) const PURE_BUILTINS: [&str; 10] = [
    "len",
    "isinstance",
    "issubclass",
    "bool",
    "str",
    "repr",
    "hash",
    "id",
    "callable",
    "print",
];

/// How far a dict follows a call chain through the scan.
pub(super) const DEPTH: usize = 4;

/// What an import statement binds a local name to.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Origin {
    /// `import a.b as c`, `from a import b` where `a.b` is a module.
    Module(String),
    /// `from a import b`: the name `b` of the module `a`.
    Symbol(String, String),
}

/// Who a call reaches.
pub(super) enum Callee<'m> {
    Scan(&'m str, &'m StmtFunctionDef),
    External,
    Unknown,
}

/// The facts of the scan that the proof reads.
pub(super) struct Project<'m> {
    scan: HashSet<&'m str>,
    defs: HashMap<&'m str, HashMap<&'m str, &'m StmtFunctionDef>>,
    imports: HashMap<&'m str, HashMap<String, Vec<Origin>>>,
    /// The names that a module binds at its top level (a builtin name is none of them).
    bound: HashMap<&'m str, HashSet<String>>,
}

/// The sole definitions of a module body, and every name that its top level binds.
fn top_level(body: &[Stmt]) -> (HashMap<&str, &StmtFunctionDef>, HashSet<String>) {
    let mut count: HashMap<&str, usize> = HashMap::new();
    let mut defs: HashMap<&str, &StmtFunctionDef> = HashMap::new();
    let mut bound = HashSet::new();
    for statement in body {
        let name = match statement {
            Stmt::FunctionDef(def) => {
                *count.entry(def.name.as_str()).or_default() += 1;
                defs.insert(def.name.as_str(), def);
                def.name.as_str()
            }
            Stmt::ClassDef(node) => node.name.as_str(),
            _ => continue,
        };
        bound.insert(name.to_owned());
    }
    // A name that is defined twice is no sole definition.
    defs.retain(|def, _| count[def] == 1);
    (defs, bound)
}

impl<'m> Project<'m> {
    pub(super) fn new(modules: &'m [Module]) -> Self {
        let mut project = Project {
            scan: modules.iter().map(|m| m.name.as_str()).collect(),
            defs: HashMap::new(),
            imports: HashMap::new(),
            bound: HashMap::new(),
        };
        for module in modules {
            let name = module.name.as_str();
            let (defs, mut bound) = top_level(&module.tree.body);
            project.defs.insert(name, defs);
            let mut imports = Imports {
                package: owning_package(module),
                found: Vec::new(),
            };
            imports.visit_body(&module.tree.body);
            for (local, origin) in imports.found {
                let origin = match origin {
                    (Some(anchor_name), symbol) => project.origin(module, &anchor_name, &symbol),
                    (None, symbol) => Origin::Module(symbol),
                };
                bound.insert(local.clone());
                let table = project.imports.entry(name).or_default();
                table.entry(local).or_default().push(origin);
            }
            bound.extend(stores(&module.tree.body));
            project.bound.insert(name, bound);
        }
        project
    }

    /// The origin of `from anchor import symbol` as the module `module` writes it.
    pub(super) fn origin(&self, module: &Module, anchor_name: &str, symbol: &str) -> Origin {
        let _ = module;
        let submodule = format!("{anchor_name}.{symbol}");
        if self.scan.contains(submodule.as_str()) {
            Origin::Module(submodule)
        } else {
            Origin::Symbol(anchor_name.to_owned(), symbol.to_owned())
        }
    }

    /// True when a module name is outside the scan: no module of the scan is it or lies below it.
    pub(super) fn external(&self, name: &str) -> bool {
        let below = format!("{name}.");
        !self
            .scan
            .iter()
            .any(|module| *module == name || module.starts_with(&below))
    }

    /// The function that `name` of `module` is: a sole definition, or one import away from it.
    pub(super) fn function(&self, module: &str, name: &str, depth: usize) -> Callee<'m> {
        if depth > DEPTH {
            return Callee::Unknown;
        }
        let owner = self.defs.get_key_value(module);
        if let Some((owner, def)) = owner.and_then(|(owner, defs)| Some((*owner, defs.get(name)?)))
        {
            return Callee::Scan(owner, def);
        }
        let Some(found) = self.imports.get(module).and_then(|table| table.get(name)) else {
            return Callee::Unknown;
        };
        match found.as_slice() {
            [Origin::Symbol(from, symbol)] if self.external(from) => {
                let _ = symbol;
                Callee::External
            }
            [Origin::Symbol(from, symbol)] => match self.scan.get(from.as_str()).copied() {
                Some(owner) => self.function(owner, symbol, depth + 1),
                None => Callee::Unknown,
            },
            [Origin::Module(from)] if self.external(from) => Callee::External,
            _ => Callee::Unknown,
        }
    }

    /// The callee of a call written in `module`, inside a function whose local names are `local`.
    pub(super) fn callee(&self, module: &str, func: &Expr, local: &Locals) -> Callee<'m> {
        match func {
            Expr::Name(name) => self.named(module, name.id.as_str(), local),
            Expr::Attribute(node) => match &*node.value {
                Expr::Name(base) => self.member(module, base.id.as_str(), node.attr.as_str()),
                _ => Callee::Unknown,
            },
            _ => Callee::Unknown,
        }
    }

    /// A callee that is a plain name.
    pub(super) fn named(&self, module: &str, id: &str, local: &Locals) -> Callee<'m> {
        if let Some(value) = local.assigned.get(id) {
            let once = local.stored.get(id).copied() == Some(1);
            return match once {
                true => self.getattr_origin(module, value),
                false => Callee::Unknown,
            };
        }
        if local.names.contains(id) {
            return Callee::Unknown;
        }
        let top = self
            .bound
            .get(module)
            .is_some_and(|names| names.contains(id));
        match (top, PURE_BUILTINS.contains(&id)) {
            (true, _) => self.function(module, id, 0),
            // A builtin that the module does not bind and that returns no container.
            (false, true) => Callee::External,
            (false, false) => Callee::Unknown,
        }
    }

    /// `mod.name(...)`: a function of a module of the scan, or any member of an external module.
    pub(super) fn member(&self, module: &str, base: &str, attr: &str) -> Callee<'m> {
        let found = self.imports.get(module).and_then(|table| table.get(base));
        match found.map(Vec::as_slice) {
            Some([Origin::Module(from) | Origin::Symbol(from, _)]) if self.external(from) => {
                Callee::External
            }
            Some([Origin::Module(from)]) => match self.scan.get(from.as_str()).copied() {
                Some(owner) => self.function(owner, attr, 0),
                None => Callee::Unknown,
            },
            _ => Callee::Unknown,
        }
    }

    /// A local name that the function writes once from `getattr(<external module>, "x", ...)`: a
    /// member of a module outside the scan.
    pub(super) fn getattr_origin(&self, module: &str, value: &Expr) -> Callee<'m> {
        let Expr::Call(call) = value else {
            return Callee::Unknown;
        };
        let literal = matches!(call.arguments.args.get(1), Some(Expr::StringLiteral(_)));
        let named = matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "getattr");
        match call.arguments.args.first() {
            Some(Expr::Name(base)) if named && literal => {
                let found = self
                    .imports
                    .get(module)
                    .and_then(|t| t.get(base.id.as_str()));
                match found.map(Vec::as_slice) {
                    Some([Origin::Module(from) | Origin::Symbol(from, _)])
                        if self.external(from) =>
                    {
                        Callee::External
                    }
                    _ => Callee::Unknown,
                }
            }
            _ => Callee::Unknown,
        }
    }
}

/// The imports of a module at any depth: `(anchor, name)` of each name that they bind.
struct Imports<'p> {
    /// The package that a relative import is relative to.
    package: &'p str,
    found: Vec<(String, (Option<String>, String))>,
}

/// The package that a module belongs to: the module itself for an `__init__`.
fn owning_package(module: &Module) -> &str {
    if module.is_init() {
        return &module.name;
    }
    module
        .name
        .rsplit_once('.')
        .map_or("", |(package, _)| package)
}

impl Imports<'_> {
    /// `import a.b as c` binds `c` to `a.b`; `import a.b` binds `a`.
    fn plain(&mut self, node: &ruff_python_ast::StmtImport) {
        for alias in &node.names {
            let name = alias.name.as_str();
            let first = name.split('.').next().unwrap_or(name);
            let (local, target) = match &alias.asname {
                Some(asname) => (asname.to_string(), name),
                None => (first.to_owned(), first),
            };
            self.found.push((local, (None, target.to_owned())));
        }
    }
}

impl<'a> Visitor<'a> for Imports<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => self.plain(node),
            Stmt::ImportFrom(node) => {
                let module = anchor(node, self.package).unwrap_or_default();
                for alias in &node.names {
                    let name = alias.name.as_str();
                    let local = alias.asname.as_ref().map_or(name, |a| a.as_str());
                    self.found
                        .push((local.to_owned(), (Some(module.clone()), name.to_owned())));
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }
}
