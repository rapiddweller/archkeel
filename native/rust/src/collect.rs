// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one request: a module for each file of a module tree, an import record for each
//! path that names another crate, and an UNKNOWN record for each place that the scan cannot read.
//!
//! This is slice 5b-1 of AD-335. The records are the crate edges. A path inside one crate gives
//! no record yet, so no rule about the modules of a crate can be decided from this collector.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_wire::identity::{package_of, stable_id, Part};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::{Evidence, FileFact, Provenance, Target};
use archkeel_wire::request::Request;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};

use crate::crates::{discover, Crate, Problem, Workspace};
use crate::manifest::{line_of, Kind};
use crate::resolve::{classify, Found, Named};
use crate::scan::{Reference, Site};
use crate::source::read_text;
use crate::source::walk as list_files;
use crate::test_scope::NO_PRODUCTION_SOURCE;
use crate::tree::{walk, Module, Walked};
use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;

pub const PROFILE: &str = "archkeel-rust-imports";
const SECTIONS: [&str; 2] = ["imports", "unknowns"];
const FEATURES: [&str; 1] = ["rust-crate-edges"];

/// Where an edge starts: the module, the file that cites it and the kind of the evidence. A
/// declared dependency starts in the main module of its crate and cites its manifest.
#[derive(Clone, Copy)]
struct Origin<'a> {
    module: &'a str,
    rel: &'a str,
    form: &'a str,
}

impl<'a> Origin<'a> {
    fn of(module: &'a Module) -> Self {
        Self {
            module: &module.module,
            rel: &module.rel,
            form: "import",
        }
    }
}

/// The facts of one request, as the typed records of `archkeel-facts` (AD-345) and the small lists.
/// `encode` writes the gaps once: they are the section `unknowns` and the gaps of the coverage.
pub struct Collected {
    pub head: Head,
    pub imports: Vec<Record<ImportFact>>,
    pub gaps: Vec<Record<GapFact>>,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    pub evidence: Vec<Evidence>,
}

impl Collected {
    /// The compressed reply for `version`.
    pub fn encode(self, version: Version) -> Result<Vec<u8>, String> {
        let Self {
            head,
            imports,
            gaps,
            selected_files,
            files_read,
            evidence,
        } = self;
        let mut bytes = Vec::new();
        encode_stream(version, head, &mut bytes, |writer| {
            writer.write_typed_section("imports", |emit| imports.iter().for_each(emit))?;
            writer.write_typed_section("unknowns", |emit| gaps.iter().for_each(emit))?;
            Ok(Tail {
                selected_files,
                files_read,
                gaps,
                evidence,
            })
        })?;
        Ok(bytes)
    }
}

#[derive(Default)]
struct Builder {
    gaps: BTreeMap<String, Record<GapFact>>,
    evidence: BTreeMap<String, Evidence>,
    files: Vec<FileFact>,
    imports: Vec<Record<ImportFact>>,
    targets: Vec<Target>,
    seen: BTreeSet<(String, String, String)>,
    /// The manifests of the crates: each is a module that holds the declared dependencies.
    manifests: Vec<String>,
    /// The request leaves test scope out: a dev-dependency is then no edge.
    exclude_tests: bool,
}

/// Collect the facts of one request.
pub fn collect(request: &Request, provenance: Provenance) -> Collected {
    let mut source = Snapshot::new(&request.root);
    let mut builder = Builder {
        exclude_tests: request.exclude_test_sources,
        ..Builder::default()
    };
    let (scope, files) = list(&mut source, &request.roots, &mut builder);
    let workspace = discover(&mut source, &files, &request.namespace);
    let walked = walk(&mut source, &workspace, request.exclude_test_sources);
    let modules: BTreeMap<&str, &str> = walked
        .modules
        .iter()
        .map(|module| (module.rel.as_str(), module.module.as_str()))
        .collect();
    for problem in source.problems.clone() {
        builder.gap(&problem, None, "");
    }
    for problem in workspace.problems.iter().chain(&walked.problems) {
        builder.problem(problem, &modules);
    }
    for module in &walked.modules {
        builder.module(&workspace, module);
    }
    let taken: BTreeSet<&str> = modules.values().copied().collect();
    builder.declared(&workspace, &request.namespace, &taken, &mut source);
    let mut selected: Vec<String> = files
        .iter()
        .filter(|f| f.ends_with(".rs"))
        .cloned()
        .collect();
    let listed_rust = !selected.is_empty();
    selected.retain(|rel| !walked.is_excluded(rel));
    if listed_rust && selected.is_empty() {
        builder.gap(NO_PRODUCTION_SOURCE, None, "");
    }
    for rel in selected.iter().filter(|rel| !walked.claimed.contains(*rel)) {
        let reason = format!("Source file is in no module tree: {rel}");
        builder.gap(&reason, None, "");
    }
    selected.extend(builder.manifests.iter().cloned());
    selected.sort();
    builder.finish(request, provenance, scope, selected, &walked, source)
}

/// The scope labels and all the files below the roots.
fn list(
    source: &mut Snapshot,
    roots: &[String],
    builder: &mut Builder,
) -> (Vec<String>, Vec<String>) {
    let mut scope = Vec::new();
    let mut files = Vec::new();
    for root in roots {
        let root = root.trim_end_matches('/');
        if source.is_dir(root) {
            scope.push(format!("{root}/**"));
            files.extend(list_files(source, root));
        } else {
            scope.push(root.to_owned());
            builder.gap(&format!("Scan root is not a directory: {root}"), None, "");
        }
    }
    files.sort();
    files.dedup();
    (scope, files)
}

impl Builder {
    fn gap(&mut self, reason: &str, evidence: Option<&str>, module: &str) {
        let mut parts = vec![Part::Text(reason)];
        parts.extend(evidence.map(Part::Text));
        parts.push(Part::Text(module));
        let id = stable_id("UNKNOWN", &parts);
        let fact = GapFact::collection(reason, module);
        let record = Record::unknown(FactId::new(id.clone()), reason, evidence, module, fact);
        self.gaps.entry(id).or_insert(record);
    }

    fn cite(&mut self, rel: &str, site: &Site) -> String {
        let evidence = Evidence::at(rel, site.line, site.end_line, site.column, &site.excerpt);
        let id = evidence.id.clone();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    fn problem(&mut self, problem: &Problem, modules: &BTreeMap<&str, &str>) {
        let module = modules.get(problem.file.as_str()).copied().unwrap_or("");
        self.gap(&problem.reason, None, module);
    }

    fn module(&mut self, workspace: &Workspace, module: &Module) {
        let first = module.first_line.as_str();
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        let cited = Evidence::at(&module.rel, line, line, column, first);
        let file_evidence = cited.id.clone();
        self.evidence.insert(file_evidence.clone(), cited);
        self.files.push(FileFact {
            id: stable_id("FILE", &[Part::Text(&module.module)]),
            rel_path: module.rel.clone(),
            module: module.module.clone(),
            package: package_of(&module.module).to_owned(),
            blank: module.blank,
            evidence_id: file_evidence,
        });
        self.edges(workspace, module);
        for concern in &module.scan.concerns {
            let evidence = self.cite(&module.rel, &concern.site);
            self.gap(&concern.reason, Some(&evidence), &module.module);
        }
    }

    fn edges(&mut self, workspace: &Workspace, module: &Module) {
        let Some(krate) = workspace.crates.get(module.crate_index) else {
            return;
        };
        let mut covered = BTreeSet::new();
        for reference in &module.scan.references {
            let found = classify(
                &reference.root,
                krate,
                &module.scan.shadows,
                reference.absolute,
            );
            if found.is_some() {
                covered.insert(reference.root.clone());
            }
            match found {
                Some(Found::Edge(named)) => {
                    self.import(workspace, Origin::of(module), reference, &named);
                }
                Some(Found::Shadowed) => {
                    let reason = format!("A local name equals a crate name: {}", reference.root);
                    let evidence = self.cite(&module.rel, &reference.site);
                    self.gap(&reason, Some(&evidence), &module.module);
                }
                None => {}
            }
        }
        self.net(krate, module, &covered);
    }

    /// The safety net: a reachable crate name that the file writes, and that no edge explains.
    fn net(&mut self, krate: &Crate, module: &Module, covered: &BTreeSet<String>) {
        let none = BTreeSet::new();
        for name in &module.scan.mentioned {
            if covered.contains(name) || classify(name, krate, &none, false).is_none() {
                continue;
            }
            let reason =
                format!("The crate name {name} appears in a place the collector does not read");
            self.gap(&reason, None, &module.module);
        }
    }

    /// A dependency that a manifest declares is an edge of its crate, in the section that it is
    /// declared in. Source can hide a use (a macro, a generated token), but it cannot use a crate
    /// that the manifest does not declare. The edge starts in the main module of the crate; the
    /// kind of the section is in the text of the specifier, until module scope exists (5b-2).
    fn declared(
        &mut self,
        workspace: &Workspace,
        namespace: &str,
        taken: &BTreeSet<&str>,
        source: &mut Snapshot,
    ) {
        for krate in &workspace.crates {
            let rel = join(&krate.dir, "Cargo.toml");
            let Ok(text) = read_text(source, &rel) else {
                continue;
            };
            source.select(&rel);
            let mut module = format!("{namespace}.{}.cargo_toml", krate.ident);
            while taken.contains(module.as_str()) {
                module.push('_');
            }
            let first = text.lines().next().unwrap_or("").trim_end();
            let cited = Evidence::at(&rel, 1, 1, 0, first);
            let file_evidence = cited.id.clone();
            self.evidence.insert(file_evidence.clone(), cited);
            self.files.push(FileFact {
                id: stable_id("FILE", &[Part::Text(&module)]),
                rel_path: rel.clone(),
                module: module.clone(),
                package: package_of(&module).to_owned(),
                blank: text.trim().is_empty(),
                evidence_id: file_evidence,
            });
            self.manifests.push(rel.clone());
            self.declared_edges(workspace, krate, &module, &text);
        }
    }

    /// The edge of each dependency that the manifest of `krate` declares.
    fn declared_edges(&mut self, workspace: &Workspace, krate: &Crate, module: &str, text: &str) {
        let rel = join(&krate.dir, "Cargo.toml");
        let exclude = self.exclude_tests;
        let others = krate
            .manifest
            .declared
            .iter()
            .filter(|dependency| dependency.package != krate.ident)
            .filter(|dependency| !(exclude && dependency.kind == Kind::Dev));
        for dependency in others {
            let (line, excerpt) = line_of(text, dependency.kind, &dependency.key);
            let reference = Reference {
                root: dependency.package.clone(),
                path: format!("{}: {}", dependency.kind.section(), dependency.key),
                site: Site {
                    line,
                    end_line: line,
                    column: 0,
                    excerpt,
                },
                absolute: true,
                ..Reference::default()
            };
            let from = Origin {
                module,
                rel: &rel,
                form: "declared",
            };
            let named = Named::Package(dependency.package.clone());
            self.import(workspace, from, &reference, &named);
        }
    }

    fn import(
        &mut self,
        workspace: &Workspace,
        from: Origin<'_>,
        reference: &Reference,
        named: &Named,
    ) {
        let (target_module, key) = match named {
            Named::Sysroot(name) => (name.clone(), format!("sysroot:{name}")),
            Named::Package(package) => (package.clone(), format!("package:{package}")),
        };
        // One record for each distinct path of a file; the first use is its evidence.
        if !self
            .seen
            .insert((from.module.to_owned(), key, reference.path.clone()))
        {
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(from.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text(from.form),
            ],
        );
        let evidence = self.cite(from.rel, site);
        let import_id = identity.clone();
        let (target, target_module) = match named {
            Named::Sysroot(name) => (
                Target::Builtin {
                    import_id,
                    name: name.clone(),
                },
                target_module,
            ),
            Named::Package(package) => match workspace
                .crates
                .iter()
                .find(|c| &c.ident == package)
                .and_then(|c| c.primary.as_ref())
            {
                Some(root) => (
                    Target::Local {
                        import_id,
                        module: root.module.clone(),
                        file: root.rel.clone(),
                        runtime_file: Some(root.rel.clone()),
                        declaration_file: None,
                    },
                    root.module.clone(),
                ),
                None => (
                    Target::External {
                        import_id,
                        package: package.clone(),
                    },
                    target_module,
                ),
            },
        };
        let target_package = match &target {
            Target::Local { module, .. } => package_of(module).to_owned(),
            _ => target_module.clone(),
        };
        self.targets.push(target);
        self.imports.push(record(
            from.module,
            reference,
            &identity,
            evidence,
            &target_module,
            &target_package,
        ));
    }

    fn finish(
        self,
        request: &Request,
        provenance: Provenance,
        scope: Vec<String>,
        selected: Vec<String>,
        walked: &Walked,
        source: Snapshot,
    ) -> Collected {
        let mut files = self.files;
        files.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
        let mut imports = self.imports;
        imports.sort_by(|a, b| a.id.cmp(&b.id));
        let head = Head {
            provenance,
            git_head: request.git_head.clone(),
            dirty: request.dirty.clone(),
            scope,
            sections: SECTIONS.to_vec(),
            features: FEATURES.to_vec(),
            constructs: Vec::new(),
            inputs: source.inputs(),
            files,
            imports: self.targets,
        };
        Collected {
            head,
            imports,
            gaps: self.gaps.into_values().collect(),
            selected_files: selected,
            files_read: walked.modules.len() + self.manifests.len(),
            evidence: self.evidence.into_values().collect(),
        }
    }
}

/// The import record of one path that names another crate.
fn record(
    module: &str,
    reference: &Reference,
    identity: &str,
    evidence: String,
    target_module: &str,
    target_package: &str,
) -> Record<ImportFact> {
    let mut subjects = vec![module.to_owned(), target_module.to_owned()];
    subjects.sort();
    subjects.dedup();
    let data = ImportData {
        source_module: ModuleName::new(module),
        source_package: PackageName::new(package_of(module)),
        target_module: ModuleName::new(target_module),
        target_package: PackageName::new(target_package),
        specifier: Some(reference.path.clone()),
        module_level_import: true,
        ..ImportData::statement()
    };
    Record {
        id: FactId::new(identity),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{module} imports {}", reference.path),
        subjects,
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data: ImportFact::Import(data),
    }
}

#[cfg(test)]
#[path = "collect_tests.rs"]
mod tests;
