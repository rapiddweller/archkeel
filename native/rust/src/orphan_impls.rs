// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trait impl in a third module (#1004, AD-516). An impl of a trait for a type runs wherever
//! the types fit, and no `use` brings it in: `y.into()`, `?`, `a + b`, `x.to_string()`, `for i in
//! x`, `==`, `Drop`, and `fn f<T: Tr>(t: T)` all run an `impl` that the caller never names. The
//! scan reads no types, so it cannot tell which caller runs which impl.
//!
//! An orphan-module impl is a trait impl in a module that defines neither its trait nor its self
//! type. Every module that may reach it gets a pair gap to the module of the impl: the modules of
//! its crate, and of each crate that depends on that crate. A trait or a type that the scan cannot
//! resolve to a definition counts as not defined here, so the impl is an orphan. The host drops a
//! pair gap when the contract lets the caller use the module (AD-357).

use std::collections::BTreeSet;

use crate::builder::Builder;
use crate::crates::Workspace;
use crate::definitions::TraitImpl;
use crate::impl_globs::{depends, once_gap};
use crate::modules::{Index, TypeOf};
use crate::tree::Module;

/// Whether the path names a type or a trait that the file `home` defines: a block of the impl
/// declares it, or its lexical module is in the file.
fn defined_in(index: &Index<'_>, home: &Module, found: &TraitImpl, path: &[String]) -> bool {
    let local = |name: &String| {
        let blocks = home.scan.orphans.block_types.iter();
        let mut blocks = blocks.filter(|(declared, _)| declared == name);
        blocks.any(|(_, end)| found.blocks.contains(end))
    };
    if matches!(path, [name] if local(name)) {
        return true;
    }
    let Some(frame) = index.frame(&home.module) else {
        return false;
    };
    match index.type_of(frame, &found.scope, path) {
        TypeOf::Known(lexical, _) => index.file_of(&lexical) == Some(home.module.as_str()),
        TypeOf::Unknown | TypeOf::Other => false,
    }
}

/// Whether the impl is an orphan of the module `home`: no path of its head is defined there.
fn orphan(index: &Index<'_>, home: &Module, found: &TraitImpl) -> bool {
    !found
        .anchors
        .iter()
        .any(|path| defined_in(index, home, found, path))
}

/// The modules that may run an impl of `home`: its crate and each crate that depends on it.
fn callers<'a>(
    workspace: &'a Workspace,
    modules: &'a [Module],
    home: &'a Module,
) -> impl Iterator<Item = &'a Module> {
    let reach = move |caller: &&Module| {
        caller.crate_index == home.crate_index || depends(workspace, caller, home)
    };
    modules.iter().filter(reach)
}

/// A pair gap from each module that may reach an orphan-module impl to the module of the impl.
pub(super) fn orphan_impl_gaps(
    builder: &mut Builder,
    (workspace, index, modules): (&Workspace, &Index<'_>, &[Module]),
    edges: &BTreeSet<(String, String)>,
) {
    for home in modules {
        let target = home.module.as_str();
        let why = format!(
            "A trait impl in {target} defines neither its trait nor its type: code of the caller may run it"
        );
        let mut impls = home.scan.orphans.impls.iter();
        let Some(found) = impls.find(|found| orphan(index, home, found)) else {
            continue;
        };
        for caller in callers(workspace, modules, home) {
            let pair = (caller.module.as_str(), target);
            once_gap(builder, edges, pair, (&home.rel, &found.site), &why);
        }
    }
}
