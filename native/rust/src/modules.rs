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

use std::collections::BTreeMap;

use crate::crates::{Crate, Workspace};
use crate::definitions::{Form, Owner};
use crate::resolve::classify;
use crate::scan::Reference;
use crate::tree::Module;
mod alias;
mod climb;
mod outcome;
use alias::Aliases;
use climb::climb;
pub(crate) use outcome::{Edge, Outcome, TypeOf};

/// The deepest chain of `use` bindings and globs that the resolver follows.
const MAX_HOPS: usize = 8;

/// One file of the walk, with the names that it binds.
pub(crate) struct Frame<'a> {
    pub module: &'a Module,
    krate: &'a Crate,
    /// The module id of the root of the target that holds the file.
    root: &'a str,
    bindings: BTreeMap<&'a str, Vec<&'a Reference>>,
    globs: Vec<&'a Reference>,
}

pub(crate) struct Index<'a> {
    /// A module or inline module, by its dotted id, to the module id of its file.
    lexical: BTreeMap<String, &'a str>,
    frames: BTreeMap<&'a str, Frame<'a>>,
    /// The names that `extern crate self as name;` binds to a crate root.
    aliases: Aliases,
}

pub(crate) fn index<'a>(workspace: &'a Workspace, modules: &'a [Module]) -> Index<'a> {
    let mut built = Index {
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

/// Whether `module` is `root` or a module below it.
pub(crate) fn inside(module: &str, root: &str) -> bool {
    module == root
        || module
            .strip_prefix(root)
            .is_some_and(|rest| rest.starts_with('.'))
}

fn lexical(frame: &Frame<'_>, scope: &[String]) -> String {
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
    /// The file module that holds a module or an inline module.
    pub(crate) fn file_of(&self, lexical: &str) -> Option<&str> {
        self.lexical.get(lexical).copied()
    }

    /// From the module `start` of the walk, down the modules that `rest` names.
    pub(crate) fn reach(&self, start: &str, rest: &[String]) -> Outcome {
        self.follow(start, 0, rest)
    }

    /// The type that `ty` names at `scope` of the file of `frame`. It is `Known` only when the
    /// module defines a struct, enum, union or trait of that name. A type alias, a re-export, a
    /// type that a macro or a function body defines, and a name that a glob may bring in are
    /// `Unknown`: the scan cannot say which type they are (#953).
    pub(crate) fn type_of(&self, frame: &Frame<'_>, scope: &[String], ty: &[String]) -> TypeOf {
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
        let (at, ty_name) = match self.resolve(frame, &path) {
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

    /// Whether the lexical module defines a struct, an enum, a union or a trait named `name`.
    fn defines_type(&self, lexical: &str, name: &str) -> bool {
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

    /// The file of a module of the walk.
    pub(crate) fn rel(&self, module: &str) -> Option<&str> {
        self.frames
            .get(module)
            .map(|frame| frame.module.rel.as_str())
    }

    /// What the path of `reference`, written in `frame`, names.
    pub(crate) fn resolve(&self, frame: &Frame<'_>, reference: &Reference) -> Outcome {
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
            (&lexical, globs),
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
        place: (&str, bool),
        hops: usize,
    ) -> Outcome {
        if hops > MAX_HOPS {
            return Outcome::Unknown("A chain of use items is too long to follow".to_owned());
        }
        let (lexical, globs) = place;
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
                match climb(frame.root, &cur, names, start) {
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

    /// The file module of the deepest module that `rest` names below `start`.
    pub(crate) fn deepest(&self, start: &str, rest: &[String]) -> String {
        match self.follow(start, 0, rest) {
            Outcome::Edge(edge) => edge.module,
            _ => start.to_owned(),
        }
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
        })
    }

    fn bare(
        &self,
        frame: &Frame<'_>,
        names: &[String],
        place: (&str, bool),
        hops: usize,
        globs: bool,
    ) -> Outcome {
        // The count and the bindings below are read across the whole file, not in the scope of the
        // path. That is safe only because a name that the file declares more than once is UNKNOWN.
        let first = &names[0];
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
        let (count, local) = if aliased && own && count == 1 {
            (0, false)
        } else {
            (count, local)
        };
        if count == 0 && !local {
            if let Some(found) = self.unbound(frame, names, (place.0, hops), globs) {
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
        if count != 1 {
            let reason =
                format!("A name that the file declares more than once may name a module: {first}");
            return Outcome::Unknown(reason);
        }
        match bound {
            Some(bindings) => {
                let binding = bindings[0];
                let at = lexical(frame, &binding.scope);
                let mut full = binding.names.clone();
                full.extend_from_slice(&names[1..]);
                // The only declaration of the name is this leaf, and its path starts with the
                // same name: the path cannot start at the leaf itself (`use dep::{dep}`). It
                // starts at a crate, and the name is no declaration for it.
                if binding.names.first() == Some(first) {
                    let unbound = self.unbound(frame, &full, (&at, hops), false);
                    return unbound.unwrap_or(Outcome::None);
                }
                self.path(frame, &full, binding.absolute, (&at, false), hops + 1)
            }
            None => self.follow(&child, 1, &names[1..]),
        }
    }

    /// A name that the file does not declare: the own package from a binary, a crate, a name from
    /// the prelude, or a name that a glob `use` brings in.
    fn unbound(
        &self,
        frame: &Frame<'_>,
        names: &[String],
        (lexical_at, hops): (&str, usize),
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
            match self.through_glob(frame, glob, names, hops) {
                Outcome::None => {}
                found => return Some(found),
            }
        }
        alias()
    }
}

impl Index<'_> {
    /// What `names` names when the glob `use` brings in its first name, or `None`.
    fn through_glob(
        &self,
        frame: &Frame<'_>,
        glob: &Reference,
        names: &[String],
        hops: usize,
    ) -> Outcome {
        let at = lexical(frame, &glob.scope);
        match self.path(frame, &glob.names, glob.absolute, (&at, false), hops + 1) {
            Outcome::Unknown(reason) => {
                Outcome::Unknown(format!("A glob import may bring in {}: {reason}", names[0]))
            }
            Outcome::Edge(edge) if edge.symbol.is_none() => {
                let Some(target) = self.frames.get(edge.module.as_str()) else {
                    return Outcome::None;
                };
                match self.bare(target, names, (edge.lexical.as_str(), true), hops + 1, true) {
                    // A macro call of the module may define the name (`mk!();` for `pub use`).
                    Outcome::None
                        if target.module.scan.macro_calls.iter().any(|c| !c.expression) =>
                    {
                        let reason = format!(
                            "A glob may bring in {} from a module that a macro call fills",
                            names[0]
                        );
                        Outcome::Unknown(reason)
                    }
                    found => found,
                }
            }
            _ => Outcome::None,
        }
    }
}

#[cfg(test)]
#[path = "modules_tests.rs"]
mod tests;
