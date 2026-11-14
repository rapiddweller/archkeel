// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import facts of one request, as `analyzer/typescript/collect.py` collects them.
//!
//! The files, inputs, coverage, file evidence, import records and import targets follow the
//! Python collector. The records are one for each statement. The expansion of a statement into one
//! record for each named binding (`_named_imports`), the symbols, the calls, the references, the
//! bindings and the constructs follow in the same reply, with the capability `inner-uml-v1`
//! (AD-340). The script globals belong to a later phase. It invents no evidence.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::io::Write;

use archkeel_facts::envelope::Target;
use archkeel_facts::envelope::{Evidence, FileFact, Provenance};
use archkeel_facts::identity::module_identity;
use archkeel_facts::request::TypeScriptRequest;
use archkeel_facts::{GapFact, Record, Section};

use crate::collected::Facts;
#[cfg(any(test, feature = "dump"))]
use crate::collected::Records;
use crate::config::load_config;
use crate::kept::{Kept, Pending};
use crate::options::Resolution;
use crate::pytext::is_space;
use crate::records::write_reply;
#[cfg(any(test, feature = "dump"))]
use crate::records_lists::listed;
#[cfg(any(test, feature = "dump"))]
use crate::records_lists::records_of;
use crate::resolve::Resolver;
use crate::syntax::Parsers;
use crate::test_sources::{is_test_source, NO_PRODUCTION_SOURCE};
use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;

pub(crate) const FEATURES: [&str; 4] = [
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
];
// What the compiler's `trim()` removes (`collect._WHITESPACE`).
const COMPILER_SPACE: &str = " \t\n\u{b}\u{c}\r\u{a0}\u{1680}\u{2000}\u{2001}\u{2002}\u{2003}\u{2004}\u{2005}\u{2006}\u{2007}\u{2008}\u{2009}\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}\u{feff}";

/// The reason of a project source under the scan roots that the TSConfig does not select.
pub(crate) const UNSELECTED: &str =
    "Source file under the scan roots is not selected by the TSConfig";

enum GapKind {
    Collection,
    Resolution,
}

struct Collection<'a> {
    request: &'a TypeScriptRequest,
    namespace: &'a str,
    roots: Vec<String>,
    snapshot: Snapshot,
    resolver: Resolver,
    parsers: Parsers,
    /// A bundler is assumed to decide module loading, and the settings allow it.
    bundler: bool,
    /// Every file to read, in discovery order; a file added while walking is walked too.
    queue: Vec<String>,
    queued: HashSet<String>,
    gaps: BTreeMap<String, Record<GapFact>>,
    /// What reaches an installed-package directory other than a `node_modules` search (AD-488).
    reach: BTreeSet<String>,
    evidence: BTreeMap<String, Evidence>,
    files: Vec<FileFact>,
    imports: Vec<crate::collected::ImportRecord>,
    targets: Vec<Target>,
    read: usize,
    kept: BTreeMap<String, Kept>,
    order: Vec<String>,
    sites: HashMap<String, crate::source::FileSite>,
    /// The script host and the vendored libraries of the project.
    script: crate::script_environment::ScriptEnvironment,
    /// `script_pending_effects` of the files: writes that no publication bounds.
    pending_effects: Vec<(String, crate::source::Span)>,
}

/// The reply of one request, written into `out`: the imports, the symbols, the calls, the
/// references, the bindings and the constructs, with the capability `inner-uml-v1` (AD-340, PR
/// 4.3a-3d). The compressed bytes go to `out` as they are made.
pub fn reply(
    request: &TypeScriptRequest,
    provenance: Provenance,
    version: archkeel_wire::protocol::Version,
    out: impl Write,
) -> Result<(), String> {
    let (facts, pending) = gather(request, provenance);
    let done = write_reply(version, facts, &pending, out);
    drop(pending);
    done
}

/// The same facts with every section in a list, for the unit tests: the producer of `reply`.
#[cfg(test)]
pub(crate) fn collect(request: &TypeScriptRequest, provenance: Provenance) -> Facts {
    let (facts, pending) = gather(request, provenance);
    listed(facts, &pending).unwrap().0
}

/// The facts as `collect` gives them and the records by the names of the tests and the dump.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn records(
    request: &TypeScriptRequest,
    provenance: Provenance,
) -> Result<(Facts, Records), String> {
    let (facts, pending) = gather(request, provenance);
    let (facts, touched) = listed(facts, &pending)?;
    let records = records_of(&facts, touched);
    Ok((facts, records))
}

pub(crate) fn gather(request: &TypeScriptRequest, provenance: Provenance) -> (Facts, Pending) {
    let roots: Vec<String> = request
        .scope
        .roots
        .iter()
        .map(|root| join(".", root))
        .collect();
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let config = load_config(&mut snapshot, &request.resolver.tsconfig, &roots);
    let resolver = Resolver::new(config.options, config.partial);
    let bundler = request.resolver.bundler
        && resolver.blocked.is_none()
        && resolver.options.resolution() == Resolution::Bundler;
    let partial = config.partial;
    let reach = config.reach;
    let script = config.script;
    let listed = config.files;
    let mut collection = Collection {
        request,
        namespace: &request.scope.namespace,
        roots: roots.clone(),
        snapshot,
        resolver,
        parsers: Parsers::new(),
        bundler,
        queue: Vec::new(),
        queued: HashSet::new(),
        gaps: BTreeMap::new(),
        reach: reach.into_iter().collect(),
        evidence: BTreeMap::new(),
        files: Vec::new(),
        imports: Vec::new(),
        targets: Vec::new(),
        read: 0,
        kept: BTreeMap::new(),
        order: Vec::new(),
        sites: HashMap::new(),
        script,
        pending_effects: Vec::new(),
    };
    collection.queue = listed
        .iter()
        .filter(|rel| !collection.excluded_test(rel))
        .cloned()
        .collect();
    collection.queued = collection.queue.iter().cloned().collect();
    if request.excludes_test_sources() && !listed.is_empty() && collection.queue.is_empty() {
        collection
            .snapshot
            .problems
            .insert(NO_PRODUCTION_SOURCE.to_owned());
    }
    if request.resolver.bundler && !collection.bundler && collection.resolver.blocked.is_none() {
        collection.gap(
            "Bundler mode requires moduleResolution bundler",
            None,
            "",
            GapKind::Resolution,
        );
    }
    let mut index = 0;
    while index < collection.queue.len() {
        let rel = collection.queue[index].clone();
        collection.file(&rel);
        index += 1;
    }
    collection.unselected();
    let (script, dependency_scope) = collection.script_dependencies(partial);
    let problems: Vec<String> = collection.snapshot.problems.iter().cloned().collect();
    for problem in problems {
        collection.gap(&problem, None, "", GapKind::Collection);
    }
    let scope = roots
        .iter()
        .map(|root| {
            if collection.snapshot.is_dir(root) {
                format!("{root}/**")
            } else {
                root.clone()
            }
        })
        .collect();
    let mut files = collection.files;
    files.sort_by(|left, right| left.rel_path.cmp(&right.rel_path));
    let mut selected_files = collection.queue;
    selected_files.sort();
    let gaps: Vec<Record<GapFact>> = collection.gaps.into_values().collect();
    let mut imports = collection.imports;
    imports.sort_by(|left, right| left.id.cmp(&right.id));
    let mut features = FEATURES.to_vec();
    // The records of the inner-UML capability come after the four features of the imports.
    features.insert(FEATURES.len(), "inner-uml-v1");
    if collection.bundler {
        features.push("bundler-mode-v1");
    }
    let pending = Pending {
        kept: collection.kept,
        order: collection.order,
        sites: collection.sites,
        partial,
        script,
        dependency_scope,
    };
    let facts = Facts {
        provenance,
        git_head: request.snapshot.git_head.clone(),
        dirty: serde_json::to_value(&request.snapshot.dirty).unwrap_or_default(),
        scope,
        sections: vec![Section::Imports(imports), Section::Unknowns(gaps.clone())],
        features,
        constructs: Vec::new(),
        inputs: collection.snapshot.inputs(),
        files,
        imports: collection.targets,
        selected_files,
        files_read: collection.read,
        gaps,
        evidence: collection.evidence.into_values().collect(),
    };
    (facts, pending)
}

impl Collection<'_> {
    /// A 9.0.0 request removes test sources, by their path or by their real path.
    fn excluded_test(&mut self, rel: &str) -> bool {
        self.request.excludes_test_sources()
            && (is_test_source(rel)
                || self
                    .snapshot
                    .real(rel)
                    .is_some_and(|real| is_test_source(&real)))
    }

    /// AD-488: each project source under the scan roots that the collection did not read is a
    /// coverage gap. The TSConfig can drop a file that holds an import, so silence could pass a
    /// rule. A test source that a 9.0.0 request removes is not a gap (AD-313). `reach` makes a
    /// package of an installed-package directory project source.
    fn unselected(&mut self) {
        let roots = self.roots.clone();
        let reach = std::mem::take(&mut self.reach);
        for rel in crate::unselected::project_sources(&mut self.snapshot, &roots, &reach) {
            if self.queued.contains(&rel) || self.excluded_test(&rel) {
                continue;
            }
            let module = module_identity(self.namespace, &rel).unwrap_or_default();
            let reason = format!("{UNSELECTED}: {rel}");
            self.gap(&reason, None, &module, GapKind::Collection);
        }
    }

    fn file(&mut self, rel: &str) {
        let Some(content) = self.snapshot.read(rel) else {
            let reason = self
                .snapshot
                .size_gap(rel)
                .unwrap_or_else(|| format!("Unreadable selected source: {rel}"));
            self.gap(&reason, None, "", GapKind::Collection);
            return;
        };
        let Ok(module) = module_identity(self.namespace, rel) else {
            self.gap(
                &format!("Source path has no module identity: {rel}"),
                None,
                "",
                GapKind::Collection,
            );
            return;
        };
        self.read += 1;
        self.snapshot.select(rel);
        let text = String::from_utf8_lossy(&content);
        let directory = match archkeel_snapshot::paths::dirname(rel) {
            "" => ".",
            directory => directory,
        };
        for name in crate::unselected::reference_types(&text) {
            let candidates = crate::unselected::type_candidates(directory, &name);
            self.reach.extend(candidates);
        }
        let evidence = self.file_evidence(rel, &text);
        self.files.push(FileFact::of(
            (rel, &module),
            text.trim_matches(|c| COMPILER_SPACE.contains(c)).is_empty(),
            evidence.clone(),
        ));
        self.references(rel, &module, &evidence, &text);
    }

    /// `source_records.file_evidence`: line 1 shows the file; an empty first line cites line 0.
    fn file_evidence(&mut self, rel: &str, text: &str) -> String {
        let first = text
            .split('\n')
            .next()
            .unwrap_or("")
            .trim_end_matches(is_space);
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        let evidence = Evidence::at(rel, line, line, column, first);
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    /// `collect._cite`: file one source location as evidence.
    fn cite(&mut self, rel: &str, span: &crate::source::Span) -> String {
        let evidence = Evidence::at(rel, span.line, span.end_line, span.column, &span.excerpt);
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    /// `collect._gap`: one UNKNOWN record; the same reason, evidence and module give one record.
    fn gap(&mut self, reason: &str, evidence: Option<&str>, module: &str, kind: GapKind) {
        let fact = match kind {
            GapKind::Collection => GapFact::collection(reason, module),
            GapKind::Resolution => GapFact::resolution(reason, module),
        };
        let (id, record) = Record::unknown_gap(reason, evidence, module, fact);
        self.gaps.entry(id).or_insert(record);
    }
}

#[path = "import_record.rs"]
mod import_record;

#[path = "import_target.rs"]
mod import_target;

#[path = "imports.rs"]
mod imports;

#[path = "script_run.rs"]
mod script_run;

#[cfg(test)]
#[path = "collect_tests.rs"]
mod tests;
