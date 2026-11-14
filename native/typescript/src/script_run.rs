// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The script analysis as a step of the collection: it reads every file that the collection has
//! kept, and adds its import records, targets and gaps to the collection (`_script_dependencies`).

use std::collections::HashSet;

use archkeel_snapshot::paths::{join, within};
use archkeel_snapshot::Entry;

use super::{Collection, GapKind};
use crate::script_deps::Run;
use crate::script_project::{Project, Write, WriteIndex};
use crate::script_records::{ScriptFacts, UNBOUNDED_EFFECT};
use crate::script_vendor::{self, Setting};
use crate::source::Span;
use crate::std_globals::standard_globals;

impl Collection<'_> {
    /// `_script_dependencies` and the runtime effects: run the analysis, take what it found into
    /// the collection, and give the facts that the later records read.
    pub(super) fn script_dependencies(&mut self, partial: bool) -> (ScriptFacts, bool) {
        let kept = std::mem::take(&mut self.kept);
        let order = std::mem::take(&mut self.order);
        let options = self.resolver.options.clone();
        let setting = Setting {
            environment: &self.script,
            options: &options,
            partial,
        };
        let vendors = script_vendor::read(&mut self.snapshot, &mut self.parsers, &setting);
        let project = Project::new(&order, &kept, options.scripts_are_global());
        let dependency_scope = project
            .files
            .iter()
            .any(|(_, file)| file.script.dependency_scope);
        let all: Vec<Write> = Run::global_writes(&project);
        let mut seen = HashSet::new();
        let unique = kept_source_writes(&project)
            .into_iter()
            .filter(|write| seen.insert(*write));
        let source_writes = WriteIndex::new(unique);
        let direct = self.direct_scope(&project, partial);
        let mut run = Run {
            project: &project,
            partial,
            direct,
            standard: standard_globals(&options),
            vendors,
            writes: WriteIndex::new(all.iter().copied()),
            source_writes,
            source_set: seen,
            sink: Default::default(),
        };
        let import_sites: HashSet<_> = self
            .sites
            .values()
            .map(crate::source::FileSite::key)
            .collect();
        run.analyze(&import_sites);
        let pending = std::mem::take(&mut self.pending_effects);
        run.effects(&all, pending);
        let sink = run.sink;
        self.kept = kept;
        self.order = order;
        self.take(sink, dependency_scope)
    }

    /// Close the snapshot boundary before a new source-only publication can resolve a use.
    fn direct_scope(&mut self, project: &Project<'_>, partial: bool) -> bool {
        let options = &self.resolver.options;
        if partial || !self.script.classic_browser || self.request.resolver.bundler
            || options.resolution() == crate::options::Resolution::Bundler
            || options.module_detection != Some(crate::options::Detection::Legacy)
            || !options.scripts_are_global() || project.any_error
            || project.files.iter().any(|(_, file)| file.script.script.direct.is_none())
        {
            return false;
        }
        let mut pending = vec![".".to_owned()];
        while let Some(directory) = pending.pop() {
            let Some(entries) = self.snapshot.listing(&directory) else { return false; };
            for (name, kind) in entries {
                let path = join(&directory, &name);
                if path == ".git" { continue; }
                match kind {
                    Entry::Directory if name != "node_modules" => pending.push(path),
                    Entry::File if self.direct_input(&path, project) => {}
                    _ => return false,
                }
            }
        }
        self.snapshot.problems.is_empty()
    }

    fn direct_input(&self, path: &str, project: &Project<'_>) -> bool {
        if project.index.contains_key(path) {
            return self.roots.iter().any(|root| within(root, path));
        }
        path == self.request.resolver.tsconfig || path == "archkeel.toml"
            || path == "architecture-contract.json" || path.ends_with(".md") || path.ends_with(".txt")
    }

    /// Take the imports, targets and gaps of the analysis into the collection.
    fn take(
        &mut self,
        sink: crate::script_records::Sink,
        dependency_scope: bool,
    ) -> (ScriptFacts, bool) {
        self.imports.extend(sink.imports);
        self.targets.extend(sink.targets);
        for (id, record) in sink.gaps {
            self.gaps.entry(id).or_insert(record);
        }
        (sink.facts, dependency_scope)
    }

    /// The part of `_file` that reports the writes of a script that nothing can bound: a gap for a
    /// write that the source writes name, a pending effect for the others.
    pub(super) fn script_file_effects(
        &mut self,
        rel: &str,
        module: &str,
        file: &crate::kept_script::ScriptFile,
    ) {
        if !file.script_mode {
            return;
        }
        // The unnamed source writes, once: a search of the list for each write is quadratic.
        let unnamed: HashSet<&Span> = file
            .script
            .source_writes
            .iter()
            .filter(|(name, _)| name.is_none())
            .map(|(_, span)| span)
            .collect();
        for (name, span) in &file.script.writes {
            if name.is_some() {
                continue;
            }
            if unnamed.contains(span) {
                let evidence = self.cite(rel, span);
                self.gap(
                    UNBOUNDED_EFFECT,
                    Some(&evidence),
                    module,
                    GapKind::Resolution,
                );
            } else {
                self.pending_effects.push((rel.to_owned(), span.clone()));
            }
        }
    }
}

/// `(rel, name, span)` of the source writes of every file.
fn kept_source_writes<'a>(project: &Project<'a>) -> Vec<Write<'a>> {
    let mut found = Vec::new();
    for (rel, file) in &project.files {
        let listed = file.script.script.source_writes.iter();
        found.extend(listed.map(|(name, span)| (*rel, name.as_deref(), span)));
    }
    found
}
