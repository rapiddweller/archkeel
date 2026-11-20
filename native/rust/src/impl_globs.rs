// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trait that a glob brings in (#953, AD-357): `use super::*;` in `a` takes the `use b::T;` of
//! its parent, and `x.m()` in `a` may then call a method of `T`. The module of `T` gets a pair gap
//! when `a` calls a method of `T`, or any method when the scan does not know what `T` is. This file
//! also writes each pair gap (`reached_gap`), for itself and for `impl_edges.rs`.

use std::collections::BTreeSet;

use crate::builder::Builder;
use crate::crates::{Root, Workspace};
use crate::definitions::{Form, MethodCall, Owner};
use crate::modules::{Edge, Frame, Index, Outcome};
use crate::resolve::{classify, Found, Named};
use crate::scan::Reference;
use crate::tree::Module;

/// One module, its method calls and the module pairs that an edge joins.
pub(crate) struct Reached<'a> {
    pub(crate) index: &'a Index<'a>,
    pub(crate) module: &'a Module,
    pub(crate) calls: &'a [MethodCall],
    pub(crate) edges: &'a BTreeSet<(String, String)>,
}

/// The deepest chain of globs that the scan follows.
const MAX_GLOBS: usize = 8;

/// The root of the crate of the workspace that the first name of a path names.
pub(crate) fn workspace_root<'w>(
    workspace: &'w Workspace,
    module: &Module,
    reference: &Reference,
) -> Option<&'w Root> {
    let krate = workspace.crates.get(module.crate_index)?;
    let found = classify(
        &reference.root,
        krate,
        &module.scan.shadows,
        reference.absolute,
    )?;
    match found {
        Found::Edge(Named::Package(package)) => workspace.primary_of(&package),
        _ => None,
    }
}

/// Whether a path may start at another crate of the workspace: by the name of the crate, by a
/// `use` leaf from it, or by a name that the file does not declare and a glob from it may bring in.
pub(crate) fn crate_path(workspace: &Workspace, frame: &Frame<'_>, reference: &Reference) -> bool {
    let module = frame.module;
    let from_crate = |leaf: &&Reference| workspace_root(workspace, module, leaf).is_some();
    let undeclared = !module.scan.counts.contains_key(&reference.root);
    reference.names.len() > 1
        && (workspace_root(workspace, module, reference).is_some()
            || frame.bound(&reference.root).iter().any(from_crate)
            || (undeclared && frame.globs().any(|glob| from_crate(&glob))))
}

/// The module and the name that a `use` leaf binds, in this crate or another of the workspace.
/// A leaf that the scan cannot resolve is a gap of its own module already.
fn leaf_target(
    workspace: &Workspace,
    index: &Index<'_>,
    frame: &Frame<'_>,
    leaf: &Reference,
) -> Option<Edge> {
    let outcome = match index.resolve(frame, leaf) {
        Outcome::None => {
            let root = workspace_root(workspace, frame.module, leaf)?;
            index.reach(&root.module, leaf.names.get(1..)?)
        }
        found => found,
    };
    match outcome {
        Outcome::Edge(edge) => Some(edge),
        _ => None,
    }
}

/// The methods of the trait `name` of a lexical module. `None` when the module defines no item of
/// that name (the kind is unknown), and no method when it defines the name as no trait.
fn trait_methods(index: &Index<'_>, lexical: &str, name: &str) -> Option<BTreeSet<String>> {
    let frame = index.frame(index.file_of(lexical)?)?;
    let here = frame.module.scan.definitions.iter();
    let defined: Vec<_> = here
        .filter(|d| frame.lexical_at(&d.scope) == lexical)
        .collect();
    let named: Vec<_> = (defined.iter())
        .filter(|d| d.name == name && d.owner == Owner::Module)
        .collect();
    if named.is_empty() {
        return None;
    }
    let owner = Owner::Trait(name.to_owned());
    let is_trait = named.iter().any(|d| d.form == Form::Trait);
    Some(
        (defined.iter().filter(|d| is_trait && d.owner == owner))
            .map(|d| d.name.clone())
            .collect(),
    )
}

/// The lexical modules, with their files, whose names the globs of `module` bring in, also
/// through the globs of those modules. `false` when the chain is too long to follow.
fn globbed(index: &Index<'_>, module: &Module) -> (Vec<(String, String)>, bool) {
    let mut found: Vec<(String, String)> = Vec::new();
    let mut queue = vec![(module.module.clone(), None::<String>, 0)];
    while let Some((file, lexical, depth)) = queue.pop() {
        let Some(frame) = index.frame(&file) else {
            continue;
        };
        let globs = frame.globs();
        let own = globs.filter(|glob| {
            lexical
                .as_ref()
                .is_none_or(|at| frame.lexical_at(&glob.scope) == *at)
        });
        for glob in own {
            let Outcome::Edge(edge) = index.resolve(frame, glob) else {
                continue;
            };
            if edge.symbol.is_some() || found.iter().any(|(at, _)| *at == edge.lexical) {
                continue;
            }
            if depth >= MAX_GLOBS {
                return (found, false);
            }
            found.push((edge.lexical.clone(), edge.module.clone()));
            queue.push((edge.module, Some(edge.lexical), depth + 1));
        }
    }
    (found, true)
}

/// Whether the crate of `caller` reaches the crate of `target` through its dependencies. A value
/// of a crate that the caller reaches only through another crate can carry a method call into it
/// (review B2 of #1121), so the walk follows the dependencies of each crate of the workspace.
pub(crate) fn depends(workspace: &Workspace, caller: &Module, target: &Module) -> bool {
    let (Some(from), Some(to)) = (
        workspace.crates.get(caller.crate_index),
        workspace.crates.get(target.crate_index),
    ) else {
        return false;
    };
    let mut seen: BTreeSet<&str> = BTreeSet::new();
    let mut work: Vec<&str> = from
        .manifest
        .dependencies
        .values()
        .map(String::as_str)
        .collect();
    while let Some(name) = work.pop() {
        if name == to.ident {
            return true;
        }
        if !seen.insert(name) {
            continue;
        }
        let next = workspace.crates.iter().filter(|krate| krate.ident == name);
        work.extend(
            next.flat_map(|krate| krate.manifest.dependencies.values().map(String::as_str)),
        );
    }
    false
}

impl Builder {
    /// A pair gap for each trait of another module that a glob of the module may bring in.
    pub(crate) fn glob_trait_gaps(&mut self, workspace: &Workspace, reached: &Reached<'_>) {
        if reached.calls.is_empty() {
            return;
        }
        let (index, module) = (reached.index, reached.module);
        let (globbed, whole) = globbed(index, module);
        if !whole {
            let reason = "A chain of glob imports is too long to follow";
            self.gap(reason, None, &module.module);
        }
        for (lexical, file) in globbed {
            let Some(frame) = index.frame(&file) else {
                continue;
            };
            let leaves = frame.leaves();
            for leaf in leaves.filter(|leaf| frame.lexical_at(&leaf.scope) == lexical) {
                self.leaf_gap(workspace, reached, frame, leaf);
            }
        }
    }

    fn leaf_gap(
        &mut self,
        workspace: &Workspace,
        reached: &Reached<'_>,
        frame: &Frame<'_>,
        leaf: &Reference,
    ) {
        let Some(edge) = leaf_target(workspace, reached.index, frame, leaf) else {
            return;
        };
        let Some(name) = edge.symbol.as_deref() else {
            return;
        };
        let methods = trait_methods(reached.index, &edge.lexical, name);
        let reason = format!(
            "A method call may use the trait {name} that a glob brings in from {}",
            edge.module
        );
        let calls = reached.calls.iter();
        for call in calls.filter(|c| methods.as_ref().is_none_or(|m| m.contains(&c.name))) {
            self.reached_gap(reached, call, &edge.module, &reason, false);
        }
    }

    /// A call holds a named site beside a known edge, or a gap for an unproved edge.
    pub(crate) fn reached_gap(
        &mut self,
        reached: &Reached<'_>,
        call: &MethodCall,
        target: &str,
        why: &str,
        no_name_route: bool,
    ) {
        let source = reached.module.module.as_str();
        let at = (reached.module.rel.as_str(), &call.site);
        if source != target
            && reached
                .edges
                .contains(&(source.to_owned(), target.to_owned()))
        {
            self.named_site((source, target), at, why, no_name_route);
            return;
        }
        once_gap(
            self,
            reached.edges,
            (source, target),
            at,
            why,
            None,
            no_name_route,
        );
    }
}

/// The pair gap `source -> target` at a site, once, unless an edge joins the pair.
pub(crate) fn once_gap(
    builder: &mut Builder,
    edges: &BTreeSet<(String, String)>,
    (source, target): (&str, &str),
    (rel, site): (&str, &crate::site::Site),
    why: &str,
    dispatch: Option<archkeel_facts::vocab::ResolutionDimension>,
    no_name_route: bool,
) {
    let pair = (source.to_owned(), target.to_owned());
    if source == target || edges.contains(&pair) {
        return;
    }
    if builder.pair_already_reported(&pair, no_name_route) {
        return;
    }
    let evidence = builder.cite(rel, site);
    let id = builder.pair_gap(why, &evidence, (source, target), dispatch, no_name_route);
    builder.gapped.insert(pair, id);
}
