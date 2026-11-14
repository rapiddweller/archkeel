// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The static imports of the selected modules (`imports.ImportCollector`, `collect_imports`).
//!
//! An import inside a function or a class is a record too; only a statement outside of each
//! definition is a module-level import. The body of `if <guard>:` (`guard.rs`: a `TYPE_CHECKING`
//! bound only by an import from `typing`) marks its imports `under_type_checking`.

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::{Stmt, StmtImportFrom};
use ruff_text_size::{Ranged, TextRange};

use super::binders::{first_part, Binders};
use super::guard::Guard;
use super::package_body::{anchor, open_body, own_submodules, shadowing_names};
use crate::module::{EvidenceMap, Location, Module};
use crate::names::package_for;

/// What a module-level import binds a name to (`source.AliasBinding`): the target module, or
/// the module and the symbol joined by a dot.
pub(super) struct Alias {
    pub target: String,
    pub module: bool,
}

/// `ParsedModule.aliases`: the last module-level import of each name wins, as in the dict.
pub(super) type Aliases = HashMap<String, Alias>;

/// The import records of all modules, sorted by id, and the aliases of each module.
/// `binders` has one entry for each module.
#[cfg(test)]
pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
) -> (Vec<Record<ImportFact>>, Vec<Aliases>) {
    let found = collect_all(modules, binders, namespace, evidence);
    (found.records, found.aliases)
}

/// What the import walk finds: the records, the aliases and the ambiguous records.
pub(super) struct Collected {
    pub records: Vec<Record<ImportFact>>,
    pub aliases: Vec<Aliases>,
    /// The ids of each `from pkg import name` where `pkg` can give an attribute or the module
    /// `pkg.name` (AD-450): the package binds the name, or has `__getattr__` or a star import.
    pub ambiguous: HashSet<String>,
}

/// `collect`, with the ambiguous records.
pub(super) fn collect_all(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
) -> Collected {
    let names: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    // AD-450: a dotted prefix of a module is a package directory, also without `__init__.py`.
    let directories: HashSet<&str> = names
        .iter()
        .flat_map(|name| name.match_indices('.').map(move |(at, _)| &name[..at]))
        .collect();
    let bindings = package_bindings(modules);
    let open: HashMap<&str, HashSet<String>> = modules
        .iter()
        .filter(|module| module.is_init() && open_body(module))
        .map(|module| (module.name.as_str(), own_submodules(module)))
        .collect();
    let mut records = Vec::new();
    let mut aliases = Vec::with_capacity(modules.len());
    let mut ambiguous = HashSet::new();
    for (module, binders) in modules.iter().zip(binders) {
        let mut found = Aliases::new();
        let mut collector = Collector {
            module,
            binders,
            unique: binders.unique(),
            names: &names,
            directories: &directories,
            guard: Guard::of(&module.tree, binders),
            bindings: &bindings,
            open: &open,
            namespace,
            evidence: &mut *evidence,
            records: &mut records,
            aliases: &mut found,
            ambiguous: &mut ambiguous,
        };
        collector.body(&module.tree.body, true, false);
        aliases.push(found);
    }
    records.sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
    Collected {
        records,
        aliases,
        ambiguous,
    }
}

/// The import record of each literal import call (AD-472): `(module index, range, target)`. A
/// record has no binding, is not at module level and re-exports nothing.
pub(super) fn literal_records(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
    sites: &[(usize, TextRange, String)],
) -> Vec<Record<ImportFact>> {
    let (names, directories, bindings, open) = (
        HashSet::new(),
        HashSet::new(),
        HashMap::new(),
        HashMap::new(),
    );
    let (mut records, mut aliases, mut ambiguous) = (Vec::new(), Aliases::new(), HashSet::new());
    for (index, range, target) in sites {
        let (module, binders) = (&modules[*index], &binders[*index]);
        let mut collector = Collector {
            module,
            binders,
            unique: HashSet::new(),
            names: &names,
            directories: &directories,
            guard: Guard::default(),
            bindings: &bindings,
            open: &open,
            namespace,
            evidence: &mut *evidence,
            records: &mut records,
            aliases: &mut aliases,
            ambiguous: &mut ambiguous,
        };
        let found = Binding {
            target,
            symbol: None,
            binding: None,
            level: 0,
        };
        collector.record((range, false, false), &found);
    }
    records
}

/// `collect_package_bindings`: for each package, the names that its body binds ahead of a
/// submodule. A later module of the same name replaces an earlier one, as in the Python dict.
pub(super) fn package_bindings(modules: &[Module]) -> HashMap<&str, HashSet<String>> {
    modules
        .iter()
        .filter(|module| module.is_init())
        .map(|module| (module.name.as_str(), shadowing_names(module)))
        .collect()
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

/// The alias target of `import a.b`: the module `a`, or `a.b` itself under an `as` name.
fn import_target(alias: &ruff_python_ast::Alias) -> &str {
    let name = alias.name.as_str();
    if alias.asname.is_some() {
        name
    } else {
        first_part(name)
    }
}

struct Collector<'m, 'e> {
    module: &'m Module,
    binders: &'m Binders,
    unique: HashSet<String>,
    names: &'m HashSet<&'m str>,
    directories: &'m HashSet<&'m str>,
    guard: Guard,
    bindings: &'m HashMap<&'m str, HashSet<String>>,
    open: &'m HashMap<&'m str, HashSet<String>>,
    namespace: &'m str,
    evidence: &'e mut EvidenceMap,
    records: &'e mut Vec<Record<ImportFact>>,
    aliases: &'e mut Aliases,
    ambiguous: &'e mut HashSet<String>,
}

/// What one import binding is: the target, the symbol, the binding and the relative level.
struct Binding<'t> {
    target: &'t str,
    symbol: Option<&'t str>,
    binding: Option<&'t str>,
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
                self.body(&node.body, level, guarded || self.guard.holds(&node.test));
                for clause in &node.elif_else_clauses {
                    let test = clause
                        .test
                        .as_ref()
                        .is_some_and(|test| self.guard.holds(test));
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
                        binding: Some(binding),
                        level: 0,
                    };
                    self.bind(level, binding, import_target(alias).to_owned(), true);
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
                    binding: Some("*"),
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
            // A submodule or a package directory: `from app import service` imports it as
            // `import app.service` does, and a directory without a module file is a gap.
            let exists = self.names.contains(submodule.as_str())
                || self.directories.contains(submodule.as_str());
            let local = !shadowed && exists;
            let open = self
                .open
                .get(anchor.as_str())
                .is_some_and(|own| !own.contains(&submodule));
            let ambiguous = exists && (shadowed || open);
            let binding = alias.asname.as_ref().map_or(name, |a| a.as_str());
            let target = if local {
                submodule.clone()
            } else {
                format!("{anchor}.{name}")
            };
            self.bind(place.1, binding, target, local);
            let found = Binding {
                target: if local { &submodule } else { &anchor },
                symbol: if local { None } else { Some(name) },
                binding: Some(binding),
                level: node.level,
            };
            self.record(place, &found);
            let last = self.records.last().filter(|_| ambiguous);
            self.ambiguous
                .extend(last.map(|record| record.id.as_str().to_owned()));
        }
    }

    /// `_bind`: only a module-level import changes the namespace of the module.
    fn bind(&mut self, module_level: bool, binding: &str, target: String, module: bool) {
        if module_level {
            let alias = Alias { target, module };
            self.aliases.insert(binding.to_owned(), alias);
        }
    }

    fn record<N: Ranged>(&mut self, (node, module_level, guarded): (&N, bool, bool), b: &Binding) {
        let module = self.module;
        let evidence_id = module.evidence(self.evidence, node);
        let Location { line, column, .. } = module.location(node);
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
            b.binding.map_or(Part::Nothing, Part::Text),
        ];
        // A literal import call binds no name and re-exports nothing (AD-472).
        let init = module.is_init() && b.binding.is_some();
        let exported = b
            .binding
            .is_some_and(|name| self.binders.all_exports.contains(name));
        let literal_unique =
            self.binders.all_literal && b.binding.is_some_and(|name| self.unique.contains(name));
        let data = ImportData {
            source_module: ModuleName::new(module.name.as_str()),
            source_package: PackageName::new(module.package.as_str()),
            target_module: ModuleName::new(b.target),
            target_package: PackageName::new(target_package),
            symbol: b.symbol.map(str::to_owned),
            binding: b.binding.map(str::to_owned),
            symbols_known: true,
            specifier: None,
            type_only: None,
            relative_level: i64::from(b.level),
            under_type_checking: guarded,
            reexport: init || (exported && literal_unique),
            module_level_import: module_level,
            ordinary_module: Some(!module.is_init()),
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
