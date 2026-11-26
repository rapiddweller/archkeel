// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state that the collection fills: gaps, evidence, file facts and the edges. Each part of the
//! collector (`edges`, `declared`, `module_edges`) adds to it; this module imports none of them.

use std::collections::{BTreeMap, BTreeSet, HashMap};

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

/// Interned strings shared across pair gaps and named sites (#1942).
#[derive(Default)]
struct StringPool {
    values: Vec<String>,
    index: HashMap<String, u32>,
    overflowed: bool,
}

impl StringPool {
    fn intern(&mut self, value: &str) -> u32 {
        if let Some(&id) = self.index.get(value) {
            return id;
        }
        let Ok(id) = u32::try_from(Vec::len(&self.values)) else {
            self.overflowed = true;
            return u32::MAX;
        };
        self.values.push(value.to_owned());
        self.index.insert(value.to_owned(), id);
        id
    }
}

/// Compact pair-gap entry materialized into `Record<GapFact>` at finish (#1942).
struct CompactPairGap {
    source: u32,
    target: u32,
    reason: u32,
    evidence: u32,
    dispatch: bool,
    runtime_effects: bool,
    no_name_route: bool,
}

impl CompactPairGap {
    fn to_record(&self, strings: &[String]) -> Record<GapFact> {
        let dimension = self
            .runtime_effects
            .then_some(ResolutionDimension::RuntimeEffects);
        compact_gap_record(
            strings,
            (self.source, self.target, self.reason, self.evidence),
            (self.dispatch, dimension, self.no_name_route, false),
        )
    }
}

/// Compact named-site gap streamed into the reply without bulk `Record` allocation (#1942).
struct CompactNamedSite {
    source: u32,
    target: u32,
    reason: u32,
    evidence: u32,
    no_name_route: bool,
}

impl CompactNamedSite {
    fn to_record(&self, strings: &[String]) -> Record<GapFact> {
        compact_gap_record(
            strings,
            (self.source, self.target, self.reason, self.evidence),
            (
                false,
                Some(ResolutionDimension::Imports),
                self.no_name_route,
                true,
            ),
        )
    }
}

fn compact_gap_record(
    strings: &[String],
    (source, target, reason, evidence): (u32, u32, u32, u32),
    (dispatch, resolution_dimension, no_name_route, source_resolution): (
        bool,
        Option<ResolutionDimension>,
        bool,
        bool,
    ),
) -> Record<GapFact> {
    let source = pool_str(strings, source);
    let target = pool_str(strings, target);
    let reason = pool_str(strings, reason);
    let evidence = pool_str(strings, evidence);
    let mut data = GapData::at(reason, target);
    data.source_module = Some(ModuleName::new(source));
    data.dispatch = dispatch;
    data.no_name_route = no_name_route;
    data.resolution_dimension = resolution_dimension;
    let fact = if source_resolution {
        GapFact::SourceResolutionGap(data)
    } else {
        GapFact::CollectionGap(data)
    };
    Record::unknown_gap(reason, Some(evidence), source, fact).1
}

fn pool_str(strings: &[String], id: u32) -> &str {
    usize::try_from(id)
        .ok()
        .and_then(|s| strings.get(s))
        .map_or("", String::as_str)
}

/// Sort key matching `UNKNOWN-<16 hex>` lexicographical order without holding all `Record`s.
fn unknown_id_key(reason: &str, evidence: &str, source: &str) -> u64 {
    let (id, _) = Record::unknown_gap(reason, Some(evidence), source, GapFact::collection("", ""));
    u64::from_str_radix(id.strip_prefix("UNKNOWN-").unwrap_or(""), 16).unwrap_or(0)
}

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
    strings: StringPool,
    pair_gaps: Vec<CompactPairGap>,
    pair_gap_index: HashMap<(u32, u32, u32), u32>,
    named_sites: Vec<CompactNamedSite>,
    named_site_index: HashMap<(u32, u32, u32), u32>,
    pub(crate) evidence: BTreeMap<String, Evidence>,
    pub(crate) files: Vec<FileFact>,
    pub(crate) calls: Vec<Record<archkeel_facts::CallFact>>,
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
    pub(crate) gapped: HashMap<(u32, u32), u32>,
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
    /// The compiler type-reach facts of each configuration, or none (AD-1047).
    pub(crate) type_reach: Vec<crate::type_reach_facts::Facts>,
    /// The filter used the facts: they name a module of the scan (AD-1116).
    pub(crate) reach_used: bool,
}

impl Builder {
    pub(crate) fn with_exclude_tests(exclude_tests: bool) -> Self {
        Self {
            exclude_tests,
            ..Self::default()
        }
    }

    pub(crate) fn intern_text(&mut self, value: &str) -> u32 {
        self.strings.intern(value)
    }

    pub(crate) fn find_text(&self, value: &str) -> Option<u32> {
        self.strings.index.get(value).copied()
    }

    pub(crate) fn interned_text(&self, id: u32) -> &str {
        pool_str(&self.strings.values, id)
    }

    pub(crate) fn interned_count(&self) -> usize {
        Vec::len(&self.strings.values)
    }

    /// Take materialized gaps and return a lightweight `Builder` holding only compact named sites.
    pub(crate) fn take_gaps_and_named_sites(&mut self) -> (Vec<Record<GapFact>>, Self) {
        self.pair_gap_index = HashMap::new();
        self.named_site_index = HashMap::new();
        self.gapped = HashMap::new();
        let gaps = std::mem::take(&mut self.gaps);
        let pair_gaps = std::mem::take(&mut self.pair_gaps);
        let named_sites = std::mem::take(&mut self.named_sites);
        let mut strings = std::mem::take(&mut self.strings);
        strings.index = HashMap::new();
        let mut all = Vec::with_capacity(BTreeMap::len(&gaps) + Vec::len(&pair_gaps));
        all.extend(gaps.into_values());
        all.extend(
            pair_gaps
                .into_iter()
                .map(|entry| entry.to_record(&strings.values)),
        );
        if strings.overflowed {
            let msg = "Internal collector string-pool index limit exceeded";
            all.push(Record::unknown_gap(msg, None, "", GapFact::collection(msg, "")).1);
        }
        all.sort_by(|left, right| left.id.cmp(&right.id));
        all.dedup_by(|later, earlier| later.id == earlier.id);
        (
            all,
            Self {
                strings,
                named_sites,
                ..Self::default()
            },
        )
    }

    /// Stream compact named sites in exact `UNKNOWN-*` id order without bulk `Record` allocation.
    pub(crate) fn stream_named_sites(&self, emit: &mut dyn FnMut(&Record<GapFact>)) {
        let strings = &self.strings.values;
        let mut order: Vec<(u64, usize)> = self
            .named_sites
            .iter()
            .enumerate()
            .map(|(slot, entry)| {
                let key = unknown_id_key(
                    pool_str(strings, entry.reason),
                    pool_str(strings, entry.evidence),
                    pool_str(strings, entry.source),
                );
                (key, slot)
            })
            .collect();
        order.sort_unstable_by_key(|&(key, _)| key);
        for (_, slot) in order {
            if let Some(entry) = self.named_sites.get(slot) {
                emit(&entry.to_record(strings));
            }
        }
    }

    /// Keep one coverage record, but do not let a later path inherit a proof from an earlier call.
    pub(crate) fn pair_already_reported(
        &mut self,
        source: &str,
        target: &str,
        no_name_route: bool,
    ) -> bool {
        let (Some(src), Some(dst)) = (self.find_text(source), self.find_text(target)) else {
            return false;
        };
        self.pair_already_reported_ids((src, dst), no_name_route)
    }

    pub(crate) fn pair_already_reported_ids(
        &mut self,
        pair: (u32, u32),
        no_name_route: bool,
    ) -> bool {
        let Some(&slot) = self.gapped.get(&pair) else {
            return false;
        };
        if let Some(entry) = usize::try_from(slot)
            .ok()
            .and_then(|index| self.pair_gaps.get_mut(index))
        {
            entry.no_name_route &= no_name_route;
        }
        true
    }

    pub(crate) fn mark_gapped(&mut self, source: &str, target: &str, slot: u32) {
        let src = self.strings.intern(source);
        let dst = self.strings.intern(target);
        self.gapped.insert((src, dst), slot);
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
    ) -> u32 {
        let (source, target) = pair;
        let reason_id = self.strings.intern(reason);
        let evidence_id = self.strings.intern(evidence);
        let source_id = self.strings.intern(source);
        if let Some(&slot) = self
            .pair_gap_index
            .get(&(reason_id, evidence_id, source_id))
        {
            return slot;
        }
        let target_id = self.strings.intern(target);
        let slot = u32::try_from(Vec::len(&self.pair_gaps)).unwrap_or(u32::MAX);
        self.pair_gaps.push(CompactPairGap {
            source: source_id,
            target: target_id,
            reason: reason_id,
            evidence: evidence_id,
            dispatch: dispatch.is_some(),
            runtime_effects: dispatch == Some(ResolutionDimension::RuntimeEffects),
            no_name_route,
        });
        self.pair_gap_index
            .insert((reason_id, evidence_id, source_id), slot);
        slot
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
        let reason_id = self.strings.intern(reason);
        let evidence_id = self.strings.intern(&evidence);
        let source_id = self.strings.intern(source);
        if let Some(&slot) = self
            .named_site_index
            .get(&(reason_id, evidence_id, source_id))
        {
            if let Some(earlier) = usize::try_from(slot)
                .ok()
                .and_then(|index| self.named_sites.get_mut(index))
            {
                earlier.no_name_route &= no_name_route;
            }
            return;
        }
        let target_id = self.strings.intern(target);
        let slot = u32::try_from(Vec::len(&self.named_sites)).unwrap_or(u32::MAX);
        self.named_sites.push(CompactNamedSite {
            source: source_id,
            target: target_id,
            reason: reason_id,
            evidence: evidence_id,
            no_name_route,
        });
        self.named_site_index
            .insert((reason_id, evidence_id, source_id), slot);
    }

    #[cfg(test)]
    pub(crate) fn materialize_test_gaps(&self) -> Vec<Record<GapFact>> {
        let mut all = Vec::with_capacity(BTreeMap::len(&self.gaps) + Vec::len(&self.pair_gaps));
        all.extend(self.gaps.values().cloned());
        all.extend(
            self.pair_gaps
                .iter()
                .map(|entry| entry.to_record(&self.strings.values)),
        );
        all.sort_by(|left, right| left.id.cmp(&right.id));
        all.dedup_by(|later, earlier| later.id == earlier.id);
        all
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
