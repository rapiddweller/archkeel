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
use crate::definitions::{Access, ImplBlock, Member, MethodCall};
use crate::impl_globs::{crate_path, Reached};
use crate::modules::{inside, Edge, Frame, Index, TypeOf};
use crate::plant;
use crate::scan::Via;
use crate::tree::Module;
use receivers::Typed;

/// A member of an inherent `impl` block that is not in the file of its type.
struct Foreign<'a> {
    module: &'a Module,
    /// The lexical module of the block.
    lexical: String,
    ty: TypeOf,
    member: &'a Member,
}

/// The members of the inherent `impl` blocks of the walk.
#[derive(Default)]
struct Members<'a> {
    foreign: BTreeMap<&'a str, Vec<Foreign<'a>>>,
    /// The members of the blocks in the file of their type: its lexical module, its name, the member.
    own: BTreeSet<(String, String, &'a str)>,
    /// The members of every block by placed type, for the calls on `self` (AD-383).
    typed: Typed<'a>,
}

fn members<'a>(index: &Index<'_>, modules: &'a [Module]) -> Members<'a> {
    let mut found = Members::default();
    for module in modules {
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
            index.type_of(frame, &block.scope, path)
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
            if let Some((lexical, ty)) = own {
                self.own.insert((lexical.clone(), ty.clone(), name));
                continue;
            }
            self.foreign.entry(name).or_default().push(Foreign {
                module,
                lexical: frame.lexical_at(&block.scope),
                ty: ty.clone(),
                member,
            });
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
    }
}

/// Whether a call at `at` in `caller` can reach the member: `x.m(..)` reaches only a member with a
/// `self` parameter and as many other parameters as the call has arguments (Rust has no overloads).
/// `pub(in path)` counts as the crate.
fn visible(
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
        Access::Private => false,
        Access::Package(text) if text == "pub(super)" => {
            let parent = member.lexical.rsplit_once('.').map_or("", |(up, _)| up);
            inside(at, parent)
        }
        Access::Package(_) => same_crate,
        Access::Public => same_crate || depends(workspace, caller, member.module),
    }
}

/// Whether the crate of `caller` reaches the crate of `target` through its dependencies. A value
/// of a crate that the caller reaches only through another crate can carry a method call into it
/// (review B2 of #1121), so the walk follows the dependencies of each crate of the workspace.
fn depends(workspace: &Workspace, caller: &Module, target: &Module) -> bool {
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
    /// The edges and the pair gaps of the methods of foreign `impl` blocks and of glob traits.
    pub(crate) fn impl_members(
        &mut self,
        workspace: &Workspace,
        index: &Index<'_>,
        modules: &[Module],
    ) {
        let found = members(index, modules);
        let paths: Vec<Vec<MethodCall>> = (modules.iter())
            .map(|module| self.member_paths(index, module, &found))
            .collect();
        let edges = self.module_pairs();
        for (module, unresolved) in modules.iter().zip(paths) {
            let mut calls = self.calls_of(workspace, index, module);
            calls.extend(unresolved);
            let reached = Reached {
                index,
                module,
                calls: &calls,
                edges: &edges,
            };
            // The first calls of the list are the ones of the scan: `calls_of` puts them first.
            let own = module.scan.method_calls.len();
            self.method_gaps(workspace, &reached, &found, own);
            self.glob_trait_gaps(workspace, &reached);
        }
    }

    /// A path `S::m` whose type file defines no `m` for `S` is an edge to each foreign block of it.
    /// A path whose type the scan cannot resolve exactly, or a type that a foreign block of an
    /// unknown type may also extend, is returned as a call: it may reach any foreign `m` (#953).
    fn member_paths(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        found: &Members<'_>,
    ) -> Vec<MethodCall> {
        let mut unresolved = Vec::new();
        let Some(frame) = index.frame(&module.module) else {
            return unresolved;
        };
        let paths = module.scan.references.iter();
        for reference in
            paths.filter(|r| matches!(r.via, Via::Path | Via::Helper) && r.in_macro.is_none())
        {
            let Some((member, ty)) = reference.names.split_last() else {
                continue;
            };
            let Some(blocks) = (found.foreign.get(member.as_str())).filter(|_| !ty.is_empty())
            else {
                continue;
            };
            let known = index.type_of(frame, &reference.scope, ty);
            let own = match &known {
                TypeOf::Known(lexical, name) => {
                    found
                        .own
                        .contains(&(lexical.clone(), name.clone(), member.as_str()))
                }
                TypeOf::Unknown => false,
                TypeOf::Other => continue,
            };
            let unknown_block = blocks.iter().any(|block| block.ty == TypeOf::Unknown);
            if known == TypeOf::Unknown || (!own && unknown_block) {
                unresolved.push(path_call(reference));
            }
            if own || known == TypeOf::Unknown {
                continue;
            }
            for block in blocks.iter().filter(|block| block.ty == known) {
                let edge = Edge {
                    module: block.module.module.clone(),
                    lexical: block.lexical.clone(),
                    symbol: Some(member.clone()),
                    level: 0,
                };
                self.module_import(index, module, reference, &edge);
            }
        }
        unresolved
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
        for reference in crate_paths.filter(|r| crate_path(workspace, frame, r)) {
            if let Some(name) = reference.names.last() {
                calls.push(MethodCall {
                    name: name.clone(),
                    site: reference.site.clone(),
                    scope: reference.scope.clone(),
                    path: true,
                    arity: None,
                    on_self: None,
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
    ) {
        let (module, frame) = (reached.module, reached.index.frame(&reached.module.module));
        let Some(frame) = frame else {
            return;
        };
        for (at_index, call) in reached.calls.iter().enumerate() {
            if at_index < own && plant::method(&module.rel, at_index) {
                continue;
            }
            if at_index < own && self.self_call((reached.index, frame), module, call, &found.typed)
            {
                *self.ended_methods.entry(module.rel.clone()).or_default() += 1;
                continue;
            }
            let at = frame.lexical_at(&call.scope);
            let blocks = found.foreign.get(call.name.as_str()).into_iter().flatten();
            for block in blocks.filter(|block| visible(workspace, (module, &at), call, block)) {
                let target = block.module.module.as_str();
                let reason = format!(
                    "A method call may reach the method {} of an impl block in {target}",
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

/// The resolution of a call on a plain `self` (AD-383).
#[path = "impl_receivers.rs"]
mod receivers;

#[cfg(test)]
#[path = "impl_edges_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "transitive_edges_tests.rs"]
mod transitive_tests;
