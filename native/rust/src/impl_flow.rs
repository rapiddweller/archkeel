// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The value flow of a method call into the file of a type (#1571).
//!
//! A call `x.m()` whose receiver no proof resolves may reach a member `m` in the file of its type
//! `S` in `c`. The caller can hold a value of `S` only through a chain of dependencies to code that
//! names `S`, and that code has an edge into `c` (or is `c`). So the call gives the pair gap
//! `a -> c` only when `c` is reachable from `a` over the edges and the pair gaps of the reply. A
//! module with a gap that names no target can depend on any module, so reaching one keeps every
//! candidate of the caller; a gap of the whole workspace keeps each candidate. Each gap that this
//! adds is a new step of the graph, so the check runs until no candidate changes.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

use crate::builder::Builder;
use crate::crates::Workspace;
use crate::definitions::{Access, Form, Member, MethodCall};
use crate::impl_globs::depends;
use crate::impl_globs::once_gap;
use crate::modules::inside;
use crate::modules::TypeOf;
use crate::scan::Via;
use crate::site::Site;
use crate::tree::Module;

/// A gap that waits for the value flow: a call in `source` (in the file `rel`, at `site`) may
/// reach a member of a type in `target`.
pub(super) struct Pending {
    pub(super) source: String,
    pub(super) rel: String,
    pub(super) site: Site,
    pub(super) target: String,
    pub(super) reason: String,
}

/// Give each pending gap whose target its source can reach.
pub(super) fn settle(builder: &mut Builder, mut open: Vec<Pending>) {
    while !open.is_empty() {
        let graph = Graph::of(builder);
        let mut reach: BTreeMap<String, Reach> = BTreeMap::new();
        let (ready, waiting): (Vec<_>, Vec<_>) = open.into_iter().partition(|pending| {
            let found = reach
                .entry(pending.source.clone())
                .or_insert_with(|| graph.reach(&pending.source));
            // A type of an inline module of the file is reached through that module.
            let below = format!("{}.", pending.target);
            found.any
                || (found.modules.iter())
                    .any(|module| *module == pending.target || module.starts_with(&below))
        });
        if ready.is_empty() {
            return;
        }
        for pending in &ready {
            let pair = (pending.source.as_str(), pending.target.as_str());
            let at = (pending.rel.as_str(), &pending.site);
            once_gap(builder, &graph.edges, pair, at, &pending.reason);
        }
        open = waiting;
    }
}

/// A member of an inherent `impl` block: in `Members::foreign` a block that is not in the file of
/// its type, in `Members::owned` a block in that file.
pub(super) struct Foreign<'a> {
    pub(super) module: &'a Module,
    /// The lexical module of the block.
    pub(super) lexical: String,
    pub(super) ty: TypeOf,
    pub(super) member: &'a Member,
    /// The block has only inert attributes and no type parameter (`ImplBlock::exact`).
    pub(super) exact: bool,
}

/// Whether a call at `at` in `caller` can reach the member: `x.m(..)` reaches only a member with a
/// `self` parameter and as many other parameters as the call has arguments (Rust has no overloads).
/// `pub(in path)` counts as the crate.
pub(super) fn visible(
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

/// The pending gaps of a call that no proof resolved: it may reach each visible member `m` in the
/// file of its type, because a field, a chain or a return value can give a value of that type
/// that the caller does not name.
pub(super) fn own_candidates(
    workspace: &Workspace,
    (module, at): (&Module, &str),
    call: &MethodCall,
    (owned, aliases): (&[Foreign<'_>], &BTreeSet<&str>),
    keep: Keep<'_>,
) -> Vec<Pending> {
    owned
        .iter()
        .filter(|block| keep(block))
        .filter(|block| names_type(module, call, &block.ty, aliases))
        .filter(|block| visible(workspace, (module, at), call, block))
        .map(|block| {
            let target = block.module.module.clone();
            let reason = format!(
                "A method call may reach the method {} of a type in its own file {target}",
                call.name
            );
            Pending {
                source: module.module.clone(),
                rel: module.rel.clone(),
                site: call.site.clone(),
                target,
                reason,
            }
        })
        .collect()
}

/// Whether the type of a receiver lets a call reach the members of a block of this type (#1571).
pub(super) type Keep<'k> = &'k dyn Fn(&Foreign<'_>) -> bool;

/// Whether the written type of a path `T::m` can name the type of a member of the file of its type:
/// `T` is its name, an alias or a renamed `use`, or a macro of the caller can give any name. A
/// method call names no type.
fn names_type(caller: &Module, call: &MethodCall, ty: &TypeOf, aliases: &BTreeSet<&str>) -> bool {
    let (Some(owner), TypeOf::Known(_, name)) = (&call.owner, ty) else {
        return true;
    };
    *owner == *name
        || aliases.contains(owner.as_str())
        || caller.scan.body_macros
        || caller.scan.module_macros
}

/// The names of a module that may stand for another type in a path: each type alias and each
/// name that a `use` renames.
pub(super) fn aliases(module: &Module) -> impl Iterator<Item = &str> {
    let scan = &module.scan;
    let aliases = (scan.definitions.iter())
        .filter(|definition| definition.form == Form::Alias)
        .map(|definition| definition.name.as_str());
    let renames = scan.references.iter().filter_map(|r| match &r.via {
        Via::Use {
            binding: Some(binding),
            ..
        } if r.names.last() != Some(binding) => Some(binding.as_str()),
        _ => None,
    });
    aliases.chain(renames)
}

/// What a module reaches: each module, or any module.
struct Reach {
    any: bool,
    modules: BTreeSet<String>,
}

/// The dependencies of the reply: the edges, the pair gaps and the modules that may depend on any
/// module.
struct Graph {
    edges: BTreeSet<(String, String)>,
    next: BTreeMap<String, Vec<String>>,
    open: BTreeSet<String>,
    anywhere: bool,
}

impl Graph {
    fn of(builder: &Builder) -> Self {
        let edges: BTreeSet<(String, String)> = (builder.imports.iter())
            .map(|record| {
                let data = record.data.data();
                let source = data.source_module.as_str().to_owned();
                (source, data.target_module.as_str().to_owned())
            })
            .collect();
        let mut next: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for (source, target) in edges.iter().chain(&builder.gapped) {
            next.entry(source.clone()).or_default().push(target.clone());
        }
        let mut open = BTreeSet::new();
        let mut anywhere = false;
        for record in builder.gaps.values() {
            let data = record.data.data();
            if data.source_module.is_some() {
                continue;
            }
            match data.module.as_ref().map(|module| module.as_str()) {
                Some(module) if !module.is_empty() => drop(open.insert(module.to_owned())),
                _ => anywhere = true,
            }
        }
        Graph {
            edges,
            next,
            open,
            anywhere,
        }
    }

    fn reach(&self, source: &str) -> Reach {
        let mut modules = BTreeSet::new();
        let mut queue = VecDeque::from([source.to_owned()]);
        while let Some(module) = queue.pop_front() {
            if self.anywhere || self.open.contains(&module) {
                return Reach { any: true, modules };
            }
            let next = self.next.get(&module).into_iter().flatten();
            for target in next.filter(|target| modules.insert((*target).clone())) {
                queue.push_back(target.clone());
            }
        }
        Reach {
            any: false,
            modules,
        }
    }
}
