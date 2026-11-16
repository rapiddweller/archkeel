// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module index state and its construction.

use super::alias::Aliases;
use super::climb::inside;
use super::outcome::{Edge, Outcome, TypeOf};
use crate::crates::{Crate, Workspace};
use crate::definitions::{Access, Form, Owner};
use crate::resolve::{classify, Found, Named};
use crate::scan::{Reference, Via};
use crate::tree::Module;
use std::collections::BTreeMap;

/// One file of the walk, with the names that it binds.
pub(crate) struct Frame<'a> {
    pub module: &'a Module,
    pub(super) krate: &'a Crate,
    /// The module id of the root of the target that holds the file.
    pub(super) root: &'a str,
    pub(super) bindings: BTreeMap<&'a str, Vec<&'a Reference>>,
    pub(super) globs: Vec<&'a Reference>,
}

pub(crate) struct Index<'a> {
    pub(super) workspace: &'a Workspace,
    /// A module or inline module, by its dotted id, to the module id of its file.
    pub(super) lexical: BTreeMap<String, &'a str>,
    pub(super) frames: BTreeMap<&'a str, Frame<'a>>,
    /// The names that `extern crate self as name;` binds to a crate root.
    pub(super) aliases: Aliases,
}

pub(crate) fn index<'a>(workspace: &'a Workspace, modules: &'a [Module]) -> Index<'a> {
    let mut built = Index {
        workspace,
        lexical: BTreeMap::new(),
        frames: BTreeMap::new(),
        aliases: Aliases::default(),
    };
    for module in modules {
        let Some(krate) = workspace.crates.get(module.crate_index) else {
            continue;
        };
        let Some(root) = krate
            .roots
            .iter()
            .map(|root| root.module.as_str())
            .filter(|root| inside(&module.module, root))
            .max_by_key(|root| root.len())
        else {
            continue;
        };
        built.lexical.insert(module.module.clone(), &module.module);
        built.aliases.record(module, root);
        for inline in &module.scan.inlines {
            built.lexical.insert(
                format!("{}.{}", module.module, inline.join(".")),
                &module.module,
            );
        }
        let mut frame = Frame {
            module,
            krate,
            root,
            bindings: BTreeMap::new(),
            globs: Vec::new(),
        };
        for reference in &module.scan.references {
            match &reference.via {
                crate::scan::Via::Use {
                    binding: Some(name),
                    ..
                } => frame.bindings.entry(name).or_default().push(reference),
                crate::scan::Via::Glob { .. } => frame.globs.push(reference),
                _ => {}
            }
        }
        built.frames.insert(&module.module, frame);
    }
    built
}

pub(super) fn lexical(frame: &Frame<'_>, scope: &[String]) -> String {
    scope.iter().fold(frame.module.module.clone(), |id, part| {
        format!("{id}.{part}")
    })
}

impl<'a> Frame<'a> {
    /// The module id of the root of the crate target that holds the file.
    pub(crate) fn root(&self) -> &'a str {
        self.root
    }

    /// The crate that holds the file.
    pub(crate) fn krate(&self) -> &'a Crate {
        self.krate
    }
}

impl Frame<'_> {
    /// The lexical module of a place in the file: the file module and the enclosing inline ones.
    pub(crate) fn lexical_at(&self, scope: &[String]) -> String {
        lexical(self, scope)
    }

    /// The glob `use` items of the file.
    pub(crate) fn globs(&self) -> impl Iterator<Item = &Reference> {
        self.globs.iter().copied()
    }

    /// The `use` leaves of the file that bind `name`.
    pub(crate) fn bound(&self, name: &str) -> &[&Reference] {
        self.bindings.get(name).map_or(&[], Vec::as_slice)
    }

    /// The `use` leaves of the file that bind a name, also `_`.
    pub(crate) fn leaves(&self) -> impl Iterator<Item = &Reference> {
        self.bindings.values().flatten().copied()
    }
}

impl<'a> Index<'a> {
    /// The workspace of the walk.
    pub(crate) fn workspace(&self) -> &'a Workspace {
        self.workspace
    }

    pub(crate) fn file_of(&self, lexical: &str) -> Option<&str> {
        self.lexical.get(lexical).copied()
    }

    pub(super) fn defines_type(&self, lexical: &str, name: &str) -> bool {
        let Some(frame) = self.file_of(lexical).and_then(|file| self.frames.get(file)) else {
            return false;
        };
        let types = [Form::Struct, Form::Enum, Form::Trait];
        frame.module.scan.definitions.iter().any(|d| {
            d.name == name
                && d.owner == Owner::Module
                && types.contains(&d.form)
                && self::lexical(frame, &d.scope) == lexical
        })
    }

    /// Each file of the walk.
    pub(crate) fn frames(&self) -> impl Iterator<Item = &Frame<'a>> {
        self.frames.values()
    }

    pub(crate) fn frame(&self, module: &str) -> Option<&Frame<'a>> {
        self.frames.get(module)
    }

    pub(crate) fn rel(&self, module: &str) -> Option<&str> {
        self.frames
            .get(module)
            .map(|frame| frame.module.rel.as_str())
    }

    pub(super) fn unique_root(&self, package: &str) -> Option<&str> {
        // A `[lib] name` gives a crate another name in source: the name may be that crate.
        let mut crates = self.workspace.crates.iter();
        if crates.any(|item| item.manifest.lib_name.is_some()) {
            return None;
        }
        if self
            .workspace
            .crates
            .iter()
            .filter(|item| item.ident == package)
            .count()
            != 1
        {
            return None;
        }
        Some(&self.workspace.primary_of(package)?.module)
    }
}

impl Index<'_> {
    /// From the module `root`, down the modules that `names` name, to its last name. Each module
    /// name must be the only declaration of its name in its file, and no step may be conditional:
    /// the one declaration then wins over each glob, and a macro cannot give the name again.
    pub(super) fn direct_reach(&self, root: &str, names: &[String]) -> Option<Outcome> {
        let (last, modules) = names.split_last()?;
        let mut at = root.to_owned();
        for name in modules {
            let parent = self.frame(self.file_of(&at)?)?;
            let scan = &parent.module.scan;
            if parent.module.gated || scan.counts.get(name) != Some(&1) {
                return None;
            }
            at = format!("{at}.{name}");
            // An attribute of an inline module is not read: any conditional item refuses the file.
            let inline = self.file_of(&at)? == parent.module.module;
            if inline && scan.conditional_use {
                return None;
            }
        }
        let frame = self.frame(self.file_of(&at)?)?;
        if frame.module.gated {
            return None;
        }
        Some(Outcome::Edge(Edge {
            module: self.file_of(&at)?.to_owned(),
            lexical: at,
            symbol: Some(last.clone()),
            level: 0,
            member_of: None,
        }))
    }
}

/// The deepest chain of explicit imports that the resolver follows.
pub(crate) const MAX_HOPS: usize = 8;

impl Index<'_> {
    /// Follow an explicit path to a workspace type. Every ambiguous step is refused (AD-544).
    pub(super) fn cross_type(
        &self,
        frame: &Frame<'_>,
        scope: &[String],
        ty: &[String],
    ) -> Option<TypeOf> {
        let scan = &frame.module.scan;
        // A macro in a block can give any name of the block again, and a macro that takes a path
        // in its tokens can give its first name again; an attribute can remove the file.
        let silent = |call: &crate::scan::MacroCall| {
            crate::tokens::NO_BIND_MACROS.contains(&call.name.as_str())
        };
        let opaque_gate = frame.module.gated && frame.module.gates.is_none();
        if scan.body_macros || opaque_gate || !scan.macro_calls.iter().all(silent) {
            return None;
        }
        let first = ty.first()?;
        let binding = frame.bound(first);
        let names = if binding.is_empty() {
            // A glob or a macro at module level can bring in a module of the name of the crate.
            if scan.counts.contains_key(first)
                || scan.module_macros
                || frame.globs().next().is_some()
            {
                return None;
            }
            ty.to_vec()
        } else {
            let [leaf] = binding else { return None };
            if scan.counts.get(first) != Some(&1)
                || scan.conditional_bindings.contains(first)
                || !matches!(leaf.via, Via::Use { block: false, .. })
                || leaf.absolute
                || frame.lexical_at(scope) != frame.lexical_at(&leaf.scope)
            {
                return None;
            }
            let mut names = leaf.names.clone();
            names.extend_from_slice(&ty[1..]);
            names
        };
        let first = names.first()?;
        let outcome = if first == "crate" {
            self.direct_reach(frame.root, names.get(1..)?)?
        } else {
            let found = classify(first, frame.krate, &scan.shadows, false)?;
            let Found::Edge(Named::Package(package)) = found else {
                return None;
            };
            self.direct_reach(self.unique_root(&package)?, names.get(1..)?)?
        };
        self.cross_outcome(outcome, names.last()?, (frame.root, 0))
    }

    /// The type that the edge names: a public exact type of its module, or the target of the one
    /// `pub use` leaf of its name. `home` is the root of the crate target that wrote the path: a
    /// restricted leaf is a step only in that target, where a path that cannot see it is an error.
    fn cross_outcome(
        &self,
        outcome: Outcome,
        expected: &str,
        (home, depth): (&str, usize),
    ) -> Option<TypeOf> {
        if depth > MAX_HOPS {
            return None;
        }
        let Outcome::Edge(edge) = outcome else {
            return None;
        };
        let name = edge.symbol.as_deref().filter(|name| *name == expected)?;
        let frame = self.frame(self.file_of(&edge.lexical)?)?;
        let scan = &frame.module.scan;
        if frame.module.gated || scan.counts.get(name) != Some(&1) {
            return None;
        }
        let local = frame.root == home;
        let is_type = scan.definitions.iter().any(|d| {
            d.name == name
                && d.owner == Owner::Module
                && (local || d.access == Access::Public)
                && matches!(d.form, Form::Struct | Form::Enum)
                && frame.lexical_at(&d.scope) == edge.lexical
        });
        if scan.exact_types.contains(name) && is_type {
            return Some(TypeOf::Known(edge.lexical, name.to_owned()));
        }
        let [leaf] = frame.bound(name) else {
            return None;
        };
        let public = matches!(leaf.via, Via::Use { reexport: true, .. })
            && !scan.restricted_bindings.contains(name);
        if !(public || local)
            || scan.conditional_bindings.contains(name)
            || !matches!(leaf.via, Via::Use { block: false, .. })
            || leaf.absolute
            || frame.lexical_at(&leaf.scope) != edge.lexical
        {
            return None;
        }
        let last = leaf.names.last()?;
        let first = leaf.names.first()?;
        let outcome = match first.as_str() {
            "crate" => self.direct_reach(frame.root, leaf.names.get(1..)?)?,
            "self" => self.direct_reach(&edge.lexical, leaf.names.get(1..)?)?,
            "super" => return None,
            _ => match classify(first, frame.krate, &scan.shadows, false) {
                Some(Found::Edge(Named::Package(package))) => {
                    self.direct_reach(self.unique_root(&package)?, leaf.names.get(1..)?)?
                }
                // A relative path starts at the module of the `use`, not at the crate root.
                None if leaf.names.len() > 1 => self.direct_reach(&edge.lexical, &leaf.names)?,
                _ => return None,
            },
        };
        self.cross_outcome(outcome, last, (home, depth + 1))
    }
}
