// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The dependencies of the global scripts of a project on one another, on the platform and on
//! vendored libraries (`collect._script_dependencies` and the helpers that it calls).
//!
//! A script that uses `Lib.run()` depends on whatever publishes `Lib`: another script of the
//! project, a standard `lib` file, a `declare` or a vendored library. The result is one import
//! record for each use, with a target, or an UNKNOWN gap where nothing proves the publisher.

use std::collections::{HashMap, HashSet};

use crate::kept::Kept;
use crate::script_project::{stable_publication, Project, Publisher, Write, WriteIndex};
use crate::source::FileSiteKey;
use archkeel_facts::identity::{evidence_id, stable_id, Part};

use crate::script_records::{Effect, Sink, SiteKey};
use crate::script_types::{ScriptAlias, ScriptDestructure};
use crate::script_vendor::Vendors;
use crate::sites::{Site, SiteKind};
use crate::source::Span;

/// `collect._SCRIPT_ROOTS`: the names of the global object, and `top` and `parent`, which are the
/// window outside a frame. The analysis of a use reads them as roots; the walk of a file does not,
/// so a write through them publishes nothing, and a local variable named `parent` is no root.
pub(crate) fn is_root(name: &str) -> bool {
    crate::source_input::is_script_root(name.as_bytes()) || FRAME_ROOTS.contains(&name)
}

/// `ScriptRoot.TOP` and `ScriptRoot.PARENT`: dependency roots, not publication roots.
const FRAME_ROOTS: [&str; 2] = ["top", "parent"];

/// `ScriptRoot.unrooted`: how many leading names of a path name the global object, so that
/// `window.self.x` is `x` (#1007).
pub(crate) fn leading_roots(path: &[String]) -> usize {
    path.iter().take_while(|name| is_root(name)).count()
}

/// A site as the analysis reads it: a site of the file, or a name that a destructuring brings.
pub(crate) struct Probe {
    pub kind: SiteKind,
    pub span: Span,
    pub path: Vec<String>,
    pub scope_ambiguous: bool,
}

impl Probe {
    pub(crate) fn key(&self) -> SiteKey {
        SiteKey::new(self.kind, &self.span, &self.path)
    }
}

/// The state of one analysis. The project is read; the sink is written.
pub(crate) struct Run<'a, 'p> {
    pub project: &'p Project<'a>,
    pub partial: bool,
    pub standard: HashSet<String>,
    pub vendors: Vendors,
    pub writes: WriteIndex<'a>,
    pub source_writes: WriteIndex<'a>,
    /// The source writes without repeats, to ask whether one is among them.
    pub source_set: HashSet<Write<'a>>,
    pub sink: Sink,
}

/// The aliases of one file by the places that they name.
struct AliasIndex<'a> {
    aliases: &'a [ScriptAlias],
    used: HashMap<&'a Span, Vec<usize>>,
    initialized: HashMap<&'a Span, Vec<usize>>,
    destructures: HashMap<&'a Span, Vec<&'a ScriptDestructure>>,
}

impl<'a> AliasIndex<'a> {
    fn new(aliases: &'a [ScriptAlias], destructures: &'a [ScriptDestructure]) -> Self {
        let mut index = Self {
            aliases,
            used: HashMap::new(),
            initialized: HashMap::new(),
            destructures: HashMap::new(),
        };
        for (at, alias) in aliases.iter().enumerate() {
            for span in alias.calls.iter().chain(&alias.reads) {
                index.used.entry(span).or_default().push(at);
            }
            index
                .initialized
                .entry(&alias.reference_span)
                .or_default()
                .push(at);
        }
        for item in destructures {
            index.destructures.entry(&item.span).or_default().push(item);
        }
        index
    }

    /// `script_publication.site_aliases`: the alias that a site calls or reads, and the alias that
    /// the site initializes.
    fn of(&self, probe: &Probe) -> (Option<&'a ScriptAlias>, Option<&'a ScriptAlias>) {
        let aliased = |at: &&usize| self.aliases.get(**at);
        let call = self
            .used
            .get(&probe.span)
            .into_iter()
            .flatten()
            .filter_map(|at| {
                let alias = self.aliases.get(*at)?;
                // An alias of the global object itself has no name to follow (#1007).
                let fits = (probe.kind == SiteKind::Call || alias.factory)
                    && leading_roots(&alias.path) < alias.path.len()
                    && probe.path.len() == 2
                    && probe.path.first() == Some(&alias.name);
                fits.then_some(alias)
            });
        let initializer = self
            .initialized
            .get(&probe.span)
            .into_iter()
            .flatten()
            .filter_map(|at| aliased(&at))
            .find(|alias| probe.kind == SiteKind::Reference || alias.factory);
        (call.into_iter().next(), initializer)
    }
}

impl<'a, 'p> Run<'a, 'p> {
    /// The probe of a site of `file`.
    fn probe(file: &Kept, site: &Site) -> Probe {
        let data = &file.text;
        let path = site.path.map(|at| file.sites.paths.names(at, data));
        Probe {
            kind: site.kind,
            span: site.span.clone(),
            path: path.unwrap_or_default(),
            scope_ambiguous: site.scope_ambiguous,
        }
    }

    /// `_script_dependencies`: every use of a global in the files that can use one.
    pub(crate) fn analyze(&mut self, import_sites: &HashSet<FileSiteKey<'_>>) {
        let loaders = self.loader_sites(import_sites);
        let project = self.project;
        for (rel, file) in &project.files {
            if file.script.dependency_scope {
                self.file_sites(rel, file, &loaders);
            }
        }
    }

    /// The uses of globals in one file; a call that an import record stands for is skipped.
    fn file_sites(&mut self, rel: &str, file: &Kept, loaders: &HashSet<FileSiteKey<'_>>) {
        let script = &file.script.script;
        let index = AliasIndex::new(&script.aliases, &script.destructures);
        for site in &file.sites.sites {
            let at = FileSiteKey {
                rel,
                line: site.span.line,
                column: site.span.column,
            };
            if site.kind != SiteKind::Call || !loaders.contains(&at) {
                self.site(rel, file, site, &index);
            }
        }
    }

    /// The `require` calls that an import record stands for.
    fn loader_sites<'s>(&self, import_sites: &HashSet<FileSiteKey<'_>>) -> HashSet<FileSiteKey<'s>>
    where
        'a: 's,
    {
        let files = self.project.files.iter();
        let requires = files.flat_map(|(rel, file)| {
            let listed = file.script.requires.iter();
            listed.map(move |(line, column)| FileSiteKey {
                rel,
                line: *line,
                column: *column,
            })
        });
        requires.filter(|at| import_sites.contains(at)).collect()
    }

    fn site(&mut self, rel: &str, file: &Kept, site: &Site, index: &AliasIndex) {
        let probe = Self::probe(file, site);
        if let Some(items) = index.destructures.get(&site.span) {
            for item in items {
                self.destructured(rel, &probe, item);
            }
            return;
        }
        let (alias_call, alias_initializer) = index.of(&probe);
        let alias = alias_call.or(alias_initializer);
        let mut path: Vec<String> = match alias_call {
            Some(call) => {
                let rest = if call.factory {
                    &[][..]
                } else {
                    probe.path.get(1..).unwrap_or(&[])
                };
                call.path.iter().chain(rest).cloned().collect()
            }
            None => probe.path.clone(),
        };
        if self.root_escape(rel, site, &probe, &path) {
            return;
        }
        path.drain(..leading_roots(&path));
        let initialized = alias_initializer.filter(|alias| !alias.factory && !path.is_empty());
        if let Some(initialized) = initialized {
            if self.alias_decomposition(rel, &probe, initialized, &path) {
                return;
            }
        }
        let shadowed = alias_call.is_none()
            && probe
                .path
                .first()
                .is_some_and(|first| file.shadow.shadows(site.shadow.chain, first));
        if path.is_empty() || !(site.script_free || alias_call.is_some()) || shadowed {
            return;
        }
        let publishers = self.publishers(path.first());
        self.dependency(rel, &probe, &path, (alias_call, alias), publishers);
    }

    /// The publications of a name, in file order.
    pub(crate) fn publishers(&self, name: Option<&String>) -> &'p [Publisher<'a>] {
        let found = name.and_then(|name| self.project.publications.get(name.as_str()));
        found.map_or(&[][..], Vec::as_slice)
    }

    /// The member of a destructuring `const { a } = window.Lib` is a use of `Lib.a`.
    fn destructured(&mut self, rel: &str, probe: &Probe, item: &ScriptDestructure) {
        for (published, _, span) in &item.members {
            let path: Vec<String> = item
                .path
                .iter()
                .skip(leading_roots(&item.path))
                .chain(std::iter::once(published))
                .cloned()
                .collect();
            let member = Probe {
                kind: probe.kind,
                span: span.clone(),
                path: path.clone(),
                scope_ambiguous: probe.scope_ambiguous,
            };
            let publishers = self.publishers(path.first());
            self.dependency(rel, &member, &path, (None, None), publishers);
        }
    }

    /// `_script_root_escape`: a root used as a value cannot be followed.
    fn root_escape(&mut self, rel: &str, site: &Site, probe: &Probe, path: &[String]) -> bool {
        // A chain of roots is a value of the global object too; a comparison of members such as
        // `window.top === window.self` is no escape (`script_escape` is false for it).
        let escaped = !path.is_empty()
            && leading_roots(path) == path.len()
            && site.script_free
            && (site.script_escape || site.computed || site.kind != SiteKind::Reference);
        if !escaped {
            return false;
        }
        let evidence = self.sink.cite(rel, &probe.span);
        let module = self.module(rel);
        let reason = "Escaped or computed global host dependency is not statically bounded";
        self.sink.gap(reason, &[evidence], &module);
        true
    }

    /// `_script_alias_decomposition`: an alias of a published object whose calls are all known.
    fn alias_decomposition(
        &mut self,
        rel: &str,
        probe: &Probe,
        alias: &ScriptAlias,
        path: &[String],
    ) -> bool {
        let publishers = self.publishers(path.first());
        let first = path.first().map_or("", String::as_str);
        if alias.calls.is_empty() || !stable_publication(first, publishers, &self.source_writes) {
            return false;
        }
        let Some((target_rel, publication)) = publishers.first().copied() else {
            return false;
        };
        self.alias_evidence(rel, probe, alias, target_rel, Some(publication), true);
        true
    }

    /// `_script_unbounded_effects` and `_script_runtime_effect`: the writes that no publication
    /// bounds. A gap names each, and a record is made when the reply is written.
    pub(crate) fn effects(&mut self, all: &[Write<'a>], early: Vec<(String, Span)>) {
        let mut pending = early;
        for (rel, file) in &self.project.files {
            let spans = file
                .script
                .script
                .globals
                .iter()
                .flat_map(|item| &item.availability);
            pending.extend(spans.map(|span| ((*rel).to_owned(), span.clone())));
        }
        for write in all {
            let (rel, name, span) = *write;
            let scripted = self.file(rel).is_some_and(|file| file.script.script_mode);
            let known = name.is_none_or(|name| self.project.publications.contains_key(name));
            if scripted && known && !self.source_set.contains(write) {
                pending.push((rel.to_owned(), span.clone()));
            }
        }
        let mut seen = HashSet::new();
        for (rel, span) in pending {
            if !seen.insert((rel.clone(), span.clone())) {
                continue;
            }
            let module = self.module(&rel);
            let parts = [
                Part::Text(&module),
                Part::Number(span.line),
                Part::Number(span.column),
            ];
            let identity = stable_id("TS_RUNTIME_EFFECT", &parts);
            let evidence = evidence_id(&rel, span.line, span.end_line, span.column);
            self.sink.effect_gap(&module, &identity, &evidence);
            self.sink.facts.effects.push(Effect { rel, module, span });
        }
    }

    /// The module of a file.
    pub(crate) fn module(&self, rel: &str) -> String {
        let at = self.project.index.get(rel).copied();
        at.and_then(|at| self.project.files.get(at))
            .map_or_else(String::new, |(_, file)| file.module.clone())
    }

    /// The file of a path; the facts of a file that the walk read.
    pub(crate) fn file(&self, rel: &str) -> Option<&'a Kept> {
        let at = self.project.index.get(rel).copied()?;
        self.project.files.get(at).map(|(_, file)| *file)
    }

    /// `(rel, name, span)` of every write that a script makes, an escaped object included
    /// (`_script_global_writes`).
    pub(crate) fn global_writes(project: &Project<'a>) -> Vec<Write<'a>> {
        let mut writes: Vec<Write<'a>> = Vec::new();
        for (rel, file) in &project.files {
            let listed = file.script.script.writes.iter();
            writes.extend(listed.map(|(name, span)| (*rel, name.as_deref(), span)));
        }
        for (rel, file) in &project.files {
            writes.extend(escaped(project, rel, file));
        }
        writes
    }
}

/// A published name that a site reads as a value that escapes: an unknown write of the name.
fn escaped<'a>(project: &Project<'a>, rel: &'a str, file: &'a Kept) -> Vec<Write<'a>> {
    let data = &file.text;
    let mut found = Vec::new();
    for site in &file.sites.sites {
        if site.kind != SiteKind::Reference || !site.script_escape {
            continue;
        }
        let path = site
            .path
            .map(|at| file.sites.paths.names(at, data))
            .unwrap_or_default();
        let skip = leading_roots(&path);
        let [name] = path.get(skip..).unwrap_or(&[]) else {
            continue;
        };
        let Some((key, _)) = project.publications.get_key_value(name.as_str()) else {
            continue;
        };
        let aliased = file
            .script
            .script
            .aliases
            .iter()
            .any(|a| a.reference_span == site.span);
        if !aliased {
            found.push((rel, Some(*key), &site.span));
        }
    }
    found
}
