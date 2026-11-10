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
use crate::resolve::classify;
use crate::scan::Reference;
use crate::tree::Module;

/// The deepest chain of `use` bindings and globs that the resolver follows.
const MAX_HOPS: usize = 8;

/// A module that a path names: the file that holds it and the first segment after it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Edge {
    /// The module id of the file that holds the target.
    pub module: String,
    /// The module of the target itself: an inline `mod` has its own, below its file.
    pub lexical: String,
    /// The segment after the deepest module, or `None` when the path ends at a module.
    pub symbol: Option<String>,
    /// 0 for `crate::`, 1 for `self::` and a child name, `n + 1` for `super::` n times.
    pub level: i64,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    /// The path names no module of this crate (a crate, a type, a function).
    None,
    Edge(Edge),
    /// The scan cannot say which module the path names, and says why.
    Unknown(String),
}

/// One file of the walk, with the names that it binds.
pub struct Frame<'a> {
    pub module: &'a Module,
    krate: &'a Crate,
    /// The module id of the root of the target that holds the file.
    root: &'a str,
    bindings: BTreeMap<&'a str, Vec<&'a Reference>>,
    globs: Vec<&'a Reference>,
}

pub struct Index<'a> {
    /// A module or inline module, by its dotted id, to the module id of its file.
    lexical: BTreeMap<String, &'a str>,
    frames: BTreeMap<&'a str, Frame<'a>>,
}

pub fn index<'a>(workspace: &'a Workspace, modules: &'a [Module]) -> Index<'a> {
    let mut built = Index {
        lexical: BTreeMap::new(),
        frames: BTreeMap::new(),
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
        for inline in &module.scan.inlines {
            built
                .lexical
                .insert(format!("{}.{}", module.module, inline.join(".")), &module.module);
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

fn inside(module: &str, root: &str) -> bool {
    module == root || module.strip_prefix(root).is_some_and(|rest| rest.starts_with('.'))
}

fn lexical(frame: &Frame<'_>, scope: &[String]) -> String {
    scope
        .iter()
        .fold(frame.module.module.clone(), |id, part| format!("{id}.{part}"))
}

impl<'a> Index<'a> {
    pub fn frame(&self, module: &str) -> Option<&Frame<'a>> {
        self.frames.get(module)
    }

    /// The file of a module of the walk.
    pub fn rel(&self, module: &str) -> Option<&str> {
        self.frames.get(module).map(|frame| frame.module.rel.as_str())
    }

    /// What the path of `reference`, written in `frame`, names.
    pub fn resolve(&self, frame: &Frame<'_>, reference: &Reference) -> Outcome {
        let lexical = lexical(frame, &reference.scope);
        let globs = matches!(reference.via, crate::scan::Via::Path);
        let found = self.path(frame, &reference.names, reference.absolute, (&lexical, globs), 0);
        if reference.in_macro && found != Outcome::None {
            let reason = "A macro_rules! body holds a module path: the scan does not know where it expands";
            return Outcome::Unknown(reason.to_owned());
        }
        found
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
        if absolute {
            return Outcome::None;
        }
        let (mut cur, mut level, mut at) = (lexical.to_owned(), 1, 0);
        match first {
            "crate" => (cur, level, at) = (frame.root.to_owned(), 0, 1),
            "self" | "super" => {
                at = usize::from(first == "self");
                while names.get(at).map(String::as_str) == Some("super") {
                    if cur == frame.root {
                        return Outcome::Unknown("super names a module above the crate root".to_owned());
                    }
                    cur = cur.rsplit_once('.').map_or(cur.clone(), |(parent, _)| parent.to_owned());
                    level += 1;
                    at += 1;
                }
            }
            _ => return self.bare(frame, names, place, hops, globs),
        }
        self.follow(&cur, level, &names[at..])
    }

    /// From the module `start`, down each segment that names a child module.
    fn follow(&self, start: &str, level: i64, rest: &[String]) -> Outcome {
        let mut cur = start.to_owned();
        let mut used = 0;
        while let Some(next) = rest.get(used).map(|part| format!("{cur}.{part}")) {
            if !self.lexical.contains_key(&next) {
                break;
            }
            cur = next;
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
        let first = &names[0];
        if first == "Self" || names.len() < 2 {
            return Outcome::None;
        }
        let count = frame.module.scan.counts.get(first).copied().unwrap_or(0);
        let child = format!("{}.{first}", place.0);
        let bound = frame.bindings.get(first.as_str());
        let local = self.lexical.contains_key(&child) || bound.is_some();
        if count == 0 && !local {
            if let Some(found) = self.unbound(frame, names, hops, globs) {
                return found;
            }
            return Outcome::None;
        }
        if !local {
            return Outcome::None;
        }
        if count != 1 {
            let reason = format!("A name that the file declares more than once may name a module: {first}");
            return Outcome::Unknown(reason);
        }
        match bound {
            Some(bindings) => {
                let binding = bindings[0];
                let at = lexical(frame, &binding.scope);
                let mut full = binding.names.clone();
                full.extend_from_slice(&names[1..]);
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
        hops: usize,
        globs: bool,
    ) -> Option<Outcome> {
        let first = &names[0];
        let primary = frame.krate.primary.as_ref();
        if *first == frame.krate.ident {
            let lib = primary.filter(|root| root.module != frame.root)?;
            return Some(self.follow(&lib.module, 0, &names[1..]));
        }
        let none = std::collections::BTreeSet::new();
        if classify(first, frame.krate, &none, false).is_some() || frame.globs.is_empty() {
            return None;
        }
        if !globs {
            let reason = format!("A use path starts with a name that a glob import may bring in: {first}");
            return Some(Outcome::Unknown(reason));
        }
        for glob in &frame.globs {
            let at = lexical(frame, &glob.scope);
            match self.path(frame, &glob.names, glob.absolute, (&at, false), hops + 1) {
                Outcome::None => {}
                Outcome::Unknown(reason) => {
                    return Some(Outcome::Unknown(format!(
                        "A glob import may bring in {first}: {reason}"
                    )));
                }
                Outcome::Edge(edge) if edge.symbol.is_none() => {
                    let Some(target) = self.frames.get(edge.module.as_str()) else {
                        continue;
                    };
                    let place = (edge.lexical.as_str(), true);
                    match self.bare(target, names, place, hops + 1, true) {
                        Outcome::None => {}
                        found => return Some(found),
                    }
                }
                Outcome::Edge(_) => {}
            }
        }
        None
    }
}

#[cfg(test)]
#[path = "modules_tests.rs"]
mod tests;
