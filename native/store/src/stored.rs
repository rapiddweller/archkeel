// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of one validated reply, kept in their typed form (AD-346).
//!
//! The store keeps the decoded `Reply` and finds a record by its id. One section dispatch
//! (`visit`) gives each record to a typed visitor. The Python byte formats (`canonical`, `pyrepr`,
//! `inventory`) see one record at a time as JSON (`saved`); no record is held in that form.
//!
//! An import record gets the projection of `check/evaluation/evaluate.py:evaluate_source` when it
//! is saved: an unresolved import gets `resolution`; a TypeScript import gets its external package
//! or builtin flag; a resolved import loses the five keys of the re-export bookkeeping.

use std::collections::HashMap;

use archkeel_facts::envelope::{Evidence, Profile, Reply, Target};
use archkeel_facts::{FactData, Record, Section};
use serde_json::{Map, Value};

/// The keys that the observation removes from a resolved import (`strip_internal_reexport_facts`).
/// This projection copies `evaluate.py:evaluate_source` for now: the PR after #941 deletes the
/// Python copies (WP4).
const BOOKKEEPING: [&str; 5] = [
    "ordinary_module",
    "origin_binding_unique",
    "origin_member_binding_static",
    "reexport_candidate",
    "module_level_import",
];

/// A typed visitor of the records of one section.
pub(crate) trait Visitor {
    fn record<D: FactData>(&mut self, section: &Section, record: &Record<D>) -> Result<(), String>;
}

fn each<D: FactData, V: Visitor>(
    section: &Section,
    records: &[Record<D>],
    visitor: &mut V,
) -> Result<(), String> {
    records
        .iter()
        .try_for_each(|record| visitor.record(section, record))
}

/// Give the records of `section` from `start` to `end` to `visitor`.
pub(crate) fn visit<V: Visitor>(
    section: &Section,
    start: usize,
    end: usize,
    visitor: &mut V,
) -> Result<(), String> {
    let range = start..end;
    match section {
        Section::Imports(records) => each(section, &records[range], visitor),
        Section::Symbols(records) => each(section, &records[range], visitor),
        Section::Calls(records) => each(section, &records[range], visitor),
        Section::References(records) => each(section, &records[range], visitor),
        Section::Bindings(records) => each(section, &records[range], visitor),
        Section::Constructs(records) => each(section, &records[range], visitor),
        Section::TypingSignals(records) => each(section, &records[range], visitor),
        Section::Unknowns(records) => each(section, &records[range], visitor),
    }
}

/// The JSON of one record, as the Python writer sees it (stage 1 byte equality).
struct Json(Option<Value>);

impl Visitor for Json {
    fn record<D: FactData>(&mut self, _: &Section, record: &Record<D>) -> Result<(), String> {
        self.0 = Some(serde_json::to_value(record).map_err(|error| error.to_string())?);
        Ok(())
    }
}

/// The observation projection of an import: what its typed target adds or removes.
enum Projection {
    Unresolved,
    External(String),
    Builtin,
    Strip,
}

/// The records and the evidence of one reply, found by id.
pub(crate) struct Store {
    reply: Reply,
    places: HashMap<String, (usize, usize)>,
    evidence: HashMap<String, usize>,
    targets: HashMap<String, usize>,
}

impl Store {
    /// `places` maps each record id to its section and position (built by the validation).
    pub(crate) fn new(reply: Reply, places: HashMap<String, (usize, usize)>) -> Self {
        let evidence = reply
            .facts
            .evidence
            .iter()
            .enumerate()
            .map(|(index, entry)| (entry.id.as_str().to_owned(), index))
            .collect();
        let targets = reply
            .facts
            .imports
            .iter()
            .enumerate()
            .map(|(index, target)| (target.import_id().as_str().to_owned(), index))
            .collect();
        Store {
            reply,
            places,
            evidence,
            targets,
        }
    }

    pub(crate) fn reply(&self) -> &Reply {
        &self.reply
    }

    pub(crate) fn evidence(&self, id: &str) -> Result<&Evidence, String> {
        self.evidence
            .get(id)
            .map(|index| &self.reply.facts.evidence[*index])
            .ok_or_else(|| format!("the store holds no evidence {id}"))
    }

    fn projection(&self, id: &str) -> Projection {
        let target = self
            .targets
            .get(id)
            .map(|index| &self.reply.facts.imports[*index]);
        let typescript = self.reply.facts.profile == Profile::TypeScript;
        match target {
            Some(Target::Unresolved { .. }) => Projection::Unresolved,
            Some(Target::External { package, .. }) if typescript => {
                Projection::External(package.as_str().to_owned())
            }
            Some(Target::Builtin { .. }) if typescript => Projection::Builtin,
            _ => Projection::Strip,
        }
    }

    fn project(&self, id: &str, data: &mut Map<String, Value>) {
        match self.projection(id) {
            Projection::Unresolved => {
                data.insert("resolution".to_owned(), Value::from("unresolved"));
                return;
            }
            Projection::External(package) => {
                data.insert("external_package".to_owned(), Value::from(package));
            }
            Projection::Builtin => {
                data.insert("builtin_target".to_owned(), Value::Bool(true));
            }
            Projection::Strip => {}
        }
        for key in BOOKKEEPING {
            data.remove(key);
        }
    }

    /// The saved JSON object of one record, with the import projection applied.
    pub(crate) fn saved(&self, id: &str) -> Result<Map<String, Value>, String> {
        let (section, index) = *self
            .places
            .get(id)
            .ok_or_else(|| format!("the store holds no record {id}"))?;
        let section = &self.reply.facts.sections[section];
        let mut json = Json(None);
        visit(section, index, index + 1, &mut json)?;
        let Some(Value::Object(mut object)) = json.0 else {
            return Err("a record is not an object".to_owned());
        };
        if matches!(section, Section::Imports(_)) {
            if let Some(Value::Object(data)) = object.get_mut("data") {
                self.project(id, data);
            }
        }
        Ok(object)
    }
}
