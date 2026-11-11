// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The static imports of the selected modules (`imports.ImportCollector`, `collect_imports`).
//!
//! An import inside a function or a class is a record too; only a statement outside of each
//! definition is a module-level import. The body of `if TYPE_CHECKING:` (a name or an attribute)
//! marks its imports `under_type_checking`.

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::{Expr, Stmt, StmtImportFrom};

use super::binders::{first_part, import_bindings, Binders};
use super::module::{EvidenceMap, Module};
use crate::names::package_for;

/// The import records of all modules, sorted by id. `binders` has one entry for each module.
pub fn collect(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
) -> Vec<Record<ImportFact>> {
    let names: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    let bindings: HashMap<&str, HashSet<String>> = modules
        .iter()
        .filter(|module| module.is_init())
        .map(|module| (module.name.as_str(), shadowing_names(module)))
        .collect();
    let mut records = Vec::new();
    for (module, binders) in modules.iter().zip(binders) {
        let mut collector = Collector {
            module,
            binders,
            unique: binders.unique(),
            names: &names,
            bindings: &bindings,
            namespace,
            evidence: &mut *evidence,
            records: &mut records,
        };
        collector.body(&module.tree.body, true, false);
    }
    records.sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
    records
}

/// `_owning_package`: the package that a relative import of the module starts from.
fn owning_package(module: &Module) -> &str {
    if module.is_init() {
        return &module.name;
    }
    module
        .name
        .rsplit_once('.')
        .map_or("", |(package, _)| package)
}

/// `importlib.util.resolve_name` for a name of `level` dots and then `name`. Each failure of it
/// on CPython 3.11 to 3.14 is an `ImportError`.
fn resolve(level: u32, name: &str, package: &str) -> Option<String> {
    if package.is_empty() {
        return None;
    }
    let mut base = package;
    for _ in 1..level {
        base = &base[..base.rfind('.')?];
    }
    Some(if name.is_empty() {
        base.to_owned()
    } else {
        format!("{base}.{name}")
    })
}

/// The module that `from ... import` names, or `None` when `resolve_name` fails.
fn anchor(node: &StmtImportFrom, package: &str) -> Option<String> {
    let name = node.module.as_ref().map_or("", |module| module.as_str());
    if node.level == 0 {
        return Some(name.to_owned());
    }
    resolve(node.level, name, package)
}

/// `_shadowed_names`: the names that the top-level statements of a package body bind ahead of a
/// submodule of the same name (AD-53). `__getattr__` or a star import empties the set.
fn shadowing_names(module: &Module) -> HashSet<String> {
    let mut names = HashSet::new();
    for statement in &module.tree.body {
        match statement {
            Stmt::FunctionDef(node) if node.name.as_str() == "__getattr__" => {
                return HashSet::new()
            }
            Stmt::ClassDef(node) if node.name.as_str() == "__getattr__" => return HashSet::new(),
            Stmt::FunctionDef(node) => drop(names.insert(node.name.id.to_string())),
            Stmt::ClassDef(node) => drop(names.insert(node.name.id.to_string())),
            Stmt::Assign(node) => names.extend(node.targets.iter().filter_map(name_of)),
            Stmt::AnnAssign(node) => names.extend(name_of(&node.target)),
            Stmt::Import(_) => names.extend(import_bindings(statement)),
            Stmt::ImportFrom(node) => {
                if node.names.iter().any(|alias| alias.name.as_str() == "*") {
                    return HashSet::new();
                }
                names.extend(from_bindings(node, &module.name));
            }
            _ => {}
        }
    }
    names
}

/// The names of `from ... import` in the package body of `package`, without the plain
/// `from . import name` that binds the submodule itself (`_binds_identical_submodule`).
fn from_bindings<'n>(node: &'n StmtImportFrom, package: &str) -> impl Iterator<Item = String> + 'n {
    let own = anchor(node, package).as_deref() == Some(package);
    node.names
        .iter()
        .filter(move |alias| !(own && alias.asname.is_none()))
        .map(|alias| alias.asname.as_ref().unwrap_or(&alias.name).id.to_string())
}

fn name_of(target: &Expr) -> Option<String> {
    match target {
        Expr::Name(node) => Some(node.id.to_string()),
        _ => None,
    }
}

/// `_is_type_checking_test`: the name `TYPE_CHECKING` or any attribute of that name.
fn is_type_checking(test: &Expr) -> bool {
    match test {
        Expr::Name(node) => node.id.as_str() == "TYPE_CHECKING",
        Expr::Attribute(node) => node.attr.as_str() == "TYPE_CHECKING",
        _ => false,
    }
}

struct Collector<'m, 'e> {
    module: &'m Module,
    binders: &'m Binders,
    unique: HashSet<String>,
    names: &'m HashSet<&'m str>,
    bindings: &'m HashMap<&'m str, HashSet<String>>,
    namespace: &'m str,
    evidence: &'e mut EvidenceMap,
    records: &'e mut Vec<Record<ImportFact>>,
}

/// What one import binding is: the target, the symbol, the binding and the relative level.
struct Binding<'t> {
    target: &'t str,
    symbol: Option<&'t str>,
    binding: &'t str,
    level: u32,
}

impl Collector<'_, '_> {
    /// The statements of one body. An import is only a statement, so the walk reads statements.
    fn body(&mut self, body: &[Stmt], module_level: bool, guarded: bool) {
        for statement in body {
            self.statement(statement, module_level, guarded);
        }
    }

    fn statement(&mut self, statement: &Stmt, level: bool, guarded: bool) {
        match statement {
            Stmt::Import(_) | Stmt::ImportFrom(_) => self.import(statement, level, guarded),
            Stmt::If(node) => {
                self.body(&node.body, level, guarded || is_type_checking(&node.test));
                for clause in &node.elif_else_clauses {
                    let test = clause.test.as_ref().is_some_and(is_type_checking);
                    self.body(&clause.body, level, guarded || test);
                }
            }
            Stmt::FunctionDef(node) => self.body(&node.body, false, guarded),
            Stmt::ClassDef(node) => self.body(&node.body, false, guarded),
            Stmt::For(node) => {
                self.body(&node.body, level, guarded);
                self.body(&node.orelse, level, guarded);
            }
            Stmt::While(node) => {
                self.body(&node.body, level, guarded);
                self.body(&node.orelse, level, guarded);
            }
            Stmt::With(node) => self.body(&node.body, level, guarded),
            Stmt::Try(node) => {
                self.body(&node.body, level, guarded);
                for handler in &node.handlers {
                    let ruff_python_ast::ExceptHandler::ExceptHandler(handler) = handler;
                    self.body(&handler.body, level, guarded);
                }
                self.body(&node.orelse, level, guarded);
                self.body(&node.finalbody, level, guarded);
            }
            Stmt::Match(node) => {
                for case in &node.cases {
                    self.body(&case.body, level, guarded);
                }
            }
            _ => {}
        }
    }

    fn import(&mut self, statement: &Stmt, level: bool, guarded: bool) {
        let place = (statement, level, guarded);
        match statement {
            Stmt::Import(node) => {
                for alias in &node.names {
                    let name = alias.name.as_str();
                    let binding = alias
                        .asname
                        .as_ref()
                        .map_or(first_part(name), |a| a.as_str());
                    let found = Binding {
                        target: name,
                        symbol: None,
                        binding,
                        level: 0,
                    };
                    self.record(place, &found);
                }
            }
            Stmt::ImportFrom(node) => self.import_from(node, place),
            _ => {}
        }
    }

    fn import_from(&mut self, node: &StmtImportFrom, place: (&Stmt, bool, bool)) {
        let anchor = anchor(node, owning_package(self.module)).unwrap_or_else(|| {
            let module = node.module.as_ref().map_or("", |module| module.as_str());
            format!(
                "<unresolved:{}{module}:ImportError>",
                ".".repeat(node.level as usize)
            )
        });
        for alias in &node.names {
            let name = alias.name.as_str();
            if name == "*" {
                let found = Binding {
                    target: &anchor,
                    symbol: Some("*"),
                    binding: "*",
                    level: node.level,
                };
                self.record(place, &found);
                continue;
            }
            let submodule = if anchor.is_empty() {
                name.to_owned()
            } else {
                format!("{anchor}.{name}")
            };
            let shadowed = self
                .bindings
                .get(anchor.as_str())
                .is_some_and(|names| names.contains(name));
            let local = !shadowed && self.names.contains(submodule.as_str());
            let found = Binding {
                target: if local { &submodule } else { &anchor },
                symbol: if local { None } else { Some(name) },
                binding: alias.asname.as_ref().map_or(name, |a| a.as_str()),
                level: node.level,
            };
            self.record(place, &found);
        }
    }

    fn record(&mut self, (statement, module_level, guarded): (&Stmt, bool, bool), b: &Binding) {
        let module = self.module;
        let evidence_id = module.evidence(self.evidence, statement);
        let (line, _, column) = module.location(statement);
        let in_scope = b.target == self.namespace
            || b.target
                .strip_prefix(self.namespace)
                .is_some_and(|rest| rest.starts_with('.'));
        let target_package = if in_scope {
            package_for(b.target)
        } else {
            first_part(b.target).to_owned()
        };
        let symbol = b.symbol.map_or(Part::Nothing, Part::Text);
        let parts = [
            Part::Text(&module.rel),
            Part::Number(line),
            Part::Number(column),
            Part::Text(b.target),
            symbol,
            Part::Text(b.binding),
        ];
        let init = module.is_init();
        let exported = self.binders.all_exports.contains(b.binding);
        let literal_unique = self.binders.all_literal && self.unique.contains(b.binding);
        let data = ImportData {
            source_module: ModuleName::new(module.name.as_str()),
            source_package: PackageName::new(module.package.as_str()),
            target_module: ModuleName::new(b.target),
            target_package: PackageName::new(target_package),
            symbol: b.symbol.map(str::to_owned),
            binding: Some(b.binding.to_owned()),
            symbols_known: true,
            specifier: None,
            type_only: None,
            relative_level: i64::from(b.level),
            under_type_checking: guarded,
            reexport: init || (exported && literal_unique),
            module_level_import: module_level,
            ordinary_module: Some(!init),
            reexport_candidate: Some(
                !init && module_level && exported && b.symbol.is_some() && !literal_unique,
            ),
            ..ImportData::statement()
        };
        let mut subjects: Vec<String> = [module.name.as_str(), b.target]
            .into_iter()
            .filter(|subject| !subject.is_empty())
            .map(str::to_owned)
            .collect();
        subjects.sort();
        let title = match b.symbol {
            Some(symbol) if !symbol.is_empty() => format!("Import {}.{symbol}", b.target),
            _ => format!("Import {}", b.target),
        };
        self.records.push(Record {
            id: FactId::new(stable_id("IMP", &parts)),
            evidence_class: EvidenceClass::Fact,
            area: Area::Dependencies,
            title,
            subjects,
            evidence_ids: vec![EvidenceId::new(evidence_id)],
            fact_ids: Vec::new(),
            data: ImportFact::Import(data),
        });
    }
}

#[cfg(test)]
#[path = "imports_tests.rs"]
mod tests;
