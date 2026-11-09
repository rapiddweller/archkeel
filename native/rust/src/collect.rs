// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one request: a module for each file of a module tree, an import record for each
//! path that names another crate, and an UNKNOWN record for each place that the scan cannot read.
//!
//! This is slice 5b-1 of AD-335. The records are the crate edges. A path inside one crate gives
//! no record yet, so no rule about the modules of a crate can be decided from this collector.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_wire::identity::{evidence_id, package_of, stable_id, Part};
use archkeel_wire::records::{evidence_at, gap_record, GapKind};
use archkeel_wire::reply::{Evidence, Facts, FileFact, Provenance, Record, Target};
use archkeel_wire::request::Request;
use serde_json::{json, Map, Value};

use crate::crates::{discover, Problem, Workspace};
use crate::resolve::{classify, Named};
use crate::scan::{Reference, Site};
use crate::source::Source;
use crate::tree::{walk, Module, Walked};

pub const PROFILE: &str = "archkeel-rust-imports";
const SECTIONS: [&str; 2] = ["imports", "unknowns"];
const FEATURES: [&str; 1] = ["rust-crate-edges"];

#[derive(Default)]
struct Builder {
    gaps: BTreeMap<String, Record>,
    evidence: BTreeMap<String, Evidence>,
    files: Vec<FileFact>,
    imports: Vec<Record>,
    targets: Vec<Target>,
    seen: BTreeSet<(String, String, String)>,
}

/// Collect the facts of one request.
pub fn collect(request: &Request, provenance: Provenance) -> Facts {
    let mut source = Source::new(&request.root);
    let mut builder = Builder::default();
    let (scope, files) = list(&source, &request.roots, &mut builder);
    let workspace = discover(&mut source, &files, &request.namespace);
    let walked = walk(&mut source, &workspace);
    let modules: BTreeMap<&str, &str> = walked
        .modules
        .iter()
        .map(|module| (module.rel.as_str(), module.module.as_str()))
        .collect();
    for problem in workspace.problems.iter().chain(&walked.problems) {
        builder.problem(problem, &modules);
    }
    for module in &walked.modules {
        builder.module(&workspace, module);
    }
    let selected: Vec<String> = files
        .iter()
        .filter(|f| f.ends_with(".rs"))
        .cloned()
        .collect();
    for rel in selected.iter().filter(|rel| !walked.claimed.contains(*rel)) {
        let reason = format!("Source file is in no module tree: {rel}");
        builder.gap(&reason, None, "");
    }
    builder.finish(request, provenance, scope, selected, &walked, source)
}

/// The scope labels and all the files below the roots.
fn list(source: &Source, roots: &[String], builder: &mut Builder) -> (Vec<String>, Vec<String>) {
    let mut scope = Vec::new();
    let mut files = Vec::new();
    for root in roots {
        let root = root.trim_end_matches('/');
        if source.is_dir(root) {
            scope.push(format!("{root}/**"));
            files.extend(source.walk(root));
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
        let record = gap_record(reason, evidence, module, GapKind::Collection);
        self.gaps.entry(record.id.clone()).or_insert(record);
    }

    fn cite(&mut self, rel: &str, site: &Site) -> String {
        let evidence = evidence_at(rel, site.line, site.end_line, site.column, &site.excerpt);
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
        let file_evidence = evidence_id(&module.rel, line, line, column);
        self.evidence.insert(
            file_evidence.clone(),
            evidence_at(&module.rel, line, line, column, first),
        );
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
        for reference in &module.scan.references {
            if let Some(named) = classify(&reference.root, krate, &module.scan.declared) {
                self.import(workspace, module, reference, &named);
            }
        }
    }

    fn import(
        &mut self,
        workspace: &Workspace,
        module: &Module,
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
            .insert((module.module.clone(), key, reference.path.clone()))
        {
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(&module.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text("import"),
            ],
        );
        let evidence = self.cite(&module.rel, site);
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
            module,
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
        source: Source,
    ) -> Facts {
        let mut files = self.files;
        files.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
        let gaps: Vec<Record> = self.gaps.into_values().collect();
        let mut imports = self.imports;
        imports.sort_by(|a, b| a.id.cmp(&b.id));
        Facts {
            provenance,
            git_head: request.git_head.clone(),
            dirty: request.dirty.clone(),
            scope,
            sections: vec![(SECTIONS[0], imports), (SECTIONS[1], gaps.clone())],
            features: FEATURES.to_vec(),
            inputs: source.inputs(),
            files,
            imports: self.targets,
            selected_files: selected,
            files_read: walked.modules.len(),
            gaps,
            evidence: self.evidence.into_values().collect(),
        }
    }
}

fn record(
    module: &Module,
    reference: &Reference,
    identity: &str,
    evidence: String,
    target_module: &str,
    target_package: &str,
) -> Record {
    let mut subjects = vec![module.module.clone(), target_module.to_owned()];
    subjects.sort();
    subjects.dedup();
    let mut data = Map::new();
    data.insert("source_module".to_owned(), json!(module.module));
    data.insert(
        "source_package".to_owned(),
        json!(package_of(&module.module)),
    );
    data.insert("target_module".to_owned(), json!(target_module));
    data.insert("target_package".to_owned(), json!(target_package));
    data.insert("symbol".to_owned(), Value::Null);
    data.insert("binding".to_owned(), Value::Null);
    data.insert("symbols_known".to_owned(), json!(false));
    data.insert("specifier".to_owned(), json!(reference.path));
    data.insert("type_only".to_owned(), json!(false));
    data.insert("relative_level".to_owned(), json!(0));
    data.insert("under_type_checking".to_owned(), json!(false));
    data.insert("reexport".to_owned(), json!(false));
    data.insert("module_level_import".to_owned(), json!(true));
    Record {
        id: identity.to_owned(),
        evidence_class: "FACT",
        area: "source",
        kind: "import",
        title: format!("{} imports {}", module.module, reference.path),
        subjects,
        evidence_ids: vec![evidence],
        data,
    }
}

#[cfg(test)]
#[path = "collect_tests.rs"]
mod tests;
