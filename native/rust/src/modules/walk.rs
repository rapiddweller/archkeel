// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The walk of a path through the module index: from its first name (`path`, `bare`, `unbound`),
//! down its modules (`walk`), through a member that a `use` leaf or a glob of a module gives
//! (`member`, `through_glob`, AD-772), and into another crate of the workspace (`through_crate`).
//! These steps call each other, so they stay in one file. The entry points of the resolver in
//! `modules.rs` call them; they call no entry point.

use super::alias::Aliases;
use super::climb::{ascend, inside};
use super::filled;
use super::outcome::{Edge, Outcome};
use super::state::{lexical, Frame, Index, MAX_HOPS};
use crate::resolve::{classify, Found, Named};
use crate::scan::Reference;
use std::collections::BTreeSet;

impl Index<'_> {
    /// `place` is the lexical module and whether a glob may bind the first name. A `use` path
    /// does not look into globs: a glob and the path would wait for each other.
    pub(super) fn path(
        &self,
        frame: &Frame<'_>,
        names: &[String],
        absolute: bool,
        place: (&str, bool, bool),
        hops: usize,
    ) -> Outcome {
        if hops > MAX_HOPS {
            return Outcome::Unknown("A chain of use items is too long to follow".to_owned());
        }
        let (lexical, globs, _) = place;
        let Some(first) = names.first().map(String::as_str) else {
            return Outcome::None;
        };
        // Edition 2015: a `use` path and a `::` path start at the crate root, so a first name
        // that is a module of the root names that module (and a crate name is no module).
        let rooted = frame.krate.manifest.legacy() && (absolute || !globs);
        let root_child = format!("{}.{first}", frame.root);
        if rooted && !["crate", "self", "super"].contains(&first) {
            if self.lexical.contains_key(&root_child) {
                return self.walk(frame.root, 0, names, hops);
            }
            // The alias of the root is an item of the root, not a name of the extern prelude.
            if let Some(found) = self.prelude_edge(frame, names, hops) {
                return found;
            }
        }
        if absolute {
            return self
                .prelude_edge(frame, names, hops)
                .unwrap_or(Outcome::None);
        }
        let (mut cur, mut level) = (lexical.to_owned(), 1);
        let at = match first {
            "crate" => {
                (cur, level) = (frame.root.to_owned(), 0);
                1
            }
            "self" | "super" => {
                let start = usize::from(first == "self");
                match ascend(frame.root, &cur, names, start) {
                    Ok((above, ups, at)) => {
                        (cur, level) = (above, level + ups);
                        at
                    }
                    Err(reason) => return Outcome::Unknown(reason.to_owned()),
                }
            }
            _ => return self.bare(frame, names, place, hops, globs),
        };
        self.walk(&cur, level, &names[at..], hops)
    }
    /// What `names` names when its first name is in the extern prelude (`extern crate self as me;`).
    fn prelude_edge(&self, frame: &Frame<'_>, names: &[String], hops: usize) -> Option<Outcome> {
        let first = names.first()?;
        let alias = self.aliases.in_prelude(frame.root, first);
        alias.then(|| self.walk(frame.root, 0, &names[1..], hops))
    }
    /// `follow` after `hops` steps through `use` leaves. A segment that is no child module and
    /// has more segments after it is read as a member of its module (`member`, #1517).
    pub(super) fn walk(&self, start: &str, level: i64, rest: &[String], hops: usize) -> Outcome {
        let mut cur = start.to_owned();
        let mut used = 0;
        while let Some(part) = rest.get(used) {
            let next = format!("{cur}.{part}");
            if self.lexical.contains_key(&next) {
                cur = next;
            } else if let Some(root) = self.aliases.member(&cur, part) {
                cur = root.to_owned();
            } else {
                break;
            }
            used += 1;
        }
        if used + 1 < rest.len() && self.lexical.contains_key(&cur) {
            if let Some(found) = self.member(&cur, level, &rest[used..], hops) {
                return found;
            }
        }
        let Some(module) = self.lexical.get(&cur) else {
            return Outcome::Unknown(format!("The module {cur} is not in the walk"));
        };
        Outcome::Edge(Edge {
            module: (*module).to_owned(),
            lexical: cur,
            symbol: rest.get(used).cloned(),
            level,
            member_of: None,
        })
    }
    fn bare(
        &self,
        frame: &Frame<'_>,
        names: &[String],
        place: (&str, bool, bool),
        hops: usize,
        globs: bool,
    ) -> Outcome {
        // The alias check reads the count and the bindings of the whole file. The one declaration of
        // the name is read in the inline module of the path: a declaration of a child module is no
        // name here, and a glob of the child stays a glob (AD-614). Within the module the rule is
        // the old one: a name that it declares more than once is UNKNOWN.
        let first = &names[0];
        if place.2 && frame.module.scan.conditional_bindings.contains(first) {
            return Outcome::Unknown(format!("A conditional use may not bind {first}"));
        }
        let aliased = self.aliases.in_prelude(frame.root, first);
        if first == "Self" || (names.len() < 2 && !aliased) {
            return Outcome::None;
        }
        let count = frame.module.scan.counts.get(first).copied().unwrap_or(0);
        let child = format!("{}.{first}", place.0);
        let bound = frame.bindings.get(first.as_str());
        let local = self.lexical.contains_key(&child) || bound.is_some();
        // The one declaration of the alias name may be the alias item of the crate root itself.
        let aliases = &frame.module.scan.self_aliases;
        let own =
            frame.module.module == frame.root && aliases.contains(&(Vec::new(), first.clone()));
        if count == 0 && !local {
            if let Some(found) = self.unbound(frame, names, (place.0, hops, place.2), globs) {
                return found;
            }
            return Outcome::None;
        }
        // A `use` or a `mod` hides the alias in its own scope only; the declaration of any other
        // kind, and one in a function body, are not placed.
        let scopes: Vec<(String, bool)> = (bound.into_iter().flatten())
            .map(|leaf| {
                (
                    lexical(frame, &leaf.scope),
                    matches!(leaf.via, crate::scan::Via::Use { block: true, .. }),
                )
            })
            .collect();
        let here = (place.0, self.lexical.contains_key(&child));
        if aliased && Aliases::contested((count, own), &scopes, here) {
            let reason =
                format!("A name that the file declares may hide the alias of the crate: {first}");
            return Outcome::Unknown(reason);
        }
        if !local {
            return Outcome::None;
        }
        let scope = frame.scope_of(place.0);
        let scan = &frame.module.scan;
        let here_count = scan.scoped_counts.get(&(scope, first.clone())).copied();
        let here_bound: Vec<&Reference> = (bound.into_iter().flatten())
            .copied()
            .filter(|leaf| lexical(frame, &leaf.scope) == place.0)
            .collect();
        if here_count.unwrap_or(0) == 0 && here_bound.is_empty() && !here.1 {
            return self
                .unbound(frame, names, (place.0, hops, place.2), globs)
                .unwrap_or(Outcome::None);
        }
        if here_count != Some(1) {
            let reason =
                format!("A name that the file declares more than once may name a module: {first}");
            return Outcome::Unknown(reason);
        }
        match (!here_bound.is_empty()).then_some(here_bound) {
            Some(bindings) => {
                let binding = bindings[0];
                let at = lexical(frame, &binding.scope);
                let mut full = binding.names.clone();
                full.extend_from_slice(&names[1..]);
                // The only declaration of the name is this leaf, and its path starts with the
                // same name: the path cannot start at the leaf itself (`use dep::{dep}`). It
                // starts at a crate, and the name is no declaration for it.
                if binding.names.first() == Some(first) {
                    let unbound = self.unbound(frame, &full, (&at, hops, place.2), false);
                    return unbound.unwrap_or(Outcome::None);
                }
                self.path(
                    frame,
                    &full,
                    binding.absolute,
                    (&at, false, place.2),
                    hops + 1,
                )
            }
            None if here.1 => self.walk(&child, 1, &names[1..], hops),
            // The one declaration here is an item, not a module: the path names no module.
            None => Outcome::None,
        }
    }
    /// A name that the file does not declare: the own package from a binary, a crate, a name from
    /// the prelude, or a name that a glob `use` brings in.
    fn unbound(
        &self,
        frame: &Frame<'_>,
        names: &[String],
        (lexical_at, hops, types): (&str, usize, bool),
        globs: bool,
    ) -> Option<Outcome> {
        let first = &names[0];
        let primary = frame.krate.primary.as_ref();
        let aliased = self.aliases.in_prelude(frame.root, first);
        if *first == frame.krate.ident && !aliased {
            let lib = primary.filter(|root| root.module != frame.root)?;
            return Some(self.walk(&lib.module, 0, &names[1..], hops));
        }
        let none = BTreeSet::new();
        // A glob of an inline module reaches only its module and below; `use me::b::*` is no alias.
        let reaching: Vec<&&Reference> = frame
            .globs
            .iter()
            .filter(|glob| inside(lexical_at, &lexical(frame, &glob.scope)))
            .filter(|glob| !(aliased && glob.names.first() == Some(first)))
            .collect();
        let alias = || self.prelude_edge(frame, names, hops);
        let crate_name = !aliased && classify(first, frame.krate, &none, false).is_some();
        if crate_name || reaching.is_empty() {
            return alias();
        }
        if !globs {
            let reason =
                format!("A use path starts with a name that a glob import may bring in: {first}");
            return Some(Outcome::Unknown(reason));
        }
        for glob in reaching {
            match self.through_glob(frame, glob, names, hops, types) {
                Outcome::None => {}
                found => return Some(found),
            }
        }
        alias()
    }
    /// What `names` names when its first name is a member of the lexical module `at` and more
    /// names follow it (AD-772). `None` when it is an item of `at`: the path names `at`. Each step
    /// uses up a name, and each `use` leaf that `bare` follows counts a hop.
    fn member(&self, at: &str, level: i64, names: &[String], hops: usize) -> Option<Outcome> {
        let frame = self.file_of(at).and_then(|file| self.frames.get(file))?;
        // An empty last name lets the member end at a module, as `through_glob` does.
        let probe = [names[0].clone(), String::new()];
        match self.bare(frame, &probe, (at, true, false), hops + 1, true) {
            Outcome::Edge(edge) if edge.symbol.as_deref().is_none_or(str::is_empty) => {
                Some(self.walk(&edge.lexical, level, &names[1..], hops + 1))
            }
            Outcome::Edge(_) => None,
            Outcome::Unknown(reason) => Some(Outcome::Unknown(reason)),
            Outcome::None => self.undeclared_or_crate(frame, at, names, (level, hops)),
        }
    }

    /// A member that `bare` reads as no module. The one module-level leaf of the name may name a
    /// crate of the workspace (`pub use base as other;`, `pub use base;`). A name that the module
    /// does not declare may come from a macro call at module level of its file, unless each such
    /// call binds nothing (`binds_nothing`): the path is UNKNOWN then.
    fn undeclared_or_crate(
        &self,
        frame: &Frame<'_>,
        at: &str,
        names: &[String],
        (level, hops): (i64, usize),
    ) -> Option<Outcome> {
        let leaves = frame.module_leaves(&names[0], at);
        let scan = &frame.module.scan;
        let [leaf] = leaves.as_slice() else {
            let key = (frame.scope_of(at), names[0].clone());
            let undeclared = leaves.is_empty() && !scan.scoped_counts.contains_key(&key);
            if undeclared && filled::may_fill(frame.module) && !filled::binds_nothing(self, frame) {
                let reason = format!(
                    "A macro call at module level of {at} may bring in {}",
                    names[0]
                );
                return Some(Outcome::Unknown(reason));
            }
            return None;
        };
        let own = leaf.names.first() == names.first();
        let none = BTreeSet::new();
        let shadows = (!own).then_some(&scan.shadows);
        let head = (
            leaf.names.as_slice(),
            leaf.absolute,
            shadows.unwrap_or(&none),
        );
        self.through_crate(frame, head, &names[1..], (level, hops))
    }
    /// The path `head` + `tail` when `head` starts at a crate of the workspace: from the root of
    /// that crate. A registry name of a crate of the workspace may be that crate (AD-704): the
    /// path is UNKNOWN. `None` for any other first name.
    fn through_crate(
        &self,
        frame: &Frame<'_>,
        (head, absolute, shadows): (&[String], bool, &BTreeSet<String>),
        tail: &[String],
        (level, hops): (i64, usize),
    ) -> Option<Outcome> {
        let first = head.first()?;
        if self.aliases.in_prelude(frame.root, first) {
            return None;
        }
        match classify(first, frame.krate, shadows, absolute)? {
            Found::Edge(Named::Package(package)) => {
                let root = &self.workspace.primary_of(&package)?.module;
                let rest: Vec<String> = head[1..].iter().chain(tail).cloned().collect();
                Some(self.walk(root, level, &rest, hops + 1))
            }
            Found::Edge(Named::Registry(package))
                if self.workspace.primary_of(&package).is_some() =>
            {
                let reason = format!(
                    "A registry name of a crate of the workspace may be that crate: {first}"
                );
                Some(Outcome::Unknown(reason))
            }
            _ => None,
        }
    }
    /// What `names` names when the glob `use` brings in its first name, or `None`. The glob is
    /// read only when the resolver of `use` paths takes its whole path to a module of the crate,
    /// which no macro call at module level may fill, or names an external crate. Any other glob
    /// may bring in the name, so the path is UNKNOWN.
    fn through_glob(
        &self,
        frame: &Frame<'_>,
        glob: &Reference,
        names: &[String],
        hops: usize,
        types: bool,
    ) -> Outcome {
        if types
            && frame
                .module
                .scan
                .conditional_globs
                .contains(&(glob.site.line, glob.site.column))
        {
            return Outcome::Unknown("A conditional glob may not bind the name".to_owned());
        }
        let at = lexical(frame, &glob.scope);
        let unknown =
            |why: &str| Outcome::Unknown(format!("A glob import may bring in {}: {why}", names[0]));
        // An empty last name lets the path end at a module (`use yy::*;`, `use crate::*;`).
        let mut target = glob.names.clone();
        target.push(String::new());
        let mut reached = self.path(frame, &target, glob.absolute, (&at, false, types), hops + 1);
        // A glob of a crate of the workspace (`use base::*;`) brings in the names of its root.
        if reached == Outcome::None && self.external(frame, glob) {
            let (tail, none) = ([String::new()], BTreeSet::new());
            match self.through_crate(frame, (&glob.names, glob.absolute, &none), &tail, (0, hops)) {
                Some(found) => reached = found,
                None => return Outcome::None,
            }
        }
        match reached {
            Outcome::Unknown(reason) => unknown(&reason),
            Outcome::Edge(edge) if edge.symbol.as_deref().is_none_or(str::is_empty) => {
                let Some(target) = self.frames.get(edge.module.as_str()) else {
                    return unknown("the module of the glob is not in the walk");
                };
                match self.bare(
                    target,
                    names,
                    (edge.lexical.as_str(), true, types),
                    hops + 1,
                    true,
                ) {
                    Outcome::None if filled::may_fill(target.module) => {
                        unknown("a macro call at module level of its module may define it")
                    }
                    found => found,
                }
            }
            _ => unknown("its path names no module of the crate"),
        }
    }
}
