// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol records that `boundary_types` reads (AD-550): the callables with the shape of each
//! written type, the classes, and the one plain import that binds a name of a module.
//!
//! The table names no language. A record that the collector does not write is absent, and an
//! absent record is a named gap of the rule, never an empty answer. A name has a definition when
//! the collector wrote the record of its one binder, or a route when one plain import binds it.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::Facts;
use archkeel_facts::type_shape::TypeShape;
use archkeel_facts::vocab::{ClassKind, MethodKind};
use archkeel_facts::{FactData, ImportFact, Record, Section, SymbolFact};

/// One parameter of a callable: its name as the record writes it and its written type.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Slot {
    pub(crate) name: String,
    pub(crate) kind: String,
    pub(crate) shape: Option<TypeShape>,
}

/// A function or a method with a record.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Callable {
    pub(crate) name: String,
    pub(crate) method: Option<MethodKind>,
    pub(crate) slots: Vec<Slot>,
    /// `None` when the collector wrote no shape for this callable.
    pub(crate) returns: Option<TypeShape>,
    pub(crate) evidence: Vec<String>,
}

/// A class with a record.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Class {
    pub(crate) kind: Option<ClassKind>,
    /// The target of each base, as the collector proves it.
    pub(crate) bases: Vec<String>,
    /// Each name that the body binds, or `None` when the body is withheld.
    pub(crate) members: Option<Vec<String>>,
    /// The names that the class declares as attributes.
    pub(crate) attributes: HashSet<String>,
    /// The qualified names of the methods that have a record.
    pub(crate) methods: Vec<String>,
    pub(crate) evidence: Vec<String>,
}

/// What a qualified name is.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Entry {
    Callable(Callable),
    Class(Class),
    /// A constant, an alias or another named value: no callable and no class.
    Value,
}

/// The one plain import that binds a name of a module.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Route {
    pub(crate) target_module: String,
    pub(crate) symbol: Option<String>,
}

/// The records of one reply that the rule reads.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct BoundaryFacts {
    entries: HashMap<String, Entry>,
    routes: HashMap<(String, String), Route>,
}

/// What a name resolves to.
pub(crate) enum Origin<'a> {
    /// The record of the definition, with its qualified name.
    Defined(&'a str, &'a Entry),
    /// A whole module: a name of an `import m`.
    Module,
    /// A definition that the collector did not write, in this module.
    Missing(String),
}

impl BoundaryFacts {
    /// The table of the symbol and import records of a reply.
    pub(crate) fn derive(facts: &Facts) -> Self {
        let mut table = BoundaryFacts::default();
        for section in &facts.sections {
            match section {
                Section::Symbols(records) => table.symbols(records),
                Section::Imports(records) => table.imports(records),
                _ => {}
            }
        }
        table
    }

    fn symbols(&mut self, records: &[Record<SymbolFact>]) {
        let mut methods: HashMap<String, Vec<String>> = HashMap::new();
        for record in records {
            let evidence: Vec<String> = record
                .evidence_ids
                .iter()
                .map(|id| id.as_str().to_owned())
                .collect();
            let name = record.data.fields().qualified_name.unwrap_or_default();
            let entry = match &record.data {
                SymbolFact::Function(data) | SymbolFact::Method(data) => {
                    if let Some(parent) = &data.parent {
                        methods
                            .entry(parent.clone())
                            .or_default()
                            .push(name.to_owned());
                    }
                    Entry::Callable(Callable {
                        name: data.name.clone(),
                        method: data.method_kind,
                        slots: data
                            .parameters
                            .iter()
                            .map(|item| Slot {
                                name: item.name.clone(),
                                kind: item.kind.clone(),
                                shape: item.shape.clone(),
                            })
                            .collect(),
                        returns: data.returns_shape.clone(),
                        evidence,
                    })
                }
                SymbolFact::Class(data) => Entry::Class(Class {
                    kind: data.class_kind,
                    bases: data
                        .base_declarations
                        .iter()
                        .flat_map(|base| base.targets.clone())
                        .collect(),
                    members: data.class_members.clone(),
                    attributes: data
                        .attribute_declarations
                        .iter()
                        .map(|item| item.name.clone())
                        .collect(),
                    methods: Vec::new(),
                    evidence,
                }),
                _ => Entry::Value,
            };
            self.entries.insert(name.to_owned(), entry);
        }
        for (class, found) in methods {
            if let Some(Entry::Class(entry)) = self.entries.get_mut(&class) {
                entry.methods = found;
                entry.methods.sort();
            }
        }
    }

    fn imports(&mut self, records: &[Record<ImportFact>]) {
        // A name that two imports bind has no route, and neither has an import that is not at
        // module level, is under a type check or is not the one binder of its name.
        let mut seen: HashMap<(String, String), (usize, Option<Route>)> = HashMap::new();
        for record in records {
            let data = record.data.data();
            let Some(binding) = &data.binding else {
                continue;
            };
            let key = (data.source_module.as_str().to_owned(), binding.clone());
            let proven = data.module_level_import
                && !data.under_type_checking
                && data.source_binding_unique == Some(true);
            let found = seen.entry(key).or_default();
            found.0 += 1;
            found.1 = proven.then(|| Route {
                target_module: data.target_module.as_str().to_owned(),
                symbol: data.symbol.clone().filter(|symbol| !symbol.is_empty()),
            });
        }
        self.routes = seen
            .into_iter()
            .filter(|(_, (count, _))| *count == 1)
            .filter_map(|(key, (_, route))| Some((key, route?)))
            .collect();
    }

    /// The entry of a qualified name.
    pub(crate) fn entry(&self, name: &str) -> Option<&Entry> {
        self.entries.get(name)
    }

    /// What `name` of `module` is: a definition, or the origin that the one plain import binds,
    /// followed through at most eight hops. `Missing` names the module that holds no record.
    pub(crate) fn origin<'a>(&'a self, module: &str, name: &str) -> Origin<'a> {
        let (mut module, mut name) = (module.to_owned(), name.to_owned());
        for _ in 0..8 {
            let qualified = format!("{module}.{name}");
            if let Some((key, entry)) = self.entries.get_key_value(&qualified) {
                return Origin::Defined(key.as_str(), entry);
            }
            let Some(route) = self.routes.get(&(module.clone(), name.clone())) else {
                return Origin::Missing(module);
            };
            match &route.symbol {
                Some(symbol) => (module, name) = (route.target_module.clone(), symbol.clone()),
                None => return Origin::Module,
            }
        }
        Origin::Missing(module)
    }

    /// The origin of a qualified name `module.name`.
    pub(crate) fn origin_of<'a>(&'a self, qualified: &str) -> Origin<'a> {
        match qualified.rsplit_once('.') {
            Some((module, name)) => self.origin(module, name),
            None => Origin::Missing(String::new()),
        }
    }
}
