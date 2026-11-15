// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The lazy import module (AD-560): a module-level `__getattr__` that imports the module of a
//! table by `import_module`, as `pydantic/__init__.py` does.
//!
//! The table (`lazy_table.rs`) and the function (`lazy_flow.rs`) bound each argument of each call
//! to a finite set of strings. The targets of a call are all candidates of the product of its
//! arguments, each resolved with `importlib.util.resolve_name`. A candidate that is a module of
//! the project, or a module outside the project, is an import record; a candidate that no regular
//! package of the project holds is no import. The sites that the proof covers are not gaps: the
//! calls, their import statement, the `globals()` writes of the keys and the `__spec__.parent`
//! reads of the table. Any other site of the module stays a gap.

use std::collections::{BTreeSet, HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::binders::{first_part, Binders};
use super::hazards;
use super::literal;
use crate::module::Module;
use flow::{Call, Callee};

#[path = "lazy_binds.rs"]
mod binds;
#[path = "lazy_flow.rs"]
mod flow;
#[path = "lazy_table.rs"]
mod table;
#[path = "lazy_writes.rs"]
mod writes;

#[cfg(test)]
#[path = "lazy_table_tests.rs"]
mod tests;

/// What the proof of one module covers: the ranges of the sites that are no gap and the import
/// targets of the calls.
#[derive(Default)]
pub(super) struct Lazy {
    pub exempt: Vec<TextRange>,
    pub targets: Vec<(TextRange, String)>,
}

/// The proof of each module, in the order of `modules`.
pub(super) fn find(modules: &[Module], binders: &[Binders], namespace: &str) -> Vec<Lazy> {
    let known: HashMap<&str, usize> = modules
        .iter()
        .enumerate()
        .map(|(index, module)| (module.name.as_str(), index))
        .collect();
    let world = World {
        modules,
        binders,
        known,
        project: first_part(namespace),
    };
    (0..modules.len())
        .map(|index| world.of(index).unwrap_or_default())
        .collect()
}

struct World<'a> {
    modules: &'a [Module],
    binders: &'a [Binders],
    known: HashMap<&'a str, usize>,
    project: &'a str,
}

impl World<'_> {
    fn of(&self, index: usize) -> Option<Lazy> {
        let module = &self.modules[index];
        let count = |name: &str| self.count(index, name);
        let function = getattr(module, &count)?;
        let used = names(function);
        let table = table::find(module, &count, &used)?;
        let elsewhere = self.modules.iter().enumerate();
        if elsewhere
            .into_iter()
            .any(|(other, item)| other != index && item.text().contains(&table.name))
        {
            return None;
        }
        let callee = callee(module, &count);
        let flow = flow::analyze(function, &table, callee.0);
        let mut found = Lazy {
            exempt: table.exempt.clone(),
            targets: Vec::new(),
        };
        found.exempt.extend(flow.exempt);
        let mut by_name = false;
        for call in &flow.calls {
            let Some(candidates) = self.candidates(call) else {
                continue;
            };
            by_name |= call.by_name;
            found.exempt.push(call.callee);
            let others = candidates.into_iter().filter(|name| name != &module.name);
            for target in others.filter(|name| self.imports(name)) {
                found.targets.push((call.range, target));
            }
        }
        if by_name {
            found.exempt.extend(callee.1);
        }
        Some(found)
    }

    /// How often a binder binds the name in the module. A star import binds a name only when the
    /// module that it names has a literal `__all__` that lists the name; any other star import
    /// makes the count unknown.
    fn count(&self, index: usize, name: &str) -> Option<usize> {
        let own = &self.binders[index];
        if let Some(count) = own.count(name) {
            return Some(count);
        }
        let count = own.count_beside_stars(name)?;
        for (level, module) in &own.stars {
            let dots = ".".repeat(*level as usize);
            let target = match *level {
                0 => module.clone(),
                _ => resolve(
                    &format!("{dots}{module}"),
                    &table::parent(&self.modules[index]),
                )?,
            };
            let other = &self.binders[*self.known.get(target.as_str())?];
            if !other.all_literal || other.all_exports.contains(name) {
                return None;
            }
        }
        Some(count)
    }

    /// The modules that a call can import, or `None` when a candidate is no module name or is a
    /// door (`hazards::hazard`).
    fn candidates(&self, call: &Call) -> Option<BTreeSet<String>> {
        let none = [String::new()];
        let packages: &[String] = call.packages.as_deref().unwrap_or(&none);
        let mut out = BTreeSet::new();
        for name in &call.names {
            for package in packages {
                let relative = name.starts_with('.');
                let given = call.packages.is_some() && !package.is_empty();
                let resolved = match (relative, given) {
                    (false, _) => name.clone(),
                    (true, true) => match resolve(name, package) {
                        Some(found) => found,
                        None => continue,
                    },
                    (true, false) => continue,
                };
                out.insert(resolved);
            }
        }
        let named = |name: &String| {
            name.split('.').all(archkeel_facts::identity::is_identifier)
                && hazards::hazard(name).is_none()
        };
        out.iter().all(named).then_some(out)
    }

    /// True when the candidate is an import: outside the project, a module of it, or a name that
    /// the survey cannot show to be absent from a regular package.
    fn imports(&self, target: &str) -> bool {
        if first_part(target) != self.project || self.known.contains_key(target) {
            return true;
        }
        let mut prefix = String::new();
        for part in target.split('.') {
            let parent = prefix.clone();
            if !prefix.is_empty() {
                prefix.push('.');
            }
            prefix.push_str(part);
            if !self.known.contains_key(prefix.as_str()) {
                // The first missing part: its package must be a module that never names `__path__`.
                let package = self.known.get(parent.as_str());
                return package.is_none_or(|at| self.modules[*at].text().contains("__path__"));
            }
        }
        true
    }
}

/// `importlib.util.resolve_name` for a relative name and a package.
fn resolve(name: &str, package: &str) -> Option<String> {
    let level = name.chars().take_while(|char| *char == '.').count();
    let rest = &name[level..];
    if package.matches('.').count() + 1 < level {
        return None;
    }
    let base = package.rsplitn(level, '.').last()?;
    Some(if rest.is_empty() {
        base.to_owned()
    } else {
        format!("{base}.{rest}")
    })
}

/// The module-level `def __getattr__(name)`, bound once, plain.
fn getattr<'a>(
    module: &'a Module,
    count: &dyn Fn(&str) -> Option<usize>,
) -> Option<&'a StmtFunctionDef> {
    if count("__getattr__") != Some(1) {
        return None;
    }
    module.tree.body.iter().find_map(|stmt| match stmt {
        Stmt::FunctionDef(node)
            if node.name.as_str() == "__getattr__"
                && !node.is_async
                && node.decorator_list.is_empty()
                && node.type_params.is_none() =>
        {
            Some(node)
        }
        _ => None,
    })
}

/// The names that the body of the function reads.
fn names(function: &StmtFunctionDef) -> HashSet<String> {
    struct Names(HashSet<String>);
    impl<'a> Visitor<'a> for Names {
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::Name(node) = expr {
                self.0.insert(node.id.to_string());
            }
            visitor::walk_expr(self, expr);
        }
    }
    let mut walk = Names(HashSet::new());
    walk.visit_body(&function.body);
    walk.0
}

/// The ranges of the `from importlib import import_module` statements.
struct Imports(Vec<TextRange>);

impl<'a> Visitor<'a> for Imports {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::ImportFrom(node) = stmt {
            let named = matches!(node.names.as_slice(), [alias]
                if alias.name.as_str() == "import_module" && alias.asname.is_none());
            let module = node.module.as_ref().map(|name| name.as_str());
            if named && module == Some("importlib") && node.level == 0 {
                self.0.push(stmt.range());
            }
        }
        visitor::walk_stmt(self, stmt);
    }
}

/// The proof of the import function, and the ranges of the import statements that bind it.
fn callee(module: &Module, count: &dyn Fn(&str) -> Option<usize>) -> (Callee, Vec<TextRange>) {
    let mut walk = Imports(Vec::new());
    walk.visit_body(&module.tree.body);
    let plain = literal::plain_importlib(&module.tree);
    let callee = Callee {
        from_import: !walk.0.is_empty() && count("import_module") == Some(walk.0.len()),
        plain: plain > 0 && count("importlib") == Some(plain),
    };
    (callee, walk.0)
}
