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

use crate::resolve::classify;
use crate::scan::Reference;
mod alias;
mod climb;
mod filled;
mod outcome;
mod state;
use alias::Aliases;
use climb::ascend;
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
    /// `place` is the lexical module and whether a glob may bind the first name. A `use` path
    /// does not look into globs: a glob and the path would wait for each other.
    fn path(
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
                return self.follow(frame.root, 0, names);
            }
            // The alias of the root is an item of the root, not a name of the extern prelude.
            if let Some(found) = self.prelude_edge(frame, names) {
                return found;
            }
        }
        if absolute {
            return self.prelude_edge(frame, names).unwrap_or(Outcome::None);
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
        self.follow(&cur, level, &names[at..])
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
            let alias = self.aliases.in_prelude(frame.root, first);
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
        root.is_some_and(|root| self.aliases.in_prelude(root, name))
    }
    /// What `names` names when its first name is in the extern prelude (`extern crate self as me;`).
    fn prelude_edge(&self, frame: &Frame<'_>, names: &[String]) -> Option<Outcome> {
        let first = names.first()?;
        let alias = self.aliases.in_prelude(frame.root, first);
        alias.then(|| self.follow(frame.root, 0, &names[1..]))
    }
    /// From the module `start`, down each segment that names a child module.
    fn follow(&self, start: &str, level: i64, rest: &[String]) -> Outcome {
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
        let scope: Vec<String> = place
            .0
            .strip_prefix(frame.module.module.as_str())
            .unwrap_or("")
            .split('.')
            .filter(|part| !part.is_empty())
            .map(str::to_owned)
            .collect();
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
            None if here.1 => self.follow(&child, 1, &names[1..]),
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
            return Some(self.follow(&lib.module, 0, &names[1..]));
        }
        let none = std::collections::BTreeSet::new();
        // A glob of an inline module reaches only its module and below; `use me::b::*` is no alias.
        let reaching: Vec<&&Reference> = frame
            .globs
            .iter()
            .filter(|glob| inside(lexical_at, &lexical(frame, &glob.scope)))
            .filter(|glob| !(aliased && glob.names.first() == Some(first)))
            .collect();
        let alias = || self.prelude_edge(frame, names);
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
}
impl Index<'_> {
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
        match self.path(frame, &target, glob.absolute, (&at, false, types), hops + 1) {
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
                    Outcome::None
                        if filled::may_fill(target.module) && !binds_nothing(self, target) =>
                    {
                        unknown("a macro call at module level of its module may define it")
                    }
                    found => found,
                }
            }
            Outcome::None if self.external(frame, glob) => Outcome::None,
            _ => unknown("its path names no module of the crate"),
        }
    }
    /// Whether the path of `glob` starts at a crate that the manifest or the sysroot names, and
    /// the file declares no name that hides it.
    fn external(&self, frame: &Frame<'_>, glob: &Reference) -> bool {
        let Some(first) = glob.names.first() else {
            return false;
        };
        let none = std::collections::BTreeSet::new();
        let declared = frame.module.scan.counts.contains_key(first);
        !declared
            && !self.aliases.in_prelude(frame.root, first)
            && classify(first, frame.krate, &none, glob.absolute).is_some()
    }
}

#[cfg(test)]
#[path = "modules_tests.rs"]
mod tests;
