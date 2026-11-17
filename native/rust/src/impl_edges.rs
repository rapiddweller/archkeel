// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The uses of a method that another module defines (#953, AD-357).
//!
//! An inherent `impl` of a type can stand in any module of the crate of the type. A member of a
//! block that is not in the file of its type is foreign. A path `c::S::m` names its member: when
//! the file of `S` defines no `m` for `S`, the module of the foreign block that does is an edge. A
//! method call `x.m()` does not tell the type of `x`: each foreign `m` that the caller can see is
//! a gap of the pair. A trait that a glob brings in gives the same gap for the calls of its methods.
//! The scan reads no types, so a pair gap is the sound answer; the host drops it when the contract
//! lets the caller use that module.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::ImportFact;

use crate::builder::Builder;
use crate::crates::Workspace;
use crate::definitions::{Form, ImplBlock, MethodCall};
use crate::impl_globs::{crate_path, Reached};
use crate::modules::{Edge, Frame, Index, TypeOf};
use crate::scan::Via;
use crate::tree::Module;
use flow::{visible, Foreign};
use orphans::orphan_impl_gaps;
use receivers::{certainly_visible, exact_type, Typed};

/// The members of the inherent `impl` blocks of the walk.
#[derive(Default)]
struct Members<'a> {
    foreign: BTreeMap<&'a str, Vec<Foreign<'a>>>,
    /// The members of the blocks in the file of their type: its lexical module, its name, the member.
    own: BTreeSet<(String, String, &'a str)>,
    /// The same members by name, with their block: a method call whose receiver the scan does not
    /// resolve may reach each of them (#1571), as it may reach a foreign one.
    owned: BTreeMap<&'a str, Vec<Foreign<'a>>>,
    /// The names that may stand for another type in a path: each type alias and each name that
    /// a `use` renames.
    aliases: BTreeSet<&'a str>,
    /// The members of every block by placed type, for the calls on `self` (AD-383).
    typed: Typed<'a>,
}

fn members<'a>(index: &Index<'_>, modules: &'a [Module]) -> Members<'a> {
    let mut found = Members::default();
    for module in modules {
        found.typed.note(module);
        found.aliases.extend(flow::aliases(module));
        let Some(frame) = index.frame(&module.module) else {
            continue;
        };
        for block in &module.scan.impls {
            found.add(index, frame, module, block);
        }
    }
    found
}

impl<'a> Members<'a> {
    /// Add the members of one block: own when the block is in the file of its type.
    fn add(
        &mut self,
        index: &Index<'_>,
        frame: &Frame<'_>,
        module: &'a Module,
        block: &'a ImplBlock,
    ) {
        let ty = block.path.as_ref().map_or(TypeOf::Unknown, |path| {
            index.local_type_of(frame, &block.scope, path)
        });
        let own = match &ty {
            TypeOf::Known(lexical, name) if index.file_of(lexical) == Some(&module.module) => {
                Some((lexical, name))
            }
            TypeOf::Other => return,
            _ => None,
        };
        self.typed
            .place(frame.lexical_at(&block.scope), module, block, &ty);
        for member in &block.members {
            let name = member.name.as_str();
            let found = Foreign {
                module,
                lexical: frame.lexical_at(&block.scope),
                ty: ty.clone(),
                member,
                exact: block.exact,
            };
            if let Some((lexical, ty)) = own {
                self.own.insert((lexical.clone(), ty.clone(), name));
                self.owned.entry(name).or_default().push(found);
                continue;
            }
            self.foreign.entry(name).or_default().push(found);
        }
    }
}

/// A path call `T::m(..)`: it can reach a member with or without `self`, of any arity.
fn path_call(reference: &crate::scan::Reference) -> MethodCall {
    MethodCall {
        name: reference.names.last().cloned().unwrap_or_default(),
        site: reference.site.clone(),
        scope: reference.scope.clone(),
        path: true,
        arity: None,
        on_self: None,
        owner: written_owner(reference),
    }
}

/// The last name of the written type of a path `T::m`.
fn written_owner(reference: &crate::scan::Reference) -> Option<String> {
    let names = &reference.names;
    names
        .len()
        .checked_sub(2)
        .and_then(|at| names.get(at))
        .cloned()
}

/// What the paths `T::m` of a module leave open.
#[derive(Default)]
struct Paths {
    /// The paths that may reach any foreign member of their last name.
    unresolved: Vec<MethodCall>,
    /// The paths to a member of a known type that the caller may not see: a gap to its module.
    doubts: Vec<(MethodCall, String)>,
    /// The places of the paths that an edge to their one member explains.
    proved: BTreeSet<(i64, i64)>,
}

/// Whether the enum has a variant of the name: `E::n(..)` then builds the variant.
fn variant(index: &Index<'_>, lexical: &str, ty: &str, member: &str) -> bool {
    let frame = index.file_of(lexical).and_then(|file| index.frame(file));
    let definitions = frame
        .into_iter()
        .flat_map(|frame| &frame.module.scan.definitions);
    let mut enums = definitions.filter(|d| d.form == Form::Enum && d.name == ty);
    enums.any(|d| d.variants.iter().any(|name| name == member))
}

/// Whether a macro of the file can give the first name of the type path again: the path then
/// names no certain type, unless it starts at `crate`, `self`, `super` or `::`.
fn rebound(module: &Module, reference: &crate::scan::Reference, shadowed: bool) -> bool {
    let fixed = ["crate", "self", "super", "Self"];
    let first = reference.names.first().map_or("", String::as_str);
    let scan = &module.scan;
    let macros = scan.body_macros || scan.module_macros || (scan.placed_macros && shadowed);
    macros && !reference.absolute && !fixed.contains(&first)
}

impl Builder {
    /// The edges and the pair gaps of the methods of foreign `impl` blocks and of glob traits.
    pub(crate) fn impl_members(
        &mut self,
        workspace: &Workspace,
        index: &Index<'_>,
        modules: &[Module],
    ) {
        let found = members(index, modules);
        let paths: Vec<Paths> = (modules.iter())
            .map(|module| self.member_paths(index, module, &found))
            .collect();
        let edges = self.module_pairs();
        orphan_impl_gaps(self, (workspace, index, modules), &edges);
        let mut pending = Vec::new();
        for (module, paths) in modules.iter().zip(paths) {
            let mut calls = self.calls_of(workspace, index, module, &paths.proved);
            calls.extend(paths.unresolved);
            let reached = Reached {
                index,
                module,
                calls: &calls,
                edges: &edges,
            };
            // The first calls of the list are the ones of the scan: `calls_of` puts them first.
            let own = module.scan.method_calls.len();
            self.method_gaps(workspace, &reached, &found, own, &mut pending);
            for (call, target) in &paths.doubts {
                let reason = format!(
                    "A method call may reach the method {} of an impl block in {target}",
                    call.name
                );
                self.reached_gap(&reached, call, target, &reason);
            }
            self.glob_trait_gaps(workspace, &reached);
        }
        flow::settle(self, pending);
    }

    /// A path `S::m` whose type file defines no `m` for `S` is an edge to each foreign block of it
    /// that the caller can see. A path whose type the scan cannot resolve exactly, or a type that
    /// a foreign block of an unknown type may also extend, is returned as a call: it may reach any
    /// foreign `m` (#953). A path to a type that explicit paths give is an edge to its one member
    /// (AD-544).
    fn member_paths(&mut self, index: &Index<'_>, module: &Module, found: &Members<'_>) -> Paths {
        let mut out = Paths::default();
        let Some(frame) = index.frame(&module.module) else {
            return out;
        };
        let paths = module.scan.references.iter();
        for reference in
            paths.filter(|r| matches!(r.via, Via::Path | Via::Helper) && r.in_macro.is_none())
        {
            let Some((member, ty)) = reference.names.split_last() else {
                continue;
            };
            // A macro may define the member outside the file of its type (#1371, AD-656).
            if !ty.is_empty() && self.macro_foreign_members.contains_key(member.as_str()) {
                out.unresolved.push(path_call(reference));
            }
            let Some(blocks) = (found.foreign.get(member.as_str())).filter(|_| !ty.is_empty())
            else {
                continue;
            };
            let site = (reference.site.line, reference.site.column);
            let shadowed = found.typed.shadowed();
            if module.scan.generic_paths.contains(&site) || rebound(module, reference, shadowed) {
                out.unresolved.push(path_call(reference));
                continue;
            }
            let at = frame.lexical_at(&reference.scope);
            let known = index.local_type_of(frame, &reference.scope, ty);
            let own = match &known {
                TypeOf::Known(lexical, name) if variant(index, lexical, name, member) => {
                    out.unresolved.push(path_call(reference));
                    continue;
                }
                TypeOf::Known(lexical, name) => {
                    found
                        .own
                        .contains(&(lexical.clone(), name.clone(), member.as_str()))
                }
                TypeOf::Unknown => false,
                TypeOf::Other => continue,
            };
            if let Some(edge) = self.sole_member((index, frame), reference, &known, found) {
                self.module_import(index, module, reference, &edge);
                out.proved.insert(site);
                continue;
            }
            let unknown_block = blocks.iter().any(|block| block.ty == TypeOf::Unknown);
            let open_call = known == TypeOf::Unknown || (!own && unknown_block);
            if open_call {
                out.unresolved.push(path_call(reference));
            }
            if own || known == TypeOf::Unknown {
                continue;
            }
            let seen = |block: &&Foreign<'_>| {
                let place = (block.module, block.lexical.as_str());
                certainly_visible(module, &at, place, &block.member.access)
            };
            let typed = blocks.iter().filter(|block| block.ty == known);
            let (open, hidden): (Vec<_>, Vec<_>) = typed.partition(seen);
            let doubt = |block: &&Foreign<'_>| (path_call(reference), block.module.module.clone());
            out.doubts.extend(hidden.iter().map(doubt));
            let TypeOf::Known(type_at, type_name) = &known else {
                continue;
            };
            // #1276: the path reaches the members of the blocks only when its type is exact and
            // each member is in every configuration. An attribute macro on the type can add a
            // variant of the name, and a `cfg` on a member can remove it: the call stays open.
            let certain = exact_type(index, module, type_at, type_name)
                && open.iter().all(|block| block.exact && block.member.inert);
            if !certain && !open_call {
                out.unresolved.push(path_call(reference));
            }
            if !certain {
                continue;
            }
            for block in open {
                let edge = Edge {
                    module: block.module.module.clone(),
                    lexical: block.lexical.clone(),
                    symbol: Some(member.clone()),
                    level: 0,
                    member_of: Some((type_at.clone(), type_name.clone())),
                };
                self.module_import(index, module, reference, &edge);
            }
        }
        out
    }

    /// The edge of a path `T::m` whose type is not a type of the module of the path, when explicit
    /// paths give the type and it has one member `m` that the path reaches for certain (AD-544).
    fn sole_member(
        &self,
        (index, frame): (&Index<'_>, &Frame<'_>),
        reference: &crate::scan::Reference,
        local: &TypeOf,
        found: &Members<'_>,
    ) -> Option<Edge> {
        let (member, ty) = reference.names.split_last()?;
        // A macro of the name of a silent macro of `std` can give a name of its tokens again.
        let opaque_gate = frame.module.gated && frame.module.gates.is_none();
        let doubt = opaque_gate || reference.absolute || found.typed.shadowed();
        if *local != TypeOf::Unknown || doubt {
            return None;
        }
        let TypeOf::Known(lexical, name) = index.type_of(frame, &reference.scope, ty) else {
            return None;
        };
        if self.macro_members.contains_key(member) || variant(index, &lexical, &name, member) {
            return None;
        }
        let at = frame.lexical_at(&reference.scope);
        let caller = (frame.module, at.as_str());
        let (module, block) = found.typed.sole(index, caller, (&lexical, &name), member)?;
        Some(Edge {
            module: module.module.clone(),
            lexical: block.to_owned(),
            symbol: Some(member.clone()),
            level: 0,
            member_of: Some((lexical, name)),
        })
    }

    /// The pairs of modules that an `import` or `reexport` record joins.
    fn module_pairs(&self) -> BTreeSet<(String, String)> {
        let data = self.imports.iter().filter_map(|record| match &record.data {
            ImportFact::Import(data) | ImportFact::Reexport(data) => Some(data),
            _ => None,
        });
        data.map(|d| {
            (
                d.source_module.as_str().to_owned(),
                d.target_module.as_str().to_owned(),
            )
        })
        .collect()
    }

    /// The method calls of a module: in its code, in the macros that it calls, and the last name
    /// of each path into another crate of the workspace.
    fn calls_of(
        &self,
        workspace: &Workspace,
        index: &Index<'_>,
        module: &Module,
        proved: &BTreeSet<(i64, i64)>,
    ) -> Vec<MethodCall> {
        let mut calls = module.scan.method_calls.clone();
        calls.extend(
            self.macro_methods
                .get(&module.module)
                .into_iter()
                .flatten()
                .cloned(),
        );
        let Some(frame) = index.frame(&module.module) else {
            return calls;
        };
        let crate_paths = module
            .scan
            .references
            .iter()
            .filter(|r| matches!(r.via, Via::Path | Via::Helper));
        let open = crate_paths.filter(|r| !proved.contains(&(r.site.line, r.site.column)));
        for reference in open.filter(|r| crate_path(workspace, frame, r)) {
            if let Some(name) = reference.names.last() {
                calls.push(MethodCall {
                    name: name.clone(),
                    site: reference.site.clone(),
                    scope: reference.scope.clone(),
                    path: true,
                    arity: None,
                    on_self: None,
                    owner: written_owner(reference),
                });
            }
        }
        calls
    }

    /// A gap for each foreign member that a call of the module can reach, and no edge explains.
    fn method_gaps(
        &mut self,
        workspace: &Workspace,
        reached: &Reached<'_>,
        found: &Members<'_>,
        own: usize,
        pending: &mut Vec<flow::Pending>,
    ) {
        let (module, frame) = (reached.module, reached.index.frame(&reached.module.module));
        let Some(frame) = frame else {
            return;
        };
        for (at_index, call) in reached.calls.iter().enumerate() {
            #[cfg(feature = "dump")]
            if at_index < own
                && std::env::var("ARCHKEEL_PLANT_METHOD")
                    .is_ok_and(|value| value == format!("{}:{at_index}", module.rel))
            {
                continue;
            }
            if at_index < own && self.self_call((reached.index, frame), module, call, &found.typed)
            {
                *self.ended_methods.entry(module.rel.clone()).or_default() += 1;
                continue;
            }
            // #1571: a receiver of a std type reaches no inherent member of the workspace; a
            // macro can still write a trait impl for it (below).
            let std = at_index < own
                && receivers::std_receiver((reached.index, frame), module, call, &found.typed);
            let at = frame.lexical_at(&call.scope);
            let blocks = found.foreign.get(call.name.as_str()).into_iter().flatten();
            let blocks = blocks.filter(|_| !std);
            for block in blocks.filter(|block| visible(workspace, (module, &at), call, block)) {
                let target = block.module.module.as_str();
                let reason = format!(
                    "A method call may reach the method {} of an impl block in {target}",
                    call.name
                );
                self.reached_gap(reached, call, target, &reason);
            }
            // #1571: the call may reach a member in the file of its type (`impl_flow.rs`).
            let owned = (found.owned.get(call.name.as_str()))
                .filter(|_| !std)
                .map_or(&[][..], Vec::as_slice);
            let candidates = (owned, &found.aliases);
            pending.extend(flow::own_candidates(
                workspace,
                (module, &at),
                call,
                candidates,
            ));
            // #1196: a macro call can define the method in an impl block outside the file of its
            // type, which the scan does not see; its visibility is not read either. A macro that
            // defines the type and its impl together adds a member of its own file (AD-357).
            let defined = (self.macro_foreign_members.get(&call.name).cloned()).unwrap_or_default();
            for target in &defined {
                let reason = format!(
                    "A method call may reach the method {} that a macro call in {target} may define",
                    call.name
                );
                self.reached_gap(reached, call, target, &reason);
            }
            if at_index < own {
                *self.ended_methods.entry(module.rel.clone()).or_default() += 1;
            }
        }
    }
}

/// A trait impl in a third module gives a pair gap (AD-516).
#[path = "orphan_impls.rs"]
mod orphans;

/// The value flow of a call into the file of a type (#1571).
#[path = "impl_flow.rs"]
mod flow;

/// The resolution of a call on a plain `self` (AD-383).
#[path = "impl_receivers.rs"]
mod receivers;

#[cfg(test)]
#[path = "impl_edges_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "transitive_edges_tests.rs"]
mod transitive_tests;
