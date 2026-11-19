// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol records that `boundary_types` reads (AD-550): the callables with the shape of each
//! written type, the classes, and the one plain import that binds a name of a module.
//!
//! The table names no language. A record that the collector does not write is absent, and an
//! absent record is a named gap of the rule, never an empty answer. A name has a definition when
//! the collector wrote the record of its one binder, or a route when one plain import binds it.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use archkeel_facts::envelope::Facts;
use archkeel_facts::standard::{StandardFacts, Wrapped};
use archkeel_facts::type_shape::{Binding, TypeShape};
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

/// The entry that one symbol record gives.
fn entry_of(fact: &SymbolFact, evidence: Vec<String>) -> Entry {
    match fact {
        SymbolFact::Function(data) | SymbolFact::Method(data) => Entry::Callable(Callable {
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
        }),
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
    }
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
    /// What the collector states about the standard library (AD-782): read only under the premise.
    standard: StandardFacts,
}

/// What the collector states about one name of the standard library (AD-782).
pub(crate) enum Standard<'a> {
    /// A type that it names: it counts under the premise `standard_library_unchanged`.
    Type,
    /// A type that code of the repository may change, with the reason.
    Changed(&'a str),
}

/// What a name resolves to.
pub(crate) enum Origin<'a> {
    /// The record of the definition, with its qualified name.
    Defined(&'a str, &'a Entry),
    /// A whole module: a name of an `import m`.
    Module,
    /// A definition that the collector did not write: the module that holds no record, and the
    /// qualified name that the routes reach.
    Missing { module: String, qualified: String },
}

impl BoundaryFacts {
    /// The table of the symbol and import records of a reply.
    pub(crate) fn derive(facts: &Facts) -> Self {
        let mut table = BoundaryFacts {
            standard: facts.standard.clone().unwrap_or_default(),
            ..BoundaryFacts::default()
        };
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
            let name = record.data.fields().qualified_name.unwrap_or_default();
            let evidence = record
                .evidence_ids
                .iter()
                .map(|id| id.as_str().to_owned())
                .collect();
            if let SymbolFact::Method(data) = &record.data {
                let parent = data.parent.clone().unwrap_or_default();
                methods.entry(parent).or_default().push(name.to_owned());
            }
            self.entries
                .insert(name.to_owned(), entry_of(&record.data, evidence));
        }
        for (class, mut found) in methods {
            if let Some(Entry::Class(entry)) = self.entries.get_mut(&class) {
                found.sort();
                entry.methods = found;
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

    pub(crate) fn canonical_protocol(&self, target: &str) -> bool {
        self.standard.protocol_unchanged
            && matches!(self.entry(target), Some(Entry::Class(class))
        if class.kind == Some(ClassKind::Protocol)
            && class.bases == ["typing.Protocol"]
            && class.members.as_ref().is_some_and(|members| !IntoIterator::into_iter(Vec::as_slice(members)).any(|name| name == "_is_protocol")))
            && target
                .rsplit_once('.')
                .is_some_and(|(module, _)| self.standard.protocol_members.contains_key(module))
    }

    pub(crate) fn protocol_member(&self, shape: &TypeShape, protocol: &str) -> Option<bool> {
        match shape {
            TypeShape::Named {
                binding: Binding::Defined { target } | Binding::Imported { target },
                ..
            } => match self.origin_of(target) {
                Origin::Defined(name, Entry::Class(_)) => Some(name == protocol),
                _ => None,
            },
            TypeShape::Unannotated {}
            | TypeShape::Nothing {}
            | TypeShape::Primitive { .. }
            | TypeShape::Dynamic { .. } => Some(false),
            _ => None,
        }
    }

    pub(crate) fn annotation_text(shape: &TypeShape) -> String {
        TypeShape::text(shape).to_owned()
    }

    pub(crate) fn standard(&self) -> &StandardFacts {
        &self.standard
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
                return Origin::Missing { module, qualified };
            };
            match &route.symbol {
                Some(symbol) => (module, name) = (route.target_module.clone(), symbol.clone()),
                None => return Origin::Module,
            }
        }
        let qualified = format!("{module}.{name}");
        Origin::Missing { module, qualified }
    }

    /// The origin of a qualified name `module.name`.
    pub(crate) fn origin_of<'a>(&'a self, qualified: &str) -> Origin<'a> {
        match qualified.rsplit_once('.') {
            Some((module, name)) => self.origin(module, name),
            None => Origin::Missing {
                module: String::new(),
                qualified: qualified.to_owned(),
            },
        }
    }
}

/// What the collector states about the standard library name `qualified`, if anything (AD-782).
pub(crate) fn standard_of<'a>(facts: &'a BoundaryFacts, qualified: &str) -> Option<Standard<'a>> {
    let stated = &facts.standard;
    if let Some(reason) = BTreeMap::get(&stated.changed, qualified) {
        return Some(Standard::Changed(reason));
    }
    BTreeSet::contains(&stated.types, qualified).then_some(Standard::Type)
}

/// The form that a decorated definition of the scan exposes, when the collector models it.
pub(crate) fn wrapped_of<'a>(facts: &'a BoundaryFacts, qualified: &str) -> Option<&'a Wrapped> {
    BTreeMap::get(&facts.standard.wrapped, qualified)
}

/// The slots of a wrapped form, as the reader reads the slots of a record.
pub(crate) fn slots_of(slots: &[archkeel_facts::standard::WrappedSlot]) -> Vec<Slot> {
    let slot = |item: &archkeel_facts::standard::WrappedSlot| Slot {
        name: item.name.clone(),
        kind: item.kind.clone(),
        shape: item.shape.clone(),
    };
    IntoIterator::into_iter(slots).map(slot).collect()
}

/// The standard library names that a written position reads by name, if any (#1718).
pub(crate) fn positions_of<'a>(
    facts: &'a BoundaryFacts,
    key: &str,
) -> Option<&'a BTreeSet<String>> {
    BTreeMap::get(&facts.standard.positions, key)
}
