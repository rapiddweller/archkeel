// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trait that a glob brings in (#953, AD-357): `use super::*;` in `a` takes the `use b::T;` of
//! its parent, and `x.m()` in `a` may then call a method of `T`. The module of `T` gets a pair gap
//! when `a` calls a method of `T`, or any method when the scan does not know what `T` is. This file
//! also writes each pair gap (`reached_gap`), for itself and for `impl_edges.rs`.

use std::collections::{BTreeSet, HashSet};

use archkeel_facts::ids::EvidenceId;
use archkeel_facts::ImportFact;

use crate::builder::Builder;
use crate::crates::{Root, Workspace};
use crate::definitions::{Access, Form, Member, MethodCall, Owner};
use crate::modules::{inside, Edge, Frame, Index, Outcome, TypeOf};
use crate::resolve::{classify, Found, Named};
use crate::scan::{Reference, Via};
use crate::tree::Module;

/// One module, its method calls and the module pairs that an edge joins.
pub(crate) struct Reached<'a> {
    pub(crate) index: &'a Index<'a>,
    pub(crate) module: &'a Module,
    pub(crate) calls: &'a [MethodCall],
    pub(crate) edges: &'a HashSet<(u32, u32)>,
}

/// Whether `edges` already joins `source -> target`, without allocating strings.
pub(crate) fn has_edge(
    builder: &Builder,
    edges: &HashSet<(u32, u32)>,
    source: &str,
    target: &str,
) -> bool {
    builder
        .find_text(source)
        .zip(builder.find_text(target))
        .is_some_and(|pair| edges.contains(&pair))
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
        let source: &str = &reached.module.module;
        let at = (String::as_str(&reached.module.rel), &call.site);
        if source != target && has_edge(self, reached.edges, source, target) {
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
    edges: &HashSet<(u32, u32)>,
    (source, target): (&str, &str),
    (rel, site): (&str, &crate::site::Site),
    why: &str,
    dispatch: Option<archkeel_facts::vocab::ResolutionDimension>,
    no_name_route: bool,
) {
    if source == target || has_edge(builder, edges, source, target) {
        return;
    }
    if builder.pair_already_reported(source, target, no_name_route) {
        return;
    }
    let evidence = builder.cite(rel, site);
    let slot = builder.pair_gap(why, &evidence, (source, target), dispatch, no_name_route);
    builder.mark_gapped(source, target, slot);
}

/// Exact import binding sites whose recorded routes reach their named types.
pub(crate) struct NameRoutes {
    sites: BTreeSet<(String, i64, i64)>,
    macro_shadow: bool,
}

impl NameRoutes {
    pub(crate) fn of(builder: &Builder, macro_shadow: bool) -> Self {
        let sites = builder.imports.iter().filter_map(|record| {
            let (ImportFact::Import(data) | ImportFact::Reexport(data)) = &record.data else {
                return None;
            };
            if !data.symbols_known || data.route_complete == Some(false) || data.symbol.is_none() {
                return None;
            }
            let [id] = &record.evidence_ids[..] else {
                return None;
            };
            let site = builder.evidence.get(EvidenceId::as_str(id))?;
            Some((site.file.clone(), site.line, site.column))
        });
        Self {
            sites: sites.collect(),
            macro_shadow,
        }
    }

    pub(crate) fn covers(&self, index: &Index<'_>, frame: &Frame<'_>, path: &Reference) -> bool {
        let [receiver, _] = path.names.as_slice() else {
            return false;
        };
        let [leaf] = frame.bound(receiver) else {
            return false;
        };
        let module = frame.module;
        let site = (path.site.line, path.site.column);
        !path.absolute
            && path.in_macro.is_none()
            && matches!(path.via, Via::Path)
            && !module.scan.generic_paths.contains(&site)
            && !module.scan.body_macros
            && !module.scan.module_macros
            && !(module.scan.placed_macros && self.macro_shadow)
            && (!module.gated || module.gates.is_some())
            && module.scan.counts.get(receiver) == Some(&1)
            && !module.scan.conditional_bindings.contains(receiver)
            && matches!(leaf.via, Via::Use { block: false, .. })
            && !leaf.absolute
            && frame.lexical_at(&path.scope) == frame.lexical_at(&leaf.scope)
            && self
                .sites
                .contains(&(module.rel.clone(), leaf.site.line, leaf.site.column))
            && matches!(
                index.type_of(frame, &path.scope, std::slice::from_ref(receiver)),
                TypeOf::Known(..)
            )
    }
}

/// A member of an inherent `impl` block: foreign when outside the file of its type, else owned.
pub(crate) struct Foreign<'a> {
    pub(crate) module: &'a Module,
    /// The lexical module of the block.
    pub(crate) lexical: String,
    pub(crate) ty: TypeOf,
    pub(crate) member: &'a Member,
    /// The block has only inert attributes and no type parameter (`ImplBlock::exact`).
    pub(crate) exact: bool,
}

/// Whether a call at `at` in `caller` can reach the member (`pub(in path)` counts as the crate).
pub(crate) fn visible(
    workspace: &Workspace,
    (caller, at): (&Module, &str),
    call: &MethodCall,
    member: &Foreign<'_>,
) -> bool {
    let arity = call.arity.is_none_or(|count| count == member.member.arity);
    if !(call.path || member.member.receiver && arity) {
        return false;
    }
    let same_crate = caller.crate_index == member.module.crate_index;
    match &member.member.access {
        // A private member is visible in its module and below it (#1571).
        Access::Private => same_crate && inside(at, &member.lexical),
        Access::Package(text) if text == "pub(super)" => {
            let parent = member.lexical.rsplit_once('.').map_or("", |(up, _)| up);
            inside(at, parent)
        }
        Access::Package(_) => same_crate,
        Access::Public => same_crate || depends(workspace, caller, member.module),
    }
}

/// Whether the written type of a path `T::m` can name the type of a member of the file of its type.
pub(crate) fn names_type(
    caller: &Module,
    call: &MethodCall,
    ty: &TypeOf,
    aliases: &BTreeSet<&str>,
) -> bool {
    let (Some(owner), TypeOf::Known(_, name)) = (&call.owner, ty) else {
        return true;
    };
    *owner == *name
        || aliases.contains(String::as_str(owner))
        || caller.scan.body_macros
        || caller.scan.module_macros
}

/// Dot-prefix module ancestors indexed by `Builder` interned id (#1942).
pub(crate) fn build_ancestors(builder: &Builder) -> Vec<Vec<u32>> {
    let count = builder.interned_count();
    let mut table = Vec::with_capacity(count);
    for raw in 0..count {
        let id = u32::try_from(raw).unwrap_or(u32::MAX);
        let mut parents = Vec::new();
        let mut rest = builder.interned_text(id);
        while let Some((prefix, _)) = rest.rsplit_once('.') {
            if let Some(parent) = builder.find_text(prefix) {
                parents.push(parent);
            }
            rest = prefix;
        }
        table.push(parents);
    }
    table
}

/// Compact bitset indexed by interned `u32` module identifiers (#1942).
pub(crate) struct BitSet {
    pub(crate) words: Vec<u64>,
}

impl BitSet {
    pub(crate) fn new(bits: usize) -> Self {
        Self {
            words: vec![0; bits.div_ceil(64)],
        }
    }

    pub(crate) fn set(&mut self, id: u32) -> bool {
        let index = usize::try_from(id).unwrap_or(usize::MAX);
        let Some(word) = self.words.get_mut(index / 64) else {
            return false;
        };
        let mask = 1u64 << (index % 64);
        let fresh = (*word & mask) == 0;
        *word |= mask;
        fresh
    }

    pub(crate) fn has_bit(&self, id: u32) -> bool {
        let index = usize::try_from(id).unwrap_or(usize::MAX);
        self.words
            .get(index / 64)
            .is_some_and(|word| (*word & (1u64 << (index % 64))) != 0)
    }

    pub(crate) fn has_bits(&self) -> bool {
        self.words.iter().any(|&word| word != 0)
    }
}

/// The names of a module that may stand for another type in a path: type aliases and `use` renames.
pub(super) fn aliases(module: &Module) -> impl Iterator<Item = &str> {
    let scan = &module.scan;
    let aliases = (scan.definitions.iter())
        .filter(|definition| definition.form == Form::Alias)
        .map(|definition| String::as_str(&definition.name));
    let renames = scan.references.iter().filter_map(|r| match &r.via {
        Via::Use {
            binding: Some(binding),
            ..
        } if r.names.last() != Some(binding) => Some(String::as_str(binding)),
        _ => None,
    });
    aliases.chain(renames)
}

pub(crate) fn build_ingress(builder: &Builder, index: &Index<'_>, modules: &[Module]) -> BitSet {
    let mut names = builder.opaque_values.clone();
    names.extend(
        modules
            .iter()
            .filter(|module| module.scan.has_static)
            .map(|module| module.module.clone()),
    );
    let count = builder.interned_count();
    let mut bits = BitSet::new(count);
    if names.is_empty() {
        return bits;
    }
    for raw in 0..count {
        let id = u32::try_from(raw).unwrap_or(u32::MAX);
        let module = builder.interned_text(id);
        if names.contains(index.file_of(module).unwrap_or(module)) {
            bits.set(id);
        }
    }
    bits
}
