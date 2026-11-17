// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT
//! Which module a path inside one crate names (AD-335, slice 5b-2c).
//!
//! The module index maps each module of the walk, and each inline `mod`, to the file that holds
//! it. A path starts at `crate`, `self` or `super`, or at a bare name. A bare name is local only
//! when the file declares it once, as a child `mod` or as a `use` leaf. A name that the file
//! declares more than once may name a module, so the path is UNKNOWN (the rule of 5b-1). A name
//! that the file does not declare may come from a glob `use`; the glob is followed into the
//! module that it names, and one that the scan cannot follow is UNKNOWN. Anything that is no
//! module (a type, a function, a crate) gives no edge.
//!
//! A name after a module that is no child module of it, with more names after it, is read as a
//! member of that module by the same rules (AD-802, #1517): in `crate::c::other::b::g`, a `use`
//! of `c` that names a module or a crate root (`crate`, an alias of `extern crate self`, a crate
//! of the workspace), or a glob of `c` that brings in `other`, takes the path on to that module.
//! An item of the module (a type, a trait) ends the walk there, with its route (AD-604).

use crate::resolve::classify;
use crate::scan::Reference;
use alias::Aliases;
mod alias;
mod climb;
mod filled;
mod outcome;
mod state;
mod walk;
pub(crate) use climb::inside;
pub(crate) use filled::binds_nothing;
pub(crate) use outcome::{Edge, Outcome, TypeOf};
use state::lexical;
pub(crate) use state::MAX_HOPS;
pub(crate) use state::{index, Frame, Index};

impl<'a> Index<'a> {
    /// From the module `start` of the walk, down the modules that `rest` names.
    pub(crate) fn reach(&self, start: &str, rest: &[String]) -> Outcome {
        self.follow(start, 0, rest)
    }
    /// The reason why a path of a value or a `use` leaf that ends at the child module of `edge`
    /// may name an item of the parent module with the same name too (#1405). A module shares the
    /// type namespace with each type, so that item is a value (`mod reply; pub fn reply() {}`):
    /// the file declares the name more than once, or a glob or a macro at module level of the
    /// parent can add it. A glob path names a module or an enum only and never asks this.
    pub(crate) fn module_or_item(&self, edge: &Edge) -> Option<String> {
        if edge.symbol.is_some() || edge.member_of.is_some() {
            return None;
        }
        let (parent, name) = edge.lexical.rsplit_once('.')?;
        let frame = self
            .file_of(parent)
            .and_then(|file| self.frames.get(file))?;
        let scan = &frame.module.scan;
        let may = scan.counts.get(name).is_some_and(|count| *count > 1)
            || scan.module_macros
            || frame.globs().next().is_some();
        may.then(|| {
            format!(
                "A path that ends at the module {} may name the item {name} of {parent}",
                edge.lexical
            )
        })
    }
    /// The type that `ty` names at `scope` of the file of `frame`. It is `Known` only when the
    /// module defines a struct, enum, union or trait of that name. A type alias, a re-export, a
    /// type that a macro or a function body defines, and a name that a glob may bring in are
    /// `Unknown`: the scan cannot say which type they are (#953).
    pub(crate) fn type_of(&self, frame: &Frame<'_>, scope: &[String], ty: &[String]) -> TypeOf {
        let local = self.local_type_of(frame, scope, ty);
        if matches!(local, TypeOf::Known(..)) {
            return local;
        }
        self.cross_type(frame, scope, ty).unwrap_or(local)
    }
    pub(crate) fn local_type_of(
        &self,
        frame: &Frame<'_>,
        scope: &[String],
        ty: &[String],
    ) -> TypeOf {
        let Some(name) = ty.last().filter(|name| *name != "Self") else {
            return TypeOf::Other;
        };
        let mut names = ty.to_vec();
        names.push(String::new());
        let path = Reference {
            names,
            scope: scope.to_vec(),
            ..Reference::default()
        };
        let declared = frame.module.scan.counts.contains_key(name);
        let (at, ty_name) = match self.resolve_mode(frame, &path, true) {
            // A renamed `use` binds one name to the type of the path.
            Outcome::Edge(edge) => match edge.symbol {
                Some(symbol) if !symbol.is_empty() && (ty.len() == 1 || symbol == *name) => {
                    (edge.lexical, symbol)
                }
                _ => return TypeOf::Other,
            },
            Outcome::None if ty.len() == 1 && declared => (lexical(frame, scope), name.clone()),
            Outcome::None if ty.len() != 1 || frame.globs.is_empty() => return TypeOf::Other,
            _ => return TypeOf::Unknown,
        };
        if self.defines_type(&at, &ty_name) {
            TypeOf::Known(at, ty_name)
        } else {
            TypeOf::Unknown
        }
    }
    /// What the path of `reference`, written in `frame`, names.
    pub(crate) fn resolve(&self, frame: &Frame<'_>, reference: &Reference) -> Outcome {
        self.resolve_mode(frame, reference, false)
    }
    fn resolve_mode(&self, frame: &Frame<'_>, reference: &Reference, types: bool) -> Outcome {
        let lexical = lexical(frame, &reference.scope);
        let globs = matches!(
            reference.via,
            crate::scan::Via::Path | crate::scan::Via::Helper
        );
        let helper =
            matches!(reference.via, crate::scan::Via::Helper) && reference.names.len() == 1;
        let single = helper.then(|| vec![reference.names[0].clone(), String::new()]);
        let outcome = self.path(
            frame,
            single.as_deref().unwrap_or(&reference.names),
            reference.absolute,
            (&lexical, globs, types),
            0,
        );
        match outcome {
            Outcome::Edge(mut edge) if helper && edge.symbol.as_deref() == Some("") => {
                edge.symbol = None;
                Outcome::Edge(edge)
            }
            other => other,
        }
    }
    /// The path that `reference` names through the `use` leaves of its file when it starts at
    /// another crate: `use dep::m; m::f()` names `dep::m::f` (AD-604). Each step needs the one
    /// declaration of its name, with no attribute that can remove the leaf, as `bare` does.
    pub(crate) fn crate_path(
        &self,
        frame: &Frame<'_>,
        reference: &Reference,
    ) -> Option<Vec<String>> {
        let scan = &frame.module.scan;
        let mut names = reference.names.clone();
        for _ in 0..=MAX_HOPS {
            let first = names.first()?;
            let alias = Aliases::in_prelude(&self.aliases, frame.root, first);
            let found = classify(first, frame.krate, &scan.shadows, false).filter(|_| !alias);
            if matches!(found, Some(crate::resolve::Found::Edge(_))) {
                return (names.len() > 1).then_some(names);
            }
            let [leaf] = frame.bound(first) else {
                return None;
            };
            if scan.counts.get(first) != Some(&1) || scan.conditional_bindings.contains(first) {
                return None;
            }
            let mut full = leaf.names.clone();
            full.extend_from_slice(&names[1..]);
            names = full;
        }
        None
    }
    /// Whether `name` is an alias of the extern prelude for the target that holds `module`.
    pub(crate) fn is_alias(&self, module: &str, name: &str) -> bool {
        let root = self.frames.get(module).map(|frame| frame.root);
        root.is_some_and(|root| Aliases::in_prelude(&self.aliases, root, name))
    }
    /// From the module `start`, down each segment that names a child module.
    fn follow(&self, start: &str, level: i64, rest: &[String]) -> Outcome {
        self.walk(start, level, rest, 0)
    }
}

#[cfg(test)]
#[path = "modules_tests.rs"]
mod tests;
