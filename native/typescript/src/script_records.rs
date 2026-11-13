// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the script analysis writes: the import records of the globals, their targets, their gaps and
//! the facts that the later records cite (`collect._script_*`).

use std::collections::HashMap;

use archkeel_facts::data::{BindingData, ImportData};
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{evidence_id, package_of, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{Area, EvidenceClass, ResolutionDimension};
use archkeel_facts::{BindingFact, GapFact};
use archkeel_facts::{ImportFact, Record};

use crate::sites::SiteKind;
use crate::source::Span;

/// The reason of the gap of an effect that no publication bounds.
pub(crate) const UNBOUNDED_EFFECT: &str = "Script namespace effects are not statically bounded";

/// The identity of a site that the maps below use: its place, its kind and its path. A site that
/// the analysis makes up (the member of a destructuring) has its own place and path.
#[derive(Clone, PartialEq, Eq, Hash)]
pub(crate) struct SiteKey {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub kind: SiteKind,
    pub path: Vec<String>,
}

impl SiteKey {
    pub(crate) fn new(kind: SiteKind, span: &Span, path: &[String]) -> Self {
        Self {
            line: span.line,
            end_line: span.end_line,
            column: span.column,
            kind,
            path: path.to_vec(),
        }
    }
}

/// What the records of a module read about its sites.
#[derive(Default)]
pub(crate) struct ModuleScript {
    /// `script_resolution`: the targets of a site that a published global resolves.
    pub resolution: HashMap<SiteKey, Vec<String>>,
    /// `script_evidence`: the evidence of a site that an alias proves.
    pub evidence: HashMap<SiteKey, Vec<String>>,
    /// `script_fact_ids`: the facts that prove a site.
    pub fact_ids: HashMap<SiteKey, Vec<String>>,
}

/// A script runtime effect that no publication bounds: the place of a write.
pub(crate) struct Effect {
    pub rel: String,
    pub module: String,
    pub span: Span,
}

/// Everything that the records after the imports read from the script analysis.
#[derive(Default)]
pub(crate) struct ScriptFacts {
    pub modules: HashMap<String, ModuleScript>,
    /// `script_publications`: the bindings that the imports cite, in the order of insertion.
    pub publications: Vec<Record<BindingFact>>,
    published: HashMap<String, usize>,
    /// The effects, in the order of `script_pending_effects` without repeats.
    pub effects: Vec<Effect>,
    /// The locations that the analysis cited, in order: the evidence of a location is the last
    /// citation of it (`record_evidence`).
    pub cites: Vec<(String, Span)>,
}

impl ScriptFacts {
    pub(crate) fn module(&mut self, module: &str) -> &mut ModuleScript {
        self.modules.entry(module.to_owned()).or_default()
    }

    /// `self.script_fact_ids.get((module, site), ())`.
    pub(crate) fn fact_ids(&self, module: &str, key: &SiteKey) -> Vec<String> {
        let found = self.modules.get(module).and_then(|m| m.fact_ids.get(key));
        found.cloned().unwrap_or_default()
    }

    /// Add a binding record: a repeated id keeps its place and takes the new record.
    pub(crate) fn publish(&mut self, record: Record<BindingFact>) {
        match self.published.get(record.id.as_str()) {
            Some(at) => {
                if let Some(slot) = self.publications.get_mut(*at) {
                    *slot = record;
                }
            }
            None => {
                self.published
                    .insert(record.id.as_str().to_owned(), self.publications.len());
                self.publications.push(record);
            }
        }
    }
}

/// An UNKNOWN record of the gaps.
pub(crate) type GapRecord = Record<GapFact>;

/// The output of the analysis.
#[derive(Default)]
pub(crate) struct Sink {
    pub facts: ScriptFacts,
    /// The UNKNOWN records of the analysis with their ids, as the collection keeps them.
    pub gaps: Vec<(String, GapRecord)>,
    pub imports: Vec<Record<ImportFact>>,
    pub targets: Vec<Target>,
}

impl Sink {
    /// `collect._cite`: the id of the location; the excerpt is registered when the reply is written.
    pub(crate) fn cite(&mut self, rel: &str, span: &Span) -> String {
        // A citation that repeats the one before changes nothing, so it is not kept.
        let repeated = self
            .facts
            .cites
            .last()
            .is_some_and(|(last, at)| last == rel && at == span);
        if !repeated {
            self.facts.cites.push((rel.to_owned(), span.clone()));
        }
        evidence_id(rel, span.line, span.end_line, span.column)
    }

    /// A resolution gap with the given evidence (`collect._gap`).
    pub(crate) fn gap(&mut self, reason: &str, evidence: &[String], module: &str) {
        let fact = GapFact::resolution(reason, module);
        let first = evidence.first().map(String::as_str);
        self.gaps
            .push(GapRecord::unknown_gap(reason, first, module, fact));
    }

    /// The gap of a runtime effect: its id is made from the effect, and it names the effect as its
    /// fact (`_script_runtime_effect`).
    pub(crate) fn effect_gap(&mut self, module: &str, effect: &str, evidence: &str) {
        let id = stable_id("UNKNOWN_RUNTIME_EFFECT", &[Part::Text(effect)]);
        let mut fact = GapFact::resolution(UNBOUNDED_EFFECT, module);
        if let GapFact::SourceResolutionGap(data) = &mut fact {
            data.resolution_dimension = Some(ResolutionDimension::RuntimeEffects);
        }
        let mut record = GapRecord::unknown(
            FactId::new(id.clone()),
            UNBOUNDED_EFFECT,
            Some(evidence),
            module,
            fact,
        );
        record.fact_ids = vec![FactId::new(effect)];
        self.gaps.push((id, record));
    }
}

fn sorted(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values
}

/// `classified` for a record of the `bindings` section.
pub(crate) fn binding(
    id: String,
    title: String,
    module: &str,
    evidence: Vec<String>,
    data: BindingData,
) -> Record<BindingFact> {
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title,
        subjects: vec![module.to_owned()],
        evidence_ids: sorted(evidence).into_iter().map(EvidenceId::new).collect(),
        fact_ids: Vec::new(),
        data: BindingFact::Bindings(data),
    }
}

/// What `_script_import_record` needs.
pub(crate) struct Use<'a> {
    pub module: &'a str,
    pub kind: SiteKind,
    pub span: &'a Span,
    pub path: &'a [String],
    pub target_module: &'a str,
    pub target_package: Option<&'a str>,
    pub symbol: Option<&'a str>,
    pub known: bool,
    pub evidence: Vec<String>,
    pub binding: Option<&'a str>,
    pub facts: Vec<String>,
}

/// The id of the global record of a site (`stable_id("TSGLOBAL", ...)`).
pub(crate) fn global_id(module: &str, kind: SiteKind, span: &Span) -> String {
    let kind = kind.as_str();
    let parts = [
        Part::Text(module),
        Part::Number(span.line),
        Part::Number(span.column),
        Part::Text(kind),
    ];
    stable_id("TSGLOBAL", &parts)
}

/// `_script_import_record`.
pub(crate) fn import_record(item: &Use) -> Record<ImportFact> {
    let first = item.path.first().map_or("", String::as_str);
    let module = item.module;
    let mut subjects: Vec<String> = [module, item.target_module]
        .into_iter()
        .filter(|name| !name.is_empty())
        .map(str::to_owned)
        .collect();
    subjects.sort();
    let target_package = item
        .target_package
        .map_or_else(|| package_of(item.target_module).to_owned(), str::to_owned);
    let member = match item.path {
        [_, member] => Nullable::Value(member.clone()),
        _ => Nullable::Null,
    };
    let data = ImportData {
        source_module: ModuleName::new(module),
        source_package: PackageName::new(package_of(module)),
        target_module: ModuleName::new(item.target_module),
        target_package: PackageName::new(target_package),
        symbol: item.symbol.map(str::to_owned),
        binding: Some(item.binding.unwrap_or(first).to_owned()),
        symbols_known: item.known,
        specifier: Some(first.to_owned()),
        type_only: Some(false),
        relative_level: 0,
        under_type_checking: false,
        reexport: false,
        module_level_import: false,
        script_global: Some(first.to_owned()),
        script_member: member,
        ..ImportData::statement()
    };
    Record {
        id: FactId::new(global_id(module, item.kind, item.span)),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{module} uses script global {first}"),
        subjects,
        evidence_ids: sorted(item.evidence.clone())
            .into_iter()
            .map(EvidenceId::new)
            .collect(),
        fact_ids: sorted(item.facts.clone())
            .into_iter()
            .map(FactId::new)
            .collect(),
        data: ImportFact::ScriptGlobal(data),
    }
}
