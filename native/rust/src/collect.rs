// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one request: a module for each file of a module tree, an import record for each
//! path that names another crate, and an UNKNOWN record for each place that the scan cannot read.
//!
//! This is slice 5b-1 of AD-335. The records are the crate edges. A path inside one crate gives
//! no record yet, so no rule about the modules of a crate can be decided from this collector.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::envelope::Provenance;
use archkeel_facts::request::RustRequest;
use archkeel_snapshot::Snapshot;

use crate::builder::Builder;
use crate::crates::discover;
use crate::modules::index;
use crate::reply::Collected;
use crate::source::walk as list_files;
use crate::test_scope::NO_PRODUCTION_SOURCE;
use crate::tree::walk;

/// Collect the facts of one request.
pub fn collect(request: &RustRequest, provenance: Provenance) -> Collected {
    let mut source = Snapshot::new(&request.snapshot.root);
    let mut builder = Builder {
        exclude_tests: request.excludes_test_sources(),
        ..Builder::default()
    };
    let (scope, files) = list(&mut source, &request.scope.roots, &mut builder);
    let workspace = discover(&mut source, &files, &request.scope.namespace);
    let walked = walk(&mut source, &workspace, request.excludes_test_sources());
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
    let modules_index = index(&workspace, &walked.modules);
    for module in &walked.modules {
        builder.module(&workspace, &modules_index, module);
    }
    builder.macro_calls(&modules_index, &walked.modules);
    builder.impl_members(&workspace, &modules_index, &walked.modules);
    let taken: BTreeSet<&str> = modules.values().copied().collect();
    builder.declared(&workspace, &request.scope.namespace, &taken, &mut source);
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

#[cfg(test)]
#[path = "collect_tests.rs"]
pub(crate) mod tests;
