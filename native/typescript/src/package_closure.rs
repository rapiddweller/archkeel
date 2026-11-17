// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closure of the installed packages that the scan imports (#1529, AD-798).
//!
//! The code of an installed package is outside the model (AD-488 point 4), but it can import
//! project source by a relative path: `node_modules/local/index.js` with `import "../../src/b"`.
//! Then each module that imports the package depends on that source. The collector reads the
//! static imports of each installed file that an import of the scan reaches, and of each installed
//! file that those reach. An import that resolves to a file outside `node_modules`, and an
//! installed file that the collector cannot read, is a gap of each module whose import reaches it.
//! A computed import inside a package is not read: it is the open class of a string loader.

use std::collections::{HashMap, HashSet};

use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

use crate::collection::{Collection, GapKind};
use crate::installed::installed;
use crate::manifest::Lookup;
use crate::options::Options;
use crate::parse::parse_for;
use crate::references::{Form, Reference};
use crate::resolve::format_of;
use crate::source_input::{classify_file, classify_specifier, ModuleFormat, SourceKind};

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
struct Graph {
    importers: HashMap<String, Vec<String>>,
    reached: HashMap<String, (String, String)>,
}

impl Collection<'_> {
    /// The gap of each module whose import of an installed package reaches project source.
    pub(crate) fn package_closure(&mut self) {
        let entries = std::mem::take(&mut self.installed);
        let Some(graph) = self.closure_graph(&entries) else {
            let reason = format!("more than {BUDGET} installed files");
            return self.closure_gaps(&entries, |_| Some((String::new(), reason.clone())));
        };
        let reached = reach_back(graph);
        self.closure_gaps(&entries, |file| reached.get(file).cloned());
    }

    /// Read the closure from the entries, or `None` above the budget.
    fn closure_graph(&mut self, entries: &[(String, String, String)]) -> Option<Graph> {
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
        if parsed.first_error.is_some() {
            // A repaired part can hide an import: read each quoted specifier of the text too.
            let declaration = classify_file(file).and_then(|suffix| suffix.source_kind())
                == Some(SourceKind::Declaration);
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

    /// A `/// <reference path>` directive names a file relative to its own file; another name is
    /// resolved as a specifier.
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
    fn package_directory(&mut self, file: &str, name: &str, type_only: bool) -> Option<String> {
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
    fn package_files(&mut self, directory: &str) -> Vec<String> {
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

/// The names that a `node_modules` search tries for a package: the name, and `@types/<name>` for a
/// type reference.
fn package_names(name: &str, type_only: bool) -> Vec<String> {
    let mut names = vec![name.to_owned()];
    if type_only {
        let mangled = name
            .strip_prefix('@')
            .map_or_else(|| name.to_owned(), |scoped| scoped.replacen('/', "__", 1));
        Vec::push(&mut names, format!("@types/{mangled}"));
    }
    names
}

/// Each quoted text after one of the words, with blanks and one `(` between: `from "x"`,
/// `import("x")`, `require('x')`, `path="x"`, `module "x"`. A word inside a longer name or after a
/// `.` is no word. A text in a comment is read too: the reading over-matches on purpose.
fn quoted_after(text: &str, words: &[&str]) -> Vec<String> {
    let bytes = text.as_bytes();
    let mut found = Vec::new();
    for word in words {
        for (at, _) in text.match_indices(word) {
            let before = at.checked_sub(1).and_then(|i| bytes.get(i));
            let joined = |b: &u8| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'$' | b'.');
            if before.is_some_and(joined) {
                continue;
            }
            let rest = text
                .get(at + str::len(word)..)
                .unwrap_or_default()
                .trim_start();
            let rest = rest.strip_prefix('(').map_or(rest, str::trim_start);
            if let Some(quoted) = quoted(rest) {
                Vec::push(&mut found, quoted);
            }
        }
    }
    found
}

/// The text of a leading quoted string that can be a specifier: not empty, without a blank, a
/// line end, a bracket, a comma or a semicolon.
fn quoted(rest: &str) -> Option<String> {
    let quote = rest
        .chars()
        .next()
        .filter(|c| matches!(c, '"' | '\'' | '`'))?;
    let inner = rest.get(1..)?;
    let text = inner.get(..inner.find(quote)?)?;
    let specifier = !str::is_empty(text)
        && !text.contains(|c: char| c.is_whitespace() || "(){}[],;".contains(c));
    specifier.then(|| text.to_owned())
}

#[cfg(test)]
#[path = "package_closure_tests.rs"]
mod tests;
