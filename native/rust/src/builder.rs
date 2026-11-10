// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state that the collection fills: gaps, evidence, file facts and the edges. Each part of the
//! collector (`edges`, `declared`, `module_edges`) adds to it; this module imports none of them.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_wire::identity::{package_of, stable_id, Part};
use archkeel_wire::reply::{Evidence, FileFact, Target};

use crate::crates::Problem;
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

#[derive(Default)]
pub(crate) struct Builder {
    pub(crate) gaps: BTreeMap<String, Record<GapFact>>,
    pub(crate) evidence: BTreeMap<String, Evidence>,
    pub(crate) files: Vec<FileFact>,
    pub(crate) imports: Vec<Record<ImportFact>>,
    pub(crate) targets: Vec<Target>,
    pub(crate) seen: BTreeSet<(String, String, String)>,
    /// The manifests of the crates: each is a module that holds the declared dependencies.
    pub(crate) manifests: Vec<String>,
    /// The request leaves test scope out: a dev-dependency is then no edge.
    pub(crate) exclude_tests: bool,
    /// The modules that the body of each `macro_rules!` of a crate names from the crate root.
    pub(crate) macro_uses: BTreeMap<(usize, String), Vec<(Edge, Reference)>>,
}

impl Builder {
    pub(crate) fn gap(&mut self, reason: &str, evidence: Option<&str>, module: &str) {
        let mut parts = vec![Part::Text(reason)];
        parts.extend(evidence.map(Part::Text));
        parts.push(Part::Text(module));
        let id = stable_id("UNKNOWN", &parts);
        let fact = GapFact::collection(reason, module);
        let record = Record::unknown(FactId::new(id.clone()), reason, evidence, module, fact);
        self.gaps.entry(id).or_insert(record);
    }

    pub(crate) fn cite(&mut self, rel: &str, site: &Site) -> String {
        let evidence = Evidence::at(rel, site.line, site.end_line, site.column, &site.excerpt);
        let id = evidence.id.clone();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    pub(crate) fn problem(&mut self, problem: &Problem, modules: &BTreeMap<&str, &str>) {
        let module = modules.get(problem.file.as_str()).copied().unwrap_or("");
        self.gap(&problem.reason, None, module);
    }

    /// The file fact of a module, with the evidence of its first line.
    pub(crate) fn file(&mut self, (rel, module): (&str, &str), blank: bool, cited: Evidence) {
        let evidence_id = cited.id.clone();
        self.evidence.insert(evidence_id.clone(), cited);
        self.files.push(FileFact {
            id: stable_id("FILE", &[Part::Text(module)]),
            rel_path: rel.to_owned(),
            module: module.to_owned(),
            package: package_of(module).to_owned(),
            blank,
            evidence_id,
        });
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
