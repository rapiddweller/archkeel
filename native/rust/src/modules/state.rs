// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module index state and its construction.

use super::alias::Aliases;
use super::climb::inside;
use super::outcome::{Edge, Outcome, TypeOf};
use crate::crates::{Crate, Workspace};
use crate::definitions::{Form, Owner};
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

    pub(crate) fn frame(&self, module: &str) -> Option<&Frame<'a>> {
        self.frames.get(module)
    }

    pub(crate) fn rel(&self, module: &str) -> Option<&str> {
        self.frames
            .get(module)
            .map(|frame| frame.module.rel.as_str())
    }

    pub(super) fn unique_root(&self, package: &str) -> Option<&str> {
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

pub(super) fn clean(frame: &Frame<'_>) -> bool {
    !frame.module.scan.conditional_use
        && frame.globs().next().is_none()
        && !frame.module.scan.macro_calls.iter().any(|call| call.fills)
}

impl Index<'_> {
    pub(super) fn direct_reach(&self, root: &str, names: &[String]) -> Option<Outcome> {
        let (last, modules) = names.split_last()?;
        let mut at = root.to_owned();
        for name in modules {
            let frame = self.frame(self.file_of(&at)?)?;
            if frame.module.gated || !clean(frame) {
                return None;
            }
            at = format!("{at}.{name}");
            self.file_of(&at)?;
        }
        let frame = self.frame(self.file_of(&at)?)?;
        if frame.module.gated || !clean(frame) {
            return None;
        }
        Some(Outcome::Edge(Edge {
            module: self.file_of(&at)?.to_owned(),
            lexical: at,
            symbol: Some(last.clone()),
            level: 0,
        }))
    }
}

/// The deepest chain of explicit imports that the resolver follows.
pub(super) const MAX_HOPS: usize = 8;

impl Index<'_> {
    /// Follow an explicit import of a workspace type. Every ambiguous step is refused.
    pub(super) fn cross_type(
        &self,
        frame: &Frame<'_>,
        scope: &[String],
        ty: &[String],
    ) -> Option<TypeOf> {
        if !clean(frame)
            || frame
                .module
                .scan
                .macro_calls
                .iter()
                .any(|call| !crate::tokens::NO_BIND_MACROS.contains(&call.name.as_str()))
        {
            return None;
        }
        let first = ty.first()?;
        let binding = frame.bound(first);
        let names = if binding.is_empty() {
            ty.to_vec()
        } else {
            let [leaf] = binding else { return None };
            if frame.module.scan.counts.get(first) != Some(&1)
                || !matches!(leaf.via, Via::Use { block: false, .. })
                || !inside(&frame.lexical_at(scope), &frame.lexical_at(&leaf.scope))
            {
                return None;
            }
            let mut names = leaf.names.clone();
            names.extend_from_slice(&ty[1..]);
            names
        };
        let first = names.first()?;
        let found = classify(first, frame.krate, &frame.module.scan.shadows, false)?;
        let Found::Edge(Named::Package(package)) = found else {
            return None;
        };
        let root = self.unique_root(&package)?;
        let outcome = self.direct_reach(root, names.get(1..)?)?;
        self.cross_outcome(outcome, names.last()?, 0)
    }

    fn cross_outcome(&self, outcome: Outcome, expected: &str, depth: usize) -> Option<TypeOf> {
        if depth > MAX_HOPS {
            return None;
        }
        let Outcome::Edge(edge) = outcome else {
            return None;
        };
        let name = edge.symbol.as_deref().filter(|name| *name == expected)?;
        let frame = self.frame(self.file_of(&edge.lexical)?)?;
        if !clean(frame) || frame.module.gated {
            return None;
        }
        let scan = &frame.module.scan;
        let exact = scan.exact_types.contains(name) && scan.counts.get(name) == Some(&1);
        let is_type = scan.definitions.iter().any(|d| {
            d.name == name
                && d.owner == Owner::Module
                && matches!(d.form, Form::Struct | Form::Enum)
                && frame.lexical_at(&d.scope) == edge.lexical
        });
        if exact && is_type {
            return Some(TypeOf::Known(edge.lexical, name.to_owned()));
        }
        let [leaf] = frame.bound(name) else {
            return None;
        };
        if scan.counts.get(name) != Some(&1)
            || !matches!(
                leaf.via,
                Via::Use {
                    reexport: true,
                    block: false,
                    ..
                }
            )
            || frame.lexical_at(&leaf.scope) != edge.lexical
        {
            return None;
        }
        let last = leaf.names.last()?;
        let first = leaf.names.first()?;
        let external = classify(
            first,
            frame.krate,
            &frame.module.scan.shadows,
            leaf.absolute,
        );
        let outcome = match external {
            Some(Found::Edge(Named::Package(package))) => {
                self.direct_reach(self.unique_root(&package)?, leaf.names.get(1..)?)?
            }
            None if !leaf.absolute && (leaf.scope.is_empty() || first == "crate") => {
                let rest = if first == "crate" {
                    leaf.names.get(1..)?
                } else {
                    &leaf.names
                };
                self.direct_reach(frame.root, rest)?
            }
            _ => return None,
        };
        self.cross_outcome(outcome, last, depth + 1)
    }
}
