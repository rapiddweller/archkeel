// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state that the collection fills: gaps, evidence, file facts and the edges. Each part of the
//! collector (`edges`, `declared`, `module_edges`) adds to it; this module imports none of them.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::envelope::Target;
use archkeel_facts::envelope::{Evidence, FileFact};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass, ResolutionDimension};
use archkeel_facts::{GapFact, ImportFact, Record, SymbolFact};

use crate::crates::Problem;
use crate::definitions::MethodCall;
use crate::modules::Edge;
use crate::scan::{Reference, Site};
use crate::tree::Module;

/// How an edge is written: a path in source, or a dependency that a manifest declares. The form
/// is part of the identity of the import record.
#[derive(Clone, Copy)]
pub(crate) enum Form {
    Import,
    Declared,
}

impl Form {
    pub(crate) fn text(self) -> &'static str {
        match self {
            Self::Import => "import",
            Self::Declared => "declared",
        }
    }
}

/// Where an edge starts: the module, the file that cites it and the kind of the evidence. A
/// declared dependency starts in the main module of its crate and cites its manifest.
#[derive(Clone, Copy)]
pub(crate) struct Origin<'a> {
    pub(crate) module: &'a str,
    pub(crate) rel: &'a str,
    pub(crate) form: Form,
}

impl<'a> Origin<'a> {
    pub(crate) fn of(module: &'a Module) -> Self {
        Self {
            module: &module.module,
            rel: &module.rel,
            form: Form::Import,
        }
    }
}

type ImportKey = (String, String, String, Option<(String, String)>);

#[derive(Default)]
pub(crate) struct Builder {
    pub(crate) gaps: BTreeMap<String, Record<GapFact>>,
    pub(crate) named_sites: BTreeMap<String, Record<GapFact>>,
    pub(crate) evidence: BTreeMap<String, Evidence>,
    pub(crate) files: Vec<FileFact>,
    pub(crate) imports: Vec<Record<ImportFact>>,
    pub(crate) symbols: Vec<Record<SymbolFact>>,
    pub(crate) targets: Vec<Target>,
    pub(crate) seen: BTreeSet<ImportKey>,
    /// The manifests of the crates: each is a module that holds the declared dependencies.
    pub(crate) manifests: Vec<String>,
    /// A proof of the scan rests on a registry identity that `Cargo.lock` records (AD-774).
    pub(crate) lock_premise: bool,
    /// The request leaves test scope out: a dev-dependency is then no edge.
    pub(crate) exclude_tests: bool,
    /// The modules that the body of each `macro_rules!` names from the crate root, by the module
    /// of the file and the id of the definition in it.
    pub(crate) macro_uses: BTreeMap<(String, usize), Vec<(Edge, Reference)>>,
    /// The reasons why the scan cannot read the body of each `macro_rules!`, by the same key.
    pub(crate) macro_unknowns: BTreeMap<(String, usize), Vec<String>>,
    /// The methods that the macros called in each module call there, at the place of the call.
    pub(crate) macro_methods: BTreeMap<String, Vec<MethodCall>>,
    /// Each function name that a macro body defines, and the modules that call the macro
    /// (AD-383): a call on `self` of that name is not resolved, since the expansion may be a
    /// member that the scan does not see.
    pub(crate) macro_members: BTreeMap<String, BTreeSet<String>>,
    /// The members that a macro call can add to an `impl` block outside the file of its type,
    /// by name, with the modules of the calls: a method call gets a pair gap to each (#1196).
    pub(crate) macro_foreign_members: BTreeMap<String, BTreeSet<String>>,
    /// The modules where a macro call may write an impl that is not anchored there, with the file
    /// and the site of the first such call: each module that may reach one gets a pair gap
    /// (#1371, AD-516).
    pub(crate) macro_impl_homes: BTreeMap<String, (String, crate::site::Site)>,
    /// The pairs that have a pair gap: one gap is enough for each pair.
    pub(crate) gapped: BTreeMap<(String, String), String>,
    /// The outcomes that the edges ended, for the invariant of the extraction
    /// (`edges_extracted.rs`): a running total, and the references and macro calls by file.
    pub(crate) ended: usize,
    pub(crate) ended_references: BTreeMap<String, usize>,
    pub(crate) ended_calls: BTreeMap<String, usize>,
    pub(crate) ended_methods: BTreeMap<String, usize>,
    /// The names that each crate root publishes, for the route of a member (AD-608).
    pub(crate) publications: crate::routes::Publications,
    /// Modules with a path to code whose value transfers the scan does not read.
    pub(crate) opaque_values: BTreeSet<String>,
}

impl Builder {
    /// Keep one coverage record, but do not let a later path inherit a proof from an earlier call.
    pub(crate) fn pair_already_reported(
        &mut self,
        pair: &(String, String),
        no_name_route: bool,
    ) -> bool {
        let Some(id) = self.gapped.get(pair) else {
            return false;
        };
        if let Some(Record {
            data: GapFact::CollectionGap(data),
            ..
        }) = self.gaps.get_mut(id)
        {
            data.no_name_route &= no_name_route;
        }
        true
    }

    pub(crate) fn gap(&mut self, reason: &str, evidence: Option<&str>, module: &str) {
        let fact = GapFact::collection(reason, module);
        let (id, record) = Record::unknown_gap(reason, evidence, module, fact);
        self.gaps.entry(id).or_insert(record);
    }

    pub(crate) fn external_origin(&mut self, module: &str, evidence: &str, package: &str) {
        let reason = format!("A re-export reaches unread package {package}: its origin is unknown");
        let mut data = GapData::at(&reason, module);
        data.effect = Some(GapEffect::Edges {
            sources: vec![ModuleName::new(module)],
        });
        let fact = GapFact::CollectionGap(data);
        let (id, record) = Record::unknown_gap(&reason, Some(evidence), module, fact);
        self.gaps.entry(id).or_insert(record);
    }

    /// The gap of one pair: the scan cannot tell whether `source` uses `target` (#953). The host
    /// drops it when the contract lets the component of `source` use the component of `target`.
    pub(crate) fn pair_gap(
        &mut self,
        reason: &str,
        evidence: &str,
        pair: (&str, &str),
        dispatch: Option<ResolutionDimension>,
        no_name_route: bool,
    ) -> String {
        let (source, target) = pair;
        let mut data = GapData::at(reason, target);
        data.source_module = Some(ModuleName::new(source));
        data.dispatch = dispatch.is_some();
        data.no_name_route = no_name_route;
        data.resolution_dimension =
            dispatch.filter(|kind| *kind == ResolutionDimension::RuntimeEffects);
        let fact = GapFact::CollectionGap(data);
        let (id, record) = Record::unknown_gap(reason, Some(evidence), source, fact);
        self.gaps.entry(id.clone()).or_insert(record);
        id
    }

    /// A known edge does not prove which name a separate call uses.
    pub(crate) fn named_site(
        &mut self,
        (source, target): (&str, &str),
        (rel, site): (&str, &Site),
        reason: &str,
        no_name_route: bool,
    ) {
        let evidence = self.cite(rel, site);
        let mut data = GapData::at(reason, target);
        data.source_module = Some(ModuleName::new(source));
        data.resolution_dimension = Some(ResolutionDimension::Imports);
        data.no_name_route = no_name_route;
        let fact = GapFact::SourceResolutionGap(data);
        let (id, record) = Record::unknown_gap(reason, Some(&evidence), source, fact);
        self.named_sites
            .entry(id)
            .and_modify(|earlier| {
                if let GapFact::SourceResolutionGap(data) = &mut earlier.data {
                    data.no_name_route &= no_name_route;
                }
            })
            .or_insert(record);
    }

    pub(crate) fn cite(&mut self, rel: &str, site: &Site) -> String {
        let evidence = Evidence::at(rel, site.line, site.end_line, site.column, &site.excerpt);
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    pub(crate) fn problem(&mut self, problem: &Problem, modules: &BTreeMap<&str, &str>) {
        let module = modules.get(problem.file.as_str()).copied().unwrap_or("");
        self.gap(&problem.reason, None, module);
    }

    /// The file fact of a module, with the evidence of its first line.
    pub(crate) fn file(
        &mut self,
        (rel, module, package): (&str, &str, &str),
        blank: bool,
        cited: Evidence,
    ) {
        let evidence_id = cited.id.as_str().to_owned();
        self.evidence.insert(evidence_id.clone(), cited);
        let mut file = FileFact::of((rel, module), blank, evidence_id);
        file.package = PackageName::new(package);
        self.files.push(file);
    }
}

/// The record of one import: the edge from `module` along the path `specifier`, between `subjects`.
pub(crate) fn import_record(
    (identity, evidence): (&str, String),
    (module, specifier): (&str, &str),
    mut subjects: Vec<String>,
    data: ImportFact,
) -> Record<ImportFact> {
    subjects.sort();
    subjects.dedup();
    Record {
        id: FactId::new(identity),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{module} imports {specifier}"),
        subjects,
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data,
    }
}
