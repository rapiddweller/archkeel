// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The test sources that a scan leaves out, and the gap of each import into one
//! (`explore_scope.ExcludedTests`).
//!
//! The walk has the rules of `Path.rglob("*")`: it lists a symlinked directory and does not enter
//! it. A path counts as a test as written and as resolved, so a link cannot hide a test source.

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::GapData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName};
use archkeel_facts::vocab::{Area, ResolutionDimension};
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_snapshot::paths::join;
use archkeel_snapshot::{Hidden, Snapshot};

use super::failures::record;
use crate::discover::is_test_source;
use crate::names::module_for;

/// `NO_PRODUCTION_SOURCE`.
const NO_PRODUCTION_SOURCE: &str = "No production source files in scope after the test exclusion";

#[derive(Default)]
pub struct Excluded {
    modules: HashSet<String>,
    prefixes: HashSet<String>,
    files: usize,
    /// The dangling `*.py` links of the walk. Python also judges the target of such a link
    /// (`resolve()` without a check); the native walk cannot read it, so each is a gap (L-30).
    dangling: Vec<String>,
    /// The minor version of the interpreter, for the module names (`names::module_for`).
    minor: u32,
}

impl Excluded {
    /// `ExcludedTests.find`.
    pub fn find(snapshot: &mut Snapshot, roots: &[String], namespace: &str, minor: u32) -> Self {
        let mut found = Self {
            minor,
            ..Self::default()
        };
        for root in roots {
            if !snapshot.is_dir(root) {
                continue;
            }
            let source_root = root.trim_end_matches('/');
            let mut pending = vec![source_root.to_owned()];
            while let Some(directory) = pending.pop() {
                found.walk(snapshot, (source_root, &directory), namespace, &mut pending);
            }
        }
        found
    }

    /// One directory of the walk: its test packages, its test files and the directories to enter.
    fn walk(
        &mut self,
        snapshot: &mut Snapshot,
        (source_root, directory): (&str, &str),
        namespace: &str,
        pending: &mut Vec<String>,
    ) {
        let (files, directories) = snapshot.entries(directory);
        for name in &directories {
            let rel = join(directory, name);
            self.directory(snapshot, &rel, namespace);
            if !snapshot.is_link(&rel) {
                pending.push(rel);
            }
        }
        let sources = files.iter().chain(&directories);
        for name in sources.filter(|name| name.ends_with(".py")) {
            let rel = join(directory, name);
            if let Some(real) = snapshot.real(&rel) {
                self.file(source_root, &[rel, real], namespace);
            }
        }
        // A dangling link: Python resolves it without a check, so it is judged as written.
        for entry in snapshot.hidden_entries(directory) {
            match entry {
                Hidden::Dangling(name) if name.ends_with(".py") => {
                    let rel = join(directory, &name);
                    self.file(source_root, std::slice::from_ref(&rel), namespace);
                    self.dangling.push(rel);
                }
                _ => {}
            }
        }
    }

    fn directory(&mut self, snapshot: &mut Snapshot, rel: &str, namespace: &str) {
        let Some(real) = snapshot.real(rel) else {
            return;
        };
        let init = format!("{rel}/__init__.py");
        if is_test_source(&init) || is_test_source(&format!("{real}/__init__.py")) {
            self.prefixes
                .extend(module_for(&init, namespace, self.minor));
        }
    }

    /// One `*.py` path as written and as resolved: a test source adds its module names.
    fn file(&mut self, source_root: &str, paths: &[String], namespace: &str) {
        if !paths.iter().any(|path| is_test_source(path)) {
            return;
        }
        self.files += 1;
        for path in paths {
            self.modules
                .extend(module_name(source_root, path, namespace, self.minor));
        }
    }

    /// `ExcludedTests.match`: the first name that is an excluded module or in an excluded package.
    fn matched<'n>(&self, names: &'n [String]) -> Option<&'n String> {
        names.iter().find(|name| {
            self.modules.contains(*name)
                || self.prefixes.iter().any(|prefix| {
                    name.as_str() == prefix
                        || name
                            .strip_prefix(prefix.as_str())
                            .is_some_and(|r| r.starts_with('.'))
                })
        })
    }

    /// `ExcludedTests.gaps`: the gap of each import into an excluded test source, and one gap when
    /// the exclusion left no source.
    pub fn gaps(
        &self,
        imports: &[Record<ImportFact>],
        bindings: &HashMap<&str, HashSet<String>>,
        no_source: bool,
    ) -> Vec<Record<GapFact>> {
        let mut gaps = Vec::new();
        for import in imports {
            let data = import.data.data();
            let target = data.target_module.as_str();
            let mut names = vec![target.to_owned()];
            let bound = |symbol: &str| bindings.get(target).is_some_and(|set| set.contains(symbol));
            let symbol = data.symbol.as_deref().filter(|symbol| *symbol != "*");
            if let Some(symbol) = symbol.filter(|symbol| !bound(symbol)) {
                names.push(format!("{target}.{symbol}"));
            }
            if let Some(excluded) = self.matched(&names) {
                gaps.push(import_gap(import, data.source_module.as_str(), excluded));
            }
        }
        if self.files > 0 && no_source {
            gaps.push(empty_scope_gap());
        }
        let mut dangling: Vec<&String> = self.dangling.iter().collect();
        dangling.sort();
        gaps.extend(dangling.into_iter().map(|rel| dangling_gap(rel)));
        gaps
    }
}

/// `_module_names`: the module name of a path, or its name under the source root.
fn module_name(source_root: &str, path: &str, namespace: &str, minor: u32) -> Option<String> {
    if let Some(name) = module_for(path, namespace, minor) {
        return Some(name);
    }
    let rest = path.strip_prefix(source_root)?.strip_prefix('/')?;
    let mut parts: Vec<&str> = rest.split('/').collect();
    let last = parts.pop()?;
    // `with_suffix("")` keeps the name of a dot file such as `.py`.
    parts.push(if last.len() > 3 {
        &last[..last.len() - 3]
    } else {
        last
    });
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }
    (!parts.is_empty()).then(|| parts.join("."))
}

fn import_gap(import: &Record<ImportFact>, source_module: &str, excluded: &str) -> Record<GapFact> {
    let parts = [
        Part::Text("excluded test import"),
        Part::Text(import.id.as_str()),
        Part::Text(excluded),
    ];
    let mut data = GapData::at("Import target is an excluded test source", source_module);
    data.source_module = Some(ModuleName::new(source_module));
    data.resolution_dimension = Some(ResolutionDimension::Imports);
    let head = (
        stable_id("UNKNOWN", &parts),
        Area::Source,
        format!("Production import targets excluded test source {excluded}"),
    );
    let fact_ids = vec![FactId::new(import.id.as_str())];
    let gap = GapFact::SourceResolutionGap(data);
    record(
        head,
        vec![source_module.to_owned()],
        import.evidence_ids.clone(),
        fact_ids,
        gap,
    )
}

/// L-30: the test exclusion cannot judge a dangling link, so the scope is never full.
fn dangling_gap(rel: &str) -> Record<GapFact> {
    let parts = [Part::Text("dangling test link"), Part::Text(rel)];
    let title = format!("Test exclusion cannot judge the dangling link {rel}");
    let head = (stable_id("UNKNOWN", &parts), Area::Source, title.clone());
    let gap = GapFact::CollectionGap(GapData::at(&title, ""));
    record(head, vec![rel.to_owned()], Vec::new(), Vec::new(), gap)
}

fn empty_scope_gap() -> Record<GapFact> {
    let parts = [Part::Text(NO_PRODUCTION_SOURCE), Part::Text("")];
    let head = (
        stable_id("UNKNOWN", &parts),
        Area::Source,
        NO_PRODUCTION_SOURCE.to_owned(),
    );
    let gap = GapFact::CollectionGap(GapData::at(NO_PRODUCTION_SOURCE, ""));
    record(head, Vec::new(), Vec::new(), Vec::new(), gap)
}

#[cfg(test)]
#[path = "excluded_tests.rs"]
mod tests;
