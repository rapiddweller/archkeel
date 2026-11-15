// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A read of the globals of a function that cannot import a module (AD-530).
//!
//! `f.__globals__` and `getattr(f, "__globals__")` give the namespace of a function. The dict
//! reaches `__builtins__` and so any import, so the survey treats a read as a dynamic import
//! (`hazards.rs`). A read is inert when the dict is used only in forms that name no door:
//!
//! - `d.get("key")`, `d["key"]` and `"key" in d` with a literal key that is no door string;
//! - an argument of a call whose callee is outside the scan, or a function of the scan whose
//!   parameter is used in these forms only (bounded, a cycle is not inert).
//!
//! The dict may be the value of one local name that the function writes once. Any other use is
//! not inert: a return, a store, a copy, `.items()`, `**d`, an iteration, a computed key, a
//! callee that the survey cannot name, or a name that the function writes again.
//!
//! Release 4.0.1 counts no edge for a read of `__globals__`. Evaluating a string annotation in the
//! dict is what `typing.get_type_hints(f)` does in library code, and the survey does not read
//! library code (AD-450).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, Expr, ExprContext, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::package_body::anchor;
use crate::module::Module;

/// The strings that name a door: a key with one of them is never read as data.
const DOOR_KEYS: [&str; 7] = [
    "__import__",
    "__builtins__",
    "import_module",
    "__subclasses__",
    "__globals__",
    "__self__",
    "__loader__",
];

/// The names that a call may not receive the dict as an argument of (each is a door itself).
const CODE_RUNNERS: [&str; 7] = [
    "exec",
    "eval",
    "compile",
    "vars",
    "globals",
    "locals",
    "__import__",
];

/// How far a dict follows a call chain through the scan.
const DEPTH: usize = 4;

/// What an import statement binds a local name to.
#[derive(Clone, Debug, PartialEq, Eq)]
enum Origin {
    /// `import a.b as c`, `from a import b` where `a.b` is a module.
    Module(String),
    /// `from a import b`: the name `b` of the module `a`.
    Symbol(String, String),
}

/// Who a call reaches.
enum Callee<'m> {
    Scan(&'m str, &'m StmtFunctionDef),
    External,
    Unknown,
}

/// The facts of the scan that the proof reads.
struct Project<'m> {
    scan: HashSet<&'m str>,
    defs: HashMap<&'m str, HashMap<&'m str, &'m StmtFunctionDef>>,
    imports: HashMap<&'m str, HashMap<String, Vec<Origin>>>,
    /// The names that a module binds at its top level (a builtin name is none of them).
    bound: HashMap<&'m str, HashSet<String>>,
}

/// The ranges of the inert sources of each module: the string `"__globals__"` of a `getattr`, or
/// the attribute `__globals__` (AD-530).
pub(super) fn inert_reads(modules: &[Module]) -> Vec<HashSet<TextRange>> {
    let project = Project::new(modules);
    modules
        .iter()
        .map(|module| {
            let mut found = HashSet::new();
            let mut walk = Functions {
                project: &project,
                module: module.name.as_str(),
                found: &mut found,
            };
            walk.visit_body(&module.tree.body);
            found
        })
        .collect()
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
    fn new(modules: &'m [Module]) -> Self {
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
    fn origin(&self, module: &Module, anchor_name: &str, symbol: &str) -> Origin {
        let _ = module;
        let submodule = format!("{anchor_name}.{symbol}");
        if self.scan.contains(submodule.as_str()) {
            Origin::Module(submodule)
        } else {
            Origin::Symbol(anchor_name.to_owned(), symbol.to_owned())
        }
    }

    /// True when a module name is outside the scan: no module of the scan is it or lies below it.
    fn external(&self, name: &str) -> bool {
        let below = format!("{name}.");
        !self
            .scan
            .iter()
            .any(|module| *module == name || module.starts_with(&below))
    }

    /// The function that `name` of `module` is: a sole definition, or one import away from it.
    fn function(&self, module: &str, name: &str, depth: usize) -> Callee<'m> {
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
    fn callee(&self, module: &str, func: &Expr, local: &Locals) -> Callee<'m> {
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
    fn named(&self, module: &str, id: &str, local: &Locals) -> Callee<'m> {
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
        match (top, CODE_RUNNERS.contains(&id)) {
            (true, _) => self.function(module, id, 0),
            (false, true) => Callee::Unknown,
            // A builtin that the module does not bind.
            (false, false) => Callee::External,
        }
    }

    /// `mod.name(...)`: a function of a module of the scan, or any member of an external module.
    fn member(&self, module: &str, base: &str, attr: &str) -> Callee<'m> {
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
    fn getattr_origin(&self, module: &str, value: &Expr) -> Callee<'m> {
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

    /// True when the parameter `param` of the scan function `def` is used in inert forms only.
    fn parameter_inert(
        &self,
        owner: &str,
        def: &StmtFunctionDef,
        param: &str,
        path: &mut Vec<(String, String, String)>,
    ) -> bool {
        let key = (owner.to_owned(), def.name.to_string(), param.to_owned());
        if path.len() >= DEPTH || path.contains(&key) {
            return false;
        }
        let local = Locals::of(def);
        if local.written(param) || local.declared.contains(param) {
            return false;
        }
        path.push(key);
        let inert = self.uses_inert(owner, &def.body, Target::Name(param), &local, path);
        path.pop();
        inert
    }

    /// True when each use of the target in `body` is inert.
    fn uses_inert(
        &self,
        module: &str,
        body: &[Stmt],
        target: Target,
        local: &Locals,
        path: &mut Vec<(String, String, String)>,
    ) -> bool {
        let mut uses = Uses {
            project: self,
            module,
            target,
            local,
            path,
            seen: HashSet::new(),
            allowed: HashSet::new(),
        };
        uses.visit_body(body);
        !uses.seen.is_empty() && uses.seen == uses.allowed
    }
}

/// The names of the one dict that a proof follows.
#[derive(Clone, Copy)]
enum Target<'t> {
    /// Each load of a name.
    Name(&'t str),
    /// One source expression, by its range.
    Source(TextRange),
}

impl Target<'_> {
    fn is(&self, expr: &Expr) -> bool {
        match self {
            Target::Name(name) => {
                matches!(expr, Expr::Name(node) if node.id.as_str() == *name && node.ctx == ExprContext::Load)
            }
            Target::Source(range) => expr.range() == *range,
        }
    }
}

/// The names that a function binds: its parameters, its assignments, and what it declares.
#[derive(Default)]
struct Locals<'f> {
    names: HashSet<String>,
    declared: HashSet<String>,
    /// The value of each name that the function writes exactly once by `name = value`.
    assigned: HashMap<String, &'f Expr>,
    stored: HashMap<String, usize>,
}

impl<'f> Locals<'f> {
    fn of(def: &'f StmtFunctionDef) -> Self {
        let mut found = Locals::default();
        let parameters = &def.parameters;
        let all = parameters
            .posonlyargs
            .iter()
            .chain(&parameters.args)
            .chain(&parameters.kwonlyargs)
            .map(|p| &p.parameter)
            .chain(parameters.vararg.as_deref())
            .chain(parameters.kwarg.as_deref());
        for parameter in all {
            found.names.insert(parameter.name.to_string());
            *found.stored.entry(parameter.name.to_string()).or_default() += 1;
        }
        found.visit_body(&def.body);
        found
    }

    /// True when the function writes `name` more than once (a parameter counts as one write).
    fn written(&self, name: &str) -> bool {
        self.stored.get(name).copied().unwrap_or(0) > 1
    }
}

impl<'a> Visitor<'a> for Locals<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Global(node) => self
                .declared
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::Nonlocal(node) => self
                .declared
                .extend(node.names.iter().map(ToString::to_string)),
            Stmt::FunctionDef(node) => {
                self.names.insert(node.name.to_string());
                *self.stored.entry(node.name.to_string()).or_default() += 2;
                return;
            }
            Stmt::ClassDef(node) => {
                self.names.insert(node.name.to_string());
                *self.stored.entry(node.name.to_string()).or_default() += 2;
                return;
            }
            Stmt::Assign(node) => {
                if let ([Expr::Name(name)], value) = (node.targets.as_slice(), &*node.value) {
                    self.assigned.insert(name.id.to_string(), value);
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if node.ctx != ExprContext::Load {
                self.names.insert(node.id.to_string());
                *self.stored.entry(node.id.to_string()).or_default() += 1;
            }
        }
        visitor::walk_expr(self, expr);
    }
}

/// The names that the statements of a module body store at any depth.
fn stores(body: &[Stmt]) -> HashSet<String> {
    let mut walk = Locals::default();
    walk.visit_body(body);
    walk.names
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

/// The uses of one target in the body of one function.
struct Uses<'p, 'm, 'f> {
    project: &'p Project<'m>,
    module: &'p str,
    target: Target<'p>,
    local: &'p Locals<'f>,
    path: &'p mut Vec<(String, String, String)>,
    /// The ranges of each load of the target, and of each load in an inert form.
    seen: HashSet<TextRange>,
    allowed: HashSet<TextRange>,
}

impl Uses<'_, '_, '_> {
    /// True for a string literal that is no door.
    fn plain_key(expr: &Expr) -> bool {
        matches!(expr, Expr::StringLiteral(text) if !DOOR_KEYS.contains(&text.value.to_str()))
    }

    /// The loads of the target that the expression `expr` uses in an inert form.
    fn consume(&mut self, expr: &Expr) {
        match expr {
            Expr::Call(call) => {
                self.lookup(call);
                self.arguments(call);
            }
            Expr::Subscript(node)
                if node.ctx == ExprContext::Load
                    && self.target.is(&node.value)
                    && Self::plain_key(&node.slice) =>
            {
                self.allowed.insert(node.value.range());
            }
            Expr::Compare(node) => self.membership(node),
            _ => {}
        }
    }

    /// `d.get("key")` with one literal key that is no door.
    fn lookup(&mut self, call: &ruff_python_ast::ExprCall) {
        let args = &call.arguments;
        let Expr::Attribute(method) = &*call.func else {
            return;
        };
        let get = method.attr.as_str() == "get"
            && self.target.is(&method.value)
            && matches!(args.args.first(), Some(key) if Self::plain_key(key))
            && args.args.len() <= 2
            && args.keywords.is_empty();
        if get {
            self.allowed.insert(method.value.range());
        }
    }

    /// `"key" in d` with a literal key that is no door.
    fn membership(&mut self, node: &ruff_python_ast::ExprCompare) {
        let ([CmpOp::In | CmpOp::NotIn], [left, right]) = (&*node.ops, &*node.operands) else {
            return;
        };
        if Self::plain_key(left) && self.target.is(right) {
            self.allowed.insert(right.range());
        }
    }

    /// Each argument of a call that is the target: inert when the callee is.
    fn arguments(&mut self, call: &ruff_python_ast::ExprCall) {
        let callee = self.project.callee(self.module, &call.func, self.local);
        for (index, arg) in call.arguments.args.iter().enumerate() {
            if self.target.is(arg) && self.passes(&callee, Some(index), None) {
                self.allowed.insert(arg.range());
            }
        }
        for keyword in &call.arguments.keywords {
            let name = keyword.arg.as_ref().map(|n| n.as_str());
            if name.is_some() && self.target.is(&keyword.value) && self.passes(&callee, None, name)
            {
                self.allowed.insert(keyword.value.range());
            }
        }
    }

    fn passes(&mut self, callee: &Callee, index: Option<usize>, name: Option<&str>) -> bool {
        match callee {
            Callee::External => true,
            Callee::Unknown => false,
            Callee::Scan(owner, def) => {
                let parameters = &def.parameters;
                let positional: Vec<&str> = parameters
                    .posonlyargs
                    .iter()
                    .chain(&parameters.args)
                    .map(|p| p.parameter.name.as_str())
                    .collect();
                let keyword = parameters
                    .kwonlyargs
                    .iter()
                    .map(|p| p.parameter.name.as_str());
                let param = match (index, name) {
                    (Some(at), _) => positional.get(at).copied(),
                    (None, Some(given)) => positional
                        .iter()
                        .copied()
                        .chain(keyword)
                        .find(|candidate| *candidate == given),
                    (None, None) => None,
                };
                param
                    .is_some_and(|param| self.project.parameter_inert(owner, def, param, self.path))
            }
        }
    }
}

impl<'a> Visitor<'a> for Uses<'_, '_, '_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if self.target.is(expr) {
            self.seen.insert(expr.range());
        }
        self.consume(expr);
        visitor::walk_expr(self, expr);
    }
}

/// The functions of a module: a source inside one is inert or not by its own uses.
struct Functions<'p, 'm> {
    project: &'p Project<'m>,
    module: &'p str,
    found: &'p mut HashSet<TextRange>,
}

/// The marker range of a source of globals: the string of `getattr(f, "__globals__")`, or the
/// attribute `__globals__`.
fn source(expr: &Expr) -> Option<TextRange> {
    match expr {
        Expr::Call(call) => {
            let named = matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "getattr");
            let args = &call.arguments.args;
            match args.get(1) {
                Some(Expr::StringLiteral(text))
                    if named
                        && (2..=3).contains(&args.len())
                        && call.arguments.keywords.is_empty()
                        && text.value.to_str() == "__globals__" =>
                {
                    Some(text.range())
                }
                _ => None,
            }
        }
        Expr::Attribute(node)
            if node.attr.as_str() == "__globals__" && node.ctx == ExprContext::Load =>
        {
            Some(node.range())
        }
        _ => None,
    }
}

impl<'a> Visitor<'a> for Functions<'_, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::FunctionDef(def) = stmt {
            self.function(def);
        }
        visitor::walk_stmt(self, stmt);
    }
}

impl Functions<'_, '_> {
    /// Each source of the function, with the expression that holds it.
    fn function(&mut self, def: &StmtFunctionDef) {
        let local = Locals::of(def);
        let mut sources = Sources::default();
        sources.visit_body(&def.body);
        for (holder, marker) in sources.found {
            let target = Target::Source(holder.range());
            let mut path = Vec::new();
            let direct = self
                .project
                .uses_inert(self.module, &def.body, target, &local, &mut path);
            if direct {
                self.found.insert(marker);
            }
        }
        // A source that one local name holds: the name has no other write, and each load is inert.
        let mut assigns = Assigned::default();
        assigns.visit_body(&def.body);
        for (name, holder, marker) in assigns.found {
            let single = local.stored.get(name.as_str()).copied() == Some(1);
            if !single || local.declared.contains(&name) {
                continue;
            }
            let mut path = Vec::new();
            let target = Target::Name(&name);
            if self
                .project
                .uses_inert(self.module, &def.body, target, &local, &mut path)
            {
                let _ = holder;
                self.found.insert(marker);
            }
        }
    }
}

/// The sources in a function body, with the expression that holds each.
#[derive(Default)]
struct Sources<'a> {
    found: Vec<(&'a Expr, TextRange)>,
}

impl<'a> Visitor<'a> for Sources<'a> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Some(marker) = source(expr) {
            self.found.push((expr, marker));
        }
        visitor::walk_expr(self, expr);
    }
}

/// The statements `name = <source>` of a function body.
#[derive(Default)]
struct Assigned<'a> {
    found: Vec<(String, &'a Expr, TextRange)>,
}

impl<'a> Visitor<'a> for Assigned<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::Assign(node) = stmt {
            if let ([Expr::Name(name)], Some(marker)) =
                (node.targets.as_slice(), source(&node.value))
            {
                self.found.push((name.id.to_string(), &node.value, marker));
            }
        }
        visitor::walk_stmt(self, stmt);
    }
}

/// The local names of a function for the door check of `hazards.rs`: each parameter and each
/// written name, less a name that a `global` or `nonlocal` line declares.
pub(super) fn local_names(def: &StmtFunctionDef) -> HashSet<String> {
    let found = Locals::of(def);
    found
        .names
        .into_iter()
        .filter(|name| !found.declared.contains(name))
        .collect()
}
