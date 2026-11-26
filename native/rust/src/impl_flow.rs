// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The value flow of a method call into the file of a type (#1571).
//!
//! A call `x.m()` whose receiver no proof resolves may reach a member `m` in the file of its type
//! `S` in `c`. The caller can hold a value of `S` only through a chain of dependencies to code that
//! names `S`, and that code has an edge into `c` (or is `c`). Each gap that this adds is a new step
//! of the graph, so the check runs until no candidate changes.

use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

use archkeel_facts::vocab::ResolutionDimension;

use crate::builder::Builder;
use crate::crates::Workspace;
use crate::definitions::MethodCall;
pub(super) use crate::impl_globs::Foreign;
use crate::impl_globs::{build_ancestors, build_ingress, names_type, once_gap, visible, BitSet};
use crate::modules::Index;
use crate::site::Site;
use crate::tree::Module;
use crate::type_reach_filter::Filter;

/// One trait or `Drop` home settled lazily without `homes x callers` materialization (#1942).
pub(super) struct LazyHome {
    pub(super) target: u32,
    pub(super) crate_index: usize,
    pub(super) rel: String,
    pub(super) site: Site,
    pub(super) reason: String,
}

/// Precomputed lazy trait/drop homes and crate dependency matrix (#1942).
pub(super) struct LazyHomes {
    pub(super) trait_homes: Vec<LazyHome>,
    pub(super) drop_homes: Vec<LazyHome>,
    pub(super) crate_deps: Vec<Vec<bool>>,
}

/// Compact pending candidate waiting for value-flow settlement (#1942).
pub(super) struct Pending {
    source: u32,
    site: u32,
    target: u32,
    reason: u32,
    erased: bool,
    execution: bool,
    no_name_route: bool,
}

/// Interned candidate pool sharing `Builder`'s string table (#1942).
pub(super) struct PendingPool {
    sites: Vec<(u32, Site)>,
    site_index: HashMap<(u32, i64, i64, i64), u32>,
    items: Vec<Pending>,
}

impl PendingPool {
    pub(super) fn new() -> Self {
        Self {
            sites: Vec::new(),
            site_index: HashMap::new(),
            items: Vec::new(),
        }
    }

    fn intern_site(&mut self, builder: &mut Builder, rel: &str, site: &Site) -> u32 {
        let rel_id = builder.intern_text(rel);
        let key = (rel_id, site.line, site.end_line, site.column);
        if let Some(&id) = self.site_index.get(&key) {
            return id;
        }
        let id = u32::try_from(Vec::len(&self.sites)).unwrap_or(u32::MAX);
        self.sites.push((rel_id, site.clone()));
        self.site_index.insert(key, id);
        id
    }

    pub(super) fn push(
        &mut self,
        builder: &mut Builder,
        (source, target): (&str, &str),
        (rel, site): (&str, &Site),
        reason: &str,
        (erased, execution, no_name_route): (bool, bool, bool),
    ) {
        let site = self.intern_site(builder, rel, site);
        self.items.push(Pending {
            source: builder.intern_text(source),
            site,
            target: builder.intern_text(target),
            reason: builder.intern_text(reason),
            erased,
            execution,
            no_name_route,
        });
    }

    /// A candidate of a written call that the compiler resolved to another module: it never reaches the target.
    /// It leaves before the named pairs are read, so a pair that only such calls named is not named (AD-1185).
    fn elsewhere(&self, builder: &Builder, reach: Option<&Filter<'_>>, pending: &Pending) -> bool {
        let Some((rel, site)) = self.site_of(pending.site) else {
            return false;
        };
        let target = builder.interned_text(pending.target);
        let at = (builder.interned_text(rel), site.line, site.column);
        !pending.execution && Filter::resolved_elsewhere(reach, target, at)
    }

    fn site_of(&self, id: u32) -> Option<(u32, &Site)> {
        let (rel, site) = self.sites.get(usize::try_from(id).ok()?)?;
        Some((*rel, site))
    }
}

struct CallerEntry {
    id: u32,
    crate_index: usize,
}

struct FlowContext<'a> {
    edges: HashSet<(u32, u32)>,
    ancestors: Vec<Vec<u32>>,
    callers: Vec<CallerEntry>,
    crate_deps: &'a [Vec<bool>],
    named: HashSet<(u32, u32)>,
    ingress: BitSet,
    pool: &'a PendingPool,
    /// The compiler type-reach filter (AD-1047), when the scan has facts.
    reach: Option<&'a Filter<'a>>,
}

/// Keep known origins first. An erased value can also come from shared storage or unread code.
pub(super) fn settle(
    builder: &mut Builder,
    mut pool: PendingPool,
    (index, modules): (&Index<'_>, &[Module]),
    homes: &LazyHomes,
) {
    let callers: Vec<CallerEntry> = modules
        .iter()
        .map(|module| CallerEntry {
            id: builder.intern_text(&module.module),
            crate_index: module.crate_index,
        })
        .collect();
    let facts = std::mem::take(&mut builder.type_reach);
    let known: BTreeSet<String> = modules.iter().map(|m| m.module.clone()).collect();
    let filter = (!facts.is_empty()).then(|| Filter::new(&facts, &known));
    if filter.as_ref().is_some_and(|f| f.matched() == 0) {
        builder.gap(Filter::no_module(), None, "");
    }
    builder.reach_used = filter.as_ref().is_some_and(|f| f.matched() > 0);
    let mut open = std::mem::take(&mut pool.items);
    open.retain(|p| !pool.elsewhere(builder, filter.as_ref(), p));
    let mut ctx = FlowContext {
        edges: import_edges(builder),
        ancestors: build_ancestors(builder),
        callers,
        crate_deps: &homes.crate_deps,
        named: named_pairs(&open),
        ingress: BitSet::new(builder.interned_count()),
        pool: &pool,
        reach: filter.as_ref(),
    };
    builder.selected_edges(index, modules, ctx.reach);
    open = settle_pending(builder, open, &ctx, &homes.trait_homes, false);
    if homes.drop_homes.is_empty() {
        return;
    }
    let ingress = build_ingress(builder, index, modules);
    if !ingress.has_bits() {
        return;
    }
    ctx.ancestors = build_ancestors(builder);
    ctx.named = named_pairs(&open);
    ctx.ingress = ingress;
    drop(settle_pending(builder, open, &ctx, &homes.drop_homes, true));
}

fn named_pairs(open: &[Pending]) -> HashSet<(u32, u32)> {
    open.iter()
        .filter(|pending| !pending.execution)
        .map(|pending| (pending.source, pending.target))
        .collect()
}

fn settle_pending(
    builder: &mut Builder,
    mut open: Vec<Pending>,
    ctx: &FlowContext<'_>,
    homes: &[LazyHome],
    erased_homes: bool,
) -> Vec<Pending> {
    let size = builder.interned_count();
    loop {
        let graph = Graph::of(builder, &ctx.edges, size);
        let mut reach: Vec<Option<Reach>> = (0..size).map(|_| None).collect();
        let (ready, waiting): (Vec<_>, Vec<_>) = open.into_iter().partition(|pending| {
            let found = reach_of(&mut reach, pending.source, &graph, ctx);
            if pending.erased {
                found.any || found.ingress
            } else {
                found.any || found.targets.has_bit(pending.target)
            }
        });
        for pending in &ready {
            emit_pending(builder, pending, ctx);
        }
        let added = !homes.is_empty()
            && ctx.callers.iter().fold(false, |any, caller| {
                any | settle_caller_homes(
                    builder,
                    &mut reach,
                    &graph,
                    ctx,
                    caller,
                    homes,
                    erased_homes,
                )
            });
        if ready.is_empty() && !added {
            return waiting;
        }
        open = waiting;
    }
}

fn reach_of<'r>(
    cache: &'r mut [Option<Reach>],
    source: u32,
    graph: &Graph,
    ctx: &FlowContext<'_>,
) -> &'r Reach {
    let slot = usize::try_from(source).unwrap_or(0);
    if let Some(cell) = cache.get_mut(slot) {
        return cell.get_or_insert_with(|| graph.reach(source, &ctx.ancestors, &ctx.ingress));
    }
    &EMPTY_REACH
}

static EMPTY_REACH: Reach = Reach {
    any: false,
    ingress: false,
    targets: BitSet { words: Vec::new() },
};

fn emit_pending(builder: &mut Builder, pending: &Pending, ctx: &FlowContext<'_>) {
    let Some((rel_id, site)) = ctx.pool.site_of(pending.site) else {
        return;
    };
    let rel = builder.interned_text(rel_id).to_owned();
    let reason = builder.interned_text(pending.reason).to_owned();
    let source = builder.interned_text(pending.source).to_owned();
    let target = builder.interned_text(pending.target).to_owned();
    if !pending.execution
        && pending.source != pending.target
        && ctx.edges.contains(&(pending.source, pending.target))
    {
        builder.named_site(
            (&source, &target),
            (&rel, site),
            &reason,
            pending.no_name_route,
        );
        return;
    }
    if ctx.reach.is_some_and(|r| r.excluded(&source, &target)) {
        return;
    }
    let dimension = if pending.execution && !ctx.named.contains(&(pending.source, pending.target)) {
        ResolutionDimension::RuntimeEffects
    } else {
        ResolutionDimension::Imports
    };
    once_gap(
        builder,
        &ctx.edges,
        (&source, &target),
        (&rel, site),
        &reason,
        Some(dimension),
        pending.no_name_route,
    );
}

fn settle_caller_homes(
    builder: &mut Builder,
    reach: &mut [Option<Reach>],
    graph: &Graph,
    ctx: &FlowContext<'_>,
    caller: &CallerEntry,
    homes: &[LazyHome],
    erased: bool,
) -> bool {
    let mut added = false;
    for home in homes {
        let pair = (caller.id, home.target);
        if caller.id == home.target
            || ctx.edges.contains(&pair)
            || builder.gapped.contains_key(&pair)
        {
            continue;
        }
        if !erased && !crate_reaches(ctx.crate_deps, caller.crate_index, home.crate_index) {
            continue;
        }
        let found = reach_of(reach, caller.id, graph, ctx);
        let ready = if erased {
            found.any || found.ingress
        } else {
            found.any || found.targets.has_bit(home.target)
        };
        let (source, target) = (
            builder.interned_text(caller.id),
            builder.interned_text(home.target),
        );
        if !ready || ctx.reach.is_some_and(|r| r.excluded(source, target)) {
            continue;
        }
        let (source, target) = (source.to_owned(), target.to_owned());
        let dimension = if ctx.named.contains(&pair) {
            ResolutionDimension::Imports
        } else {
            ResolutionDimension::RuntimeEffects
        };
        once_gap(
            builder,
            &ctx.edges,
            (&source, &target),
            (&home.rel, &home.site),
            &home.reason,
            Some(dimension),
            true,
        );
        added = true;
    }
    added
}

/// Record pending gaps of an unresolved call directly into the compact candidate pool (#1942).
pub(super) fn push_own_candidates(
    builder: &mut Builder,
    pool: &mut PendingPool,
    workspace: &Workspace,
    (module, at): (&Module, &str),
    call: &MethodCall,
    (owned, aliases): (&[Foreign<'_>], &BTreeSet<&str>),
    (keep, no_name_route): (Keep<'_>, bool),
) {
    for block in owned
        .iter()
        .filter(|block| keep(block))
        .filter(|block| names_type(module, call, &block.ty, aliases))
        .filter(|block| visible(workspace, (module, at), call, block))
    {
        let target = block.module.module.as_str();
        let reason = format!(
            "A method call may reach the method {} of a type in its own file {target}",
            call.name
        );
        pool.push(
            builder,
            (&module.module, target),
            (&module.rel, &call.site),
            &reason,
            (false, false, no_name_route),
        );
    }
}

/// Whether the type of a receiver lets a call reach the members of a block of this type (#1571).
pub(super) type Keep<'k> = &'k dyn Fn(&Foreign<'_>) -> bool;

/// What a module reaches: each module (and its dot-prefix targets), or any module.
struct Reach {
    any: bool,
    ingress: bool,
    targets: BitSet,
}

/// Dense module adjacency graph over `Builder::strings` ids.
struct Graph {
    next: Vec<Vec<u32>>,
    open: BitSet,
    anywhere: bool,
}

fn import_edges(builder: &mut Builder) -> HashSet<(u32, u32)> {
    let imports = std::mem::take(&mut builder.imports);
    let mut edges = HashSet::new();
    for record in &imports {
        let data = record.data.data();
        let source = builder.intern_text(data.source_module.as_str());
        let target = builder.intern_text(data.target_module.as_str());
        edges.insert((source, target));
    }
    builder.imports = imports;
    edges
}

fn mark_open_gaps(builder: &Builder, open: &mut BitSet) -> bool {
    let mut anywhere = false;
    for record in builder.gaps.values() {
        let data = record.data.data();
        if data.source_module.is_some() {
            continue;
        }
        let module = data.module.as_ref().map(|m| m.as_str()).unwrap_or("");
        if module.is_empty() {
            anywhere = true;
        } else if let Some(id) = builder.find_text(module) {
            open.set(id);
        }
    }
    anywhere
}

fn mark_target_ancestors(targets: &mut BitSet, ancestors: &[Vec<u32>], target: u32) {
    if let Some(parents) = usize::try_from(target)
        .ok()
        .and_then(|slot| ancestors.get(slot))
    {
        for &parent in parents {
            targets.set(parent);
        }
    }
}

impl Graph {
    fn of(builder: &Builder, edges: &HashSet<(u32, u32)>, size: usize) -> Self {
        let mut next: Vec<Vec<u32>> = vec![Vec::new(); size];
        for &(source, target) in edges.iter().chain(builder.gapped.keys()) {
            if let Some(list) = usize::try_from(source).ok().and_then(|i| next.get_mut(i)) {
                list.push(target);
            }
        }
        let mut open = BitSet::new(size);
        let anywhere = mark_open_gaps(builder, &mut open);
        Self {
            next,
            open,
            anywhere,
        }
    }

    fn reach(&self, source: u32, ancestors: &[Vec<u32>], ingress: &BitSet) -> Reach {
        let size = Vec::len(&self.next);
        let mut visited = BitSet::new(size);
        let mut targets = BitSet::new(size);
        let mut incoming = false;
        let mut queue = VecDeque::from([source]);
        while let Some(module) = queue.pop_front() {
            if self.anywhere || self.open.has_bit(module) {
                return Reach {
                    any: true,
                    ingress: incoming,
                    targets,
                };
            }
            incoming |= ingress.has_bit(module);
            let outgoing = usize::try_from(module)
                .ok()
                .and_then(|slot| self.next.get(slot))
                .map_or(&[][..], Vec::as_slice);
            for &target in outgoing.iter().filter(|&&t| visited.set(t)) {
                targets.set(target);
                mark_target_ancestors(&mut targets, ancestors, target);
                queue.push_back(target);
            }
        }
        Reach {
            any: false,
            ingress: incoming,
            targets,
        }
    }
}

fn crate_reaches(deps: &[Vec<bool>], from: usize, to: usize) -> bool {
    from == to || deps.get(from).and_then(|row| row.get(to)).copied() == Some(true)
}

#[cfg(test)]
#[path = "impl_flow_tests.rs"]
mod tests;
