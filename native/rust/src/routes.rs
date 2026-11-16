// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The publication route of a name (AD-604): each module that publishes the name on the way from
//! the module that a path names to the module that defines it, as `module.name` hops.
//!
//! Each hop is true: the path, or the `use` leaf of the hop before it, names that name in that
//! module, and rustc resolved it. The route is complete only when each step is certain, by the
//! rules of AD-544 (`cross_outcome`): no attribute can swap the file of the module, the file
//! declares the name once (in any namespace, at any depth), no macro call in item place can add a
//! declaration, and the name is a definition of the module or the one module-level `use` leaf
//! that binds it with no attribute that can remove it. A definition ends the route, and so does a
//! leaf into a crate outside the workspace, which the scan does not read. At any other step (a
//! glob or a macro may give the name, a leaf that names a module, the step limit) the route stops
//! and is not complete: a later hop may follow. An item of an inline module has no hop, because
//! a hop names a file module.

use crate::definitions::Owner;
use crate::modules::{Frame, Index, Outcome, MAX_HOPS};
use crate::resolve::{classify, Found, Named};
use crate::scan::{Reference, Via};

/// The hops of a route, and whether the scan proves each step to its end.
pub(crate) struct Route {
    pub hops: Vec<String>,
    pub complete: bool,
}

impl Route {
    /// No route: the import names no item, or names it where no hop can stand.
    pub(crate) fn none() -> Self {
        Route {
            hops: Vec::new(),
            complete: true,
        }
    }
}

/// Where a `use` leaf takes a name.
enum Next {
    /// A name of a module of the workspace: its lexical module and the name there.
    Item(String, String),
    /// A crate that the scan does not read.
    Outside,
}

/// The route of `name` in the lexical module `at`.
pub(crate) fn route(index: &Index<'_>, at: &str, name: &str) -> Route {
    let mut hops = Vec::new();
    let (mut at, mut name) = (at.to_owned(), name.to_owned());
    let stop = |hops: Vec<String>, complete: bool| Route { hops, complete };
    loop {
        let Some(frame) = index.file_of(&at).and_then(|file| index.frame(file)) else {
            return stop(hops, false);
        };
        if frame.module.module != at || hops.len() > MAX_HOPS {
            return stop(hops, false);
        }
        hops.push(format!("{at}.{name}"));
        let scan = &frame.module.scan;
        let opaque = frame.module.gated && frame.module.gates.is_none();
        if opaque || scan.module_macros || scan.counts.get(&name) != Some(&1) {
            return stop(hops, false);
        }
        let defined = scan.definitions.iter().any(|d| {
            d.name == name && d.owner == Owner::Module && frame.lexical_at(&d.scope) == at
        });
        if defined {
            return stop(hops, true);
        }
        let [leaf] = frame.bound(&name) else {
            return stop(hops, false);
        };
        if scan.conditional_bindings.contains(&name)
            || !matches!(leaf.via, Via::Use { block: false, .. })
            || frame.lexical_at(&leaf.scope) != at
        {
            return stop(hops, false);
        }
        match next(index, frame, leaf) {
            Some(Next::Item(module, item)) => (at, name) = (module, item),
            Some(Next::Outside) => return stop(hops, true),
            None => return stop(hops, false),
        }
    }
}

/// The module and the name that a `use` leaf of `frame` names, by the rules of the edges: a
/// first segment that names a crate is that crate, any other path goes to the module resolver.
fn next(index: &Index<'_>, frame: &Frame<'_>, leaf: &Reference) -> Option<Next> {
    let first = leaf.names.first()?;
    let alias = index.is_alias(&frame.module.module, first);
    let found = classify(
        first,
        frame.krate(),
        &frame.module.scan.shadows,
        leaf.absolute,
    )
    .filter(|_| !alias);
    let outcome = match found {
        Some(Found::Edge(Named::Package(package))) => {
            let root = &index.workspace().primary_of(&package)?.module;
            index.reach(root, leaf.names.get(1..)?)
        }
        Some(Found::Edge(Named::Registry(_) | Named::Sysroot(_))) => {
            return Some(Next::Outside);
        }
        Some(Found::Shadowed) => return None,
        None => index.resolve(frame, leaf),
    };
    match outcome {
        Outcome::Edge(edge) => {
            let item = edge.symbol.filter(|name| !name.is_empty())?;
            // The item must be the last segment: `use a::T::V` names a variant of `T`.
            (leaf.names.last() == Some(&item)).then_some(Next::Item(edge.lexical, item))
        }
        Outcome::None | Outcome::Unknown(_) => None,
    }
}
