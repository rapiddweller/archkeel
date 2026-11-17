// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Installed-package closure and computed-import reachability (AD-798, #1529, #1749, AD-812).

use std::collections::{HashMap, HashSet};

use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

use super::preloads;
#[path = "package_closure_names.rs"]
mod names;
use crate::collection::{Collection, GapKind};
use crate::installed::installed;
use crate::manifest::Lookup;
use crate::options::Options;
use crate::parse::parse_for;
use crate::references::{Form, Reference};
use crate::source_input::{
    classify_file, classify_specifier, skipped_directory, ModuleFormat, SourceKind,
};
use crate::{resolve::format_of, resolver::Resolver};
use names::{package_names, quoted_after, unknown_loader};

/// The most installed files that one run reads. A larger closure is a gap of each importer.
const BUDGET: usize = 20_000;

/// What one installed file leads to.
#[derive(Default)]
struct Step {
    /// The installed source files that it imports.
    installed: Vec<String>,
    /// The first project file that it imports, or why the file can reach one unseen.
    project: Option<String>,
}

/// The installed files of the closure: who imports each one, and the reach of project source of
/// each file, with the file of the step and the project file.
#[derive(Default)]
pub(super) struct Graph {
    importers: HashMap<String, Vec<String>>,
    pub(super) reached: HashMap<String, (String, String)>,
    /// Installed files in closure walk order.
    pub(super) files: Vec<String>,
}

impl Collection<'_> {
    /// The gap of each module whose import of an installed package reaches project source.
    pub(crate) fn package_closure(&mut self) {
        let entries = std::mem::take(&mut self.installed);
        if let Some(graph) = self.closure_graph(&entries) {
            let reached = reach_back(graph);
            self.closure_gaps(&entries, |file| reached.get(file).cloned());
        } else {
            let reason = format!("more than {BUDGET} installed files");
            self.closure_gaps(&entries, |_| Some((String::new(), reason.clone())));
        }
        self.tool_preloads();
    }

    /// Read the closure and writes of each preload that the repository names.
    fn tool_preloads(&mut self) {
        let named = self.named_preloads();
        let mut files = Vec::new();
        for preload in named {
            let Some(entries) = self.preload_entries(&preload.file, &preload.name, preload.mode)
            else {
                let reason = format!(
                    "Preload {} named in {}:{} is no installed package that the scan can read",
                    preload.name, preload.file, preload.line
                );
                self.gap(&reason, None, "", GapKind::Collection);
                continue;
            };
            let entries: Vec<(String, String, String)> = entries
                .into_iter()
                .map(|file| (file, String::new(), String::new()))
                .collect();
            let Some(graph) = self.closure_graph(&entries) else {
                let reason = format!(
                    "Preload {} named in {}:{} has a closure of more than 20000 installed files",
                    preload.name, preload.file, preload.line
                );
                self.gap(&reason, None, "", GapKind::Collection);
                continue;
            };
            if !std::collections::HashMap::is_empty(&graph.reached) {
                let reason = format!(
                    "Preload {} named in {}:{} has an incomplete closure: it can reach project \
                     source, has an unknown loader target, or has an unreadable file",
                    preload.name, preload.file, preload.line
                );
                self.gap(&reason, None, "", GapKind::Resolution);
            }
            let closure_files = graph.files;
            let module = closure_files.iter().any(|file| self.reaches_module(file));
            for file in &closure_files {
                self.loader_patch(&preload, file, module);
            }
            Vec::extend(&mut files, closure_files);
        }
        files.sort();
        files.dedup();
        self.preload_files = files;
    }

    /// Each preload name of each repository config, with its source location.
    fn named_preloads(&mut self) -> Vec<preloads::Named> {
        let mut found = Vec::new();
        let mut pending = vec![".".to_owned()];
        while let Some(directory) = Vec::pop(&mut pending) {
            let (files, children) = self.snapshot.entries(&directory);
            for name in files {
                found.extend(
                    self.read_named_preload(&directory, &name)
                        .unwrap_or_default(),
                );
            }
            pending.extend(
                children
                    .into_iter()
                    .filter(|name| !skipped_directory(name))
                    .map(|name| join(&directory, &name)),
            );
        }
        found
    }

    /// Read one repository data file that names preload entries.
    fn read_named_preload(&mut self, directory: &str, name: &str) -> Option<Vec<preloads::Named>> {
        if !preloads::preload_file(name) {
            return None;
        }
        let file = join(directory, name);
        let Some(data) = self.snapshot.read(&file) else {
            self.gap(
                &format!("Preload configuration {file} cannot be read"),
                None,
                "",
                GapKind::Collection,
            );
            return Some(Vec::new());
        };
        let text = String::from_utf8_lossy(&data);
        let base = file.rsplit('/').next().unwrap_or_default();
        if preloads::malformed_config(base, &text) {
            self.gap(
                &format!("Preload configuration {file} is malformed"),
                None,
                "",
                GapKind::Collection,
            );
            return Some(Vec::new());
        }
        Some(
            preloads::names_of(base, &text)
                .into_iter()
                .map(|name| preloads::Named {
                    line: preloads::line_of(&text, &name),
                    mode: preloads::mode_of(base, &text, &name),
                    name,
                    file: file.clone(),
                })
                .collect(),
        )
    }

    /// Does code in this closure reach Node's module object?
    fn reaches_module(&mut self, file: &str) -> bool {
        self.snapshot
            .read(file)
            .is_some_and(|data| preloads::reaches_module(&String::from_utf8_lossy(&data)))
    }

    /// Report a loader patch found in one preload-closure file.
    fn loader_patch(&mut self, preload: &preloads::Named, file: &str, module: bool) {
        let Some(data) = self.snapshot.read(file) else {
            return;
        };
        let text = String::from_utf8_lossy(&data);
        if let Some(line) = preloads::patch_line(&text, module) {
            let reason = format!(
                "Preload {} named in {}:{} patches the module loader at {file}:{line}",
                preload.name, preload.file, preload.line
            );
            self.gap(&reason, None, "", GapKind::Collection);
        }
    }

    /// Read the closure from the entries, or `None` above the budget.
    pub(super) fn closure_graph(&mut self, entries: &[(String, String, String)]) -> Option<Graph> {
        let mut seen: HashSet<String> = HashSet::new();
        let mut queue: Vec<String> = Vec::new();
        let fresh: Vec<String> = entries
            .iter()
            .map(|(file, _, _)| file.clone())
            .filter(|file| seen.insert(file.clone()))
            .collect();
        Vec::extend(&mut queue, fresh);
        let mut graph = Graph::default();
        let mut index = 0;
        while index < Vec::len(&queue) {
            if index == BUDGET {
                return None;
            }
            let file = queue[index].clone();
            index += 1;
            let step = self.package_step(&file);
            if let Some(project) = step.project {
                graph.reached.insert(file.clone(), (file.clone(), project));
            }
            for next in &step.installed {
                Vec::push(
                    graph.importers.entry(next.clone()).or_default(),
                    file.clone(),
                );
            }
            let fresh: Vec<String> = step
                .installed
                .into_iter()
                .filter(|next| seen.insert(next.clone()))
                .collect();
            Vec::extend(&mut queue, fresh);
        }
        graph.files = queue;
        Some(graph)
    }

    /// One gap for each import of the scan whose installed file reaches project source.
    fn closure_gaps(
        &mut self,
        entries: &[(String, String, String)],
        witness: impl Fn(&str) -> Option<(String, String)>,
    ) {
        for (file, module, evidence) in entries {
            let Some((via, project)) = witness(file) else {
                continue;
            };
            let through = if String::is_empty(&via) || via == *file {
                String::new()
            } else {
                format!(" through {via}")
            };
            let reason =
                format!("Installed package can reach project source: {file}{through}: {project}");
            self.gap(&reason, Some(evidence), module, GapKind::Resolution);
        }
    }

    /// The installed files and the first project file that one installed file imports.
    fn package_step(&mut self, file: &str) -> Step {
        let mut step = Step::default();
        let snapshot: &mut Snapshot = &mut self.snapshot;
        let Some(content) = snapshot.read(file) else {
            let why =
                Snapshot::size_gap(&self.snapshot, file).unwrap_or_else(|| "unreadable".to_owned());
            step.project = Some(format!("not read ({why})"));
            return step;
        };
        let reach = Options::reach(&self.resolver.options);
        let parsed = parse_for(&mut self.parsers, file, &content, reach, None);
        let text = String::from_utf8_lossy(&content);
        // A loader whose target is unknown can load project source (#1749, AD-812).
        let declaration = classify_file(file).and_then(|suffix| suffix.source_kind())
            == Some(SourceKind::Declaration);
        let loader = (!declaration)
            .then(|| {
                let computed_form = parsed.references.iter().find_map(|reference| {
                    Option::is_none(&reference.specifier).then(|| Form::as_str(reference.form))
                });
                unknown_loader(computed_form, &text, parsed.first_error)
            })
            .flatten();
        if let Some(loader) = loader {
            step.project = Some(format!("a loader with an unknown target ({loader})"));
            return step;
        }
        if parsed.first_error.is_some() {
            // A repaired part can hide an import: read each quoted specifier of the text too.
            for specifier in quoted_after(&text, &["from", "import", "require"]) {
                self.specifier_step(file, (&specifier, declaration), None, &mut step);
            }
        }
        for path in quoted_after(&text, &["path="]) {
            self.path_step(file, &path, &mut step);
        }
        // `declare module "x"`: a relative name augments a file; a bare name is an ambient module
        // unless `paths` or `baseUrl` can map it to a file (as the parser reads it).
        let aliased = Options::reach(&self.resolver.options).aliased;
        for name in quoted_after(&text, &["module"]) {
            if name.starts_with(['.', '/']) || aliased {
                self.specifier_step(file, (&name, true), None, &mut step);
            }
        }
        let format = format_of(&mut self.resolver, &mut self.snapshot, file);
        for reference in parsed.references.iter().chain(&parsed.directives) {
            self.package_import(file, reference, &format, &mut step);
            if step.project.is_some() {
                break;
            }
        }
        step
    }

    /// Resolve one import of an installed file into the step.
    fn package_import(
        &mut self,
        file: &str,
        reference: &Reference,
        format: &Lookup<ModuleFormat>,
        step: &mut Step,
    ) {
        let Some(specifier) = reference.specifier.as_deref() else {
            return;
        };
        let mode = match reference.form {
            Form::DynamicImport => Some(ModuleFormat::Esm),
            Form::Require | Form::ImportEquals => Some(ModuleFormat::Cjs),
            _ => match format {
                Lookup::Hit(format) => Some(*format),
                Lookup::Missing | Lookup::Unknown(_) => None,
            },
        };
        self.specifier_step(file, (specifier, reference.type_only), mode, step);
    }

    /// A reference path is relative to its file; another name is resolved as a specifier.
    fn path_step(&mut self, file: &str, path: &str, step: &mut Step) {
        let target = join(dirname(file), path);
        let snapshot: &mut Snapshot = &mut self.snapshot;
        if !snapshot.is_file(&target) {
            // A relative `types` directive names a directory or a name without a suffix.
            return self.specifier_step(file, (path, true), None, step);
        }
        if !installed(&mut self.snapshot, &target) {
            step.project = Some(target);
        } else if classify_file(&target)
            .and_then(|suffix| suffix.source_kind())
            .is_some()
        {
            Vec::push(&mut step.installed, target);
        }
    }

    /// The installed directory that a `node_modules` search finds for a package name from `file`
    /// (`@types/<name>` too, for a type reference), or `None` when it is not installed.
    pub(super) fn package_directory(
        &mut self,
        file: &str,
        name: &str,
        type_only: bool,
    ) -> Option<String> {
        if str::is_empty(name) || name.starts_with(['.', '/', '#']) {
            return None;
        }
        let names = package_names(name, type_only);
        let mut directory = dirname(file).to_owned();
        loop {
            if let Some(found) = self.first_directory(&directory, &names) {
                return installed(&mut self.snapshot, &found).then_some(found);
            }
            if String::is_empty(&directory) || directory == "." {
                return None;
            }
            directory = dirname(&directory).to_owned();
        }
    }

    /// The first `node_modules/<name>` directory below `directory`.
    fn first_directory(&mut self, directory: &str, names: &[String]) -> Option<String> {
        let snapshot: &mut Snapshot = &mut self.snapshot;
        names
            .iter()
            .map(|name| join(directory, &format!("node_modules/{name}")))
            .find(|candidate| snapshot.is_dir(candidate))
    }

    /// The source files of an installed package directory, without its nested packages.
    pub(super) fn package_files(&mut self, directory: &str) -> Vec<String> {
        let mut found = Vec::new();
        let mut pending = vec![directory.to_owned()];
        while let Some(next) = Vec::pop(&mut pending) {
            let snapshot: &mut Snapshot = &mut self.snapshot;
            let (files, directories) = snapshot.entries(&next);
            let sources = files.iter().map(|name| join(&next, name)).filter(|path| {
                classify_file(path)
                    .and_then(|suffix| suffix.source_kind())
                    .is_some()
            });
            Vec::extend(&mut found, sources);
            let nested = directories
                .iter()
                .filter(|name| *name != "node_modules")
                .map(|name| join(&next, name));
            Vec::extend(&mut pending, nested);
        }
        found
    }

    pub(super) fn preload_entries(
        &mut self,
        file: &str,
        name: &str,
        mode: Option<ModuleFormat>,
    ) -> Option<Vec<String>> {
        let name = name
            .strip_prefix("<rootDir>/")
            .map_or_else(|| name.to_owned(), |rest| format!("./{rest}"));
        let class = classify_specifier(&name);
        if class.builtin() {
            return Some(Vec::new());
        }
        let mut resolver = Resolver::for_node_preload(&self.resolver);
        let modes = [ModuleFormat::Cjs, ModuleFormat::Esm]
            .into_iter()
            .filter(|candidate| mode.is_none_or(|mode| *candidate == mode));
        let mut entries = Vec::new();
        for mode in modes {
            match resolver.resolve_classified(
                &mut self.snapshot,
                (&name, &class),
                file,
                Some(mode),
                true,
            ) {
                Lookup::Hit(found) if preloads::runtime_source(&found.path) => {
                    entries.push(found.path);
                }
                _ => return None,
            }
        }
        entries.sort();
        entries.dedup();
        Some(entries)
    }

    /// Resolve one specifier of an installed file, as the run resolves an import, into the step.
    fn specifier_step(
        &mut self,
        file: &str,
        (specifier, type_only): (&str, bool),
        mode: Option<ModuleFormat>,
        step: &mut Step,
    ) {
        let class = classify_specifier(specifier);
        if class.builtin() && !type_only {
            return;
        }
        let found = self.resolver.resolve_classified(
            &mut self.snapshot,
            (specifier, &class),
            file,
            mode,
            !type_only,
        );
        match found {
            Lookup::Hit(found) if installed(&mut self.snapshot, &found.path) => {
                let source = classify_file(&found.path).and_then(|suffix| suffix.source_kind());
                if source.is_some() {
                    Vec::push(&mut step.installed, found.path);
                }
            }
            Lookup::Hit(found) => step.project = Some(found.path),
            // A path that the resolver cannot decide can name a project file, also through a
            // link in `node_modules`. In an installed package directory each file can be the one.
            Lookup::Unknown(_) => match self.package_directory(file, &class.package, type_only) {
                Some(directory) => {
                    let files = self.package_files(&directory);
                    Vec::extend(&mut step.installed, files);
                }
                None => step.project = Some(format!("{specifier} (not decided)")),
            },
            Lookup::Missing => {}
        }
    }
}

/// A file reaches project source when a file that it imports does. Each reach keeps its witness.
fn reach_back(mut graph: Graph) -> HashMap<String, (String, String)> {
    let mut pending: Vec<String> = graph.reached.keys().cloned().collect();
    while let Some(file) = Vec::pop(&mut pending) {
        let witness = graph.reached[&file].clone();
        let importers = graph.importers.get(&file).cloned().unwrap_or_default();
        let fresh: Vec<String> = importers
            .into_iter()
            .filter(|importer| !graph.reached.contains_key(importer))
            .collect();
        for importer in fresh {
            graph.reached.insert(importer.clone(), witness.clone());
            Vec::push(&mut pending, importer);
        }
    }
    graph.reached
}

#[cfg(test)]
#[path = "package_closure_tests.rs"]
mod tests;
