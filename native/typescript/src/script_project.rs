// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cross-file indexes of the script analysis. Python answers each question about "every other
//! file" with a loop over the project for each site (`_script_global_stable`,
//! `_script_vendor_package`, `_script_declared_global`, `stable_publication`). The indexes here are
//! built once and answer the same questions with a lookup, so a project with n files and m sites
//! does not cost n times m.

use std::cell::OnceCell;
use std::collections::{HashMap, HashSet};

use crate::kept::Kept;
use crate::script_types::{ScriptGlobal, ScriptNamespace};
use crate::source::Span;

/// A file that publishes a global, and the publication.
pub type Publisher<'a> = (&'a str, &'a ScriptGlobal);

/// A write of a name that a script makes: the file, the name (`None` where it is not known) and the
/// place.
pub type Write<'a> = (&'a str, Option<&'a str>, &'a Span);

/// The writes that can name one global: those of the name and those of no known name.
/// `stable_publication` asks whether exactly one write does, and which. A name keeps its first
/// write and how many there are, so n writes cost n entries and no list for each name.
#[derive(Default)]
pub struct WriteIndex<'a> {
    unknown: Option<(Write<'a>, usize)>,
    named: HashMap<&'a str, (Write<'a>, usize)>,
}

impl<'a> WriteIndex<'a> {
    pub fn new(writes: impl IntoIterator<Item = Write<'a>>) -> Self {
        let mut index = Self::default();
        for write in writes {
            let slot = match write.1 {
                Some(name) => index.named.entry(name).or_insert((write, 0)),
                None => index.unknown.get_or_insert((write, 0)),
            };
            slot.1 = slot.1.saturating_add(1);
        }
        index
    }

    /// The only write that is of the name or of no known name: its file and place.
    pub fn sole(&self, name: &str) -> Option<(&'a str, &'a Span)> {
        let count = |slot: Option<&(Write<'a>, usize)>| slot.map_or(0, |(_, count)| *count);
        let named = self.named.get(name);
        let total = count(named).saturating_add(count(self.unknown.as_ref()));
        let first = named.or(self.unknown.as_ref())?;
        (total == 1).then_some((first.0 .0, first.0 .2))
    }
}

/// `script_publication.stable_publication`.
pub fn stable_publication(name: &str, publishers: &[Publisher], writes: &WriteIndex) -> bool {
    let [(rel, publication)] = publishers else {
        return false;
    };
    publication.stable && writes.sole(name) == Some((*rel, &publication.span))
}

/// `script_publication.source_origin`.
pub fn source_origin(name: &str, publishers: &[Publisher], writes: &WriteIndex) -> bool {
    let [(rel, publication)] = publishers else {
        return false;
    };
    (publication.stable || publication.source_origin)
        && writes.sole(name) == Some((*rel, &publication.span))
}

/// The global write paths of the project, as the questions about them need them.
#[derive(Default)]
pub struct WritePaths<'a> {
    /// A write has no path (`()`): it may name anything.
    pub any_empty: bool,
    /// Some write has a path at all.
    pub any_path: bool,
    /// The paths of one name (`(name,)`), by the name and the files that write them.
    pub singles: HashMap<&'a str, Owners>,
    /// Some path starts with the name of a loader (`exports`, `module`, `define`).
    pub loader_first: bool,
    /// Every path, to find the prefixes of them when a factory asks (`has_prefix`).
    all: Vec<&'a [String]>,
    prefixes: OnceCell<HashSet<&'a [String]>>,
}

impl<'a> WritePaths<'a> {
    /// Some path starts with `prefix` (`path[:len(prefix)] == prefix`). The set of the prefixes of
    /// all paths is built when the first factory asks, so a project without one pays nothing.
    pub fn has_prefix(&self, prefix: &[String]) -> bool {
        if prefix.is_empty() {
            return self.any_path;
        }
        let set = self.prefixes.get_or_init(|| {
            let lengths = |path: &&'a [String]| {
                let path: &'a [String] = path;
                (1..=path.len()).map(move |n| path.get(..n))
            };
            self.all.iter().flat_map(lengths).flatten().collect()
        });
        set.contains(prefix)
    }
}

/// The files that hold something, kept as the first file and whether another file holds it too:
/// the questions ask for "a file other than this one", never for the list.
#[derive(Clone, Copy)]
pub struct Owners {
    first: usize,
    more: bool,
}

impl Owners {
    fn add<'a>(owners: &mut HashMap<&'a str, Owners>, name: &'a str, file: usize) {
        let entry = owners.entry(name).or_insert(Owners {
            first: file,
            more: false,
        });
        entry.more |= entry.first != file;
    }

    /// A file other than `file` holds it.
    pub fn other_than(self, file: usize) -> bool {
        self.first != file || self.more
    }
}

/// The names of the module loaders: a script may not write them under a vendor's name.
pub const LOADER_NAMES: [&str; 3] = ["exports", "module", "define"];

/// The names that a classic script host gives itself.
pub const HOST_NAMES: [&str; 6] = ["exports", "module", "define", "window", "global", "self"];

/// The first project `declare` of a name, and whether a global script of another file binds the
/// name (`_script_declared_global`: a `declare const` also binds its own file; only another
/// binding blocks).
pub struct Declared<'a> {
    pub file: usize,
    pub span: &'a Span,
    pub bound_elsewhere: bool,
}

/// What the project knows once every file is read.
pub struct Project<'a> {
    pub files: Vec<(&'a str, &'a Kept)>,
    pub index: HashMap<&'a str, usize>,
    /// `script_globals` by name, in file order.
    pub publications: HashMap<&'a str, Vec<Publisher<'a>>>,
    pub paths: WritePaths<'a>,
    /// Some file has a syntax error.
    pub any_error: bool,
    /// The names that a global script binds, and the files that bind each.
    pub bound_in_scripts: HashMap<&'a str, Owners>,
    /// The names that a file binds at the top level, whatever the file is.
    pub bound_anywhere: HashMap<&'a str, Owners>,
    pub namespaces: HashMap<&'a str, Vec<(usize, &'a ScriptNamespace)>>,
    /// The first `declare` of each name, in file order by path.
    pub declared: HashMap<&'a str, Declared<'a>>,
}

impl<'a> Project<'a> {
    /// `collect._global_script`: the top-level names of the file belong to the global scope.
    pub fn global_script(file: &Kept, scripts_are_global: bool) -> bool {
        file.script.declaration_file || (scripts_are_global && !file.script.module_file)
    }

    pub fn new(
        order: &'a [String],
        kept: &'a std::collections::BTreeMap<String, Kept>,
        scripts_are_global: bool,
    ) -> Self {
        let files: Vec<(&str, &Kept)> = order
            .iter()
            .filter_map(|rel| Some((rel.as_str(), kept.get(rel)?)))
            .collect();
        let index = files.iter().enumerate().map(|(at, f)| (f.0, at)).collect();
        let mut project = Self {
            index,
            publications: HashMap::new(),
            paths: WritePaths::default(),
            any_error: files.iter().any(|(_, file)| file.has_error),
            bound_in_scripts: HashMap::new(),
            bound_anywhere: HashMap::new(),
            namespaces: HashMap::new(),
            declared: HashMap::new(),
            files: Vec::new(),
        };
        for (at, (rel, file)) in files.iter().enumerate() {
            let global = Self::global_script(file, scripts_are_global);
            project.add_file(at, rel, file, global);
        }
        // `_script_declared_global` visits the files in the order of their paths.
        let mut sorted: Vec<usize> = (0..files.len()).collect();
        sorted.sort_by_key(|at| files.get(*at).map(|file| file.0));
        for at in sorted {
            let Some((_, file)) = files.get(at) else {
                continue;
            };
            let global = Self::global_script(file, scripts_are_global);
            let top = global.then_some(&file.script.ambient_top_level);
            let listed = file
                .script
                .ambient_globals
                .iter()
                .chain(top.into_iter().flatten());
            for (name, span) in listed {
                project.declared.entry(name).or_insert(Declared {
                    file: at,
                    span,
                    bound_elsewhere: false,
                });
            }
        }
        project.mark_bound_elsewhere(&files, scripts_are_global);
        project.files = files;
        project
    }

    /// A name is bound elsewhere when a global script that does not declare it binds it. One pass
    /// over the bindings of each global script, so the cost does not grow with the product of the
    /// declared names and the files.
    fn mark_bound_elsewhere(&mut self, files: &[(&'a str, &'a Kept)], scripts_are_global: bool) {
        for (_, kept) in files {
            if Self::global_script(kept, scripts_are_global) {
                self.mark_bindings_of(kept);
            }
        }
    }

    /// The bindings of one global script that name a declared name which the script does not declare.
    fn mark_bindings_of(&mut self, kept: &'a Kept) {
        let (globals, top) = (&kept.script.ambient_globals, &kept.script.ambient_top_level);
        // The names that the file declares, listed once and only when a binding needs them.
        let own = OnceCell::new();
        let declares = |name: &str| {
            let listed = own.get_or_init(|| {
                let names = globals.iter().chain(top.iter());
                names
                    .map(|(declared, _)| declared.as_str())
                    .collect::<HashSet<_>>()
            });
            listed.contains(name)
        };
        for name in &kept.script.bindings {
            if let Some(entry) = self.declared.get_mut(name.as_str()) {
                entry.bound_elsewhere |= !declares(name);
            }
        }
    }

    fn add_file(&mut self, at: usize, rel: &'a str, file: &'a Kept, global: bool) {
        let script = &file.script;
        for publication in &script.script.globals {
            let listed = self.publications.entry(&publication.name).or_default();
            listed.push((rel, publication));
        }
        for name in &script.bindings {
            Owners::add(&mut self.bound_anywhere, name, at);
            if global {
                Owners::add(&mut self.bound_in_scripts, name, at);
            }
        }
        for item in &script.script.namespaces {
            self.namespaces
                .entry(&item.name)
                .or_default()
                .push((at, item));
        }
        let top = global.then_some(&script.script.top_level_write_paths);
        let listed = script
            .script
            .write_paths
            .iter()
            .chain(top.into_iter().flatten());
        for path in listed {
            self.add_path(at, path);
        }
    }

    fn add_path(&mut self, at: usize, path: &'a [String]) {
        let paths = &mut self.paths;
        paths.any_path = true;
        match path {
            [] => paths.any_empty = true,
            [name] => Owners::add(&mut paths.singles, name, at),
            _ => {}
        }
        if path
            .first()
            .is_some_and(|first| LOADER_NAMES.contains(&first.as_str()))
        {
            paths.loader_first = true;
        }
        paths.all.push(path);
    }

    /// Another file than `file` binds `name`, or writes the path `(name,)`.
    pub fn bound_or_written_elsewhere(&self, name: &str, file: usize) -> bool {
        let other = |owners: Option<&Owners>| owners.is_some_and(|owners| owners.other_than(file));
        other(self.bound_anywhere.get(name)) || other(self.paths.singles.get(name))
    }
}

#[cfg(test)]
#[path = "script_project_tests.rs"]
mod tests;
