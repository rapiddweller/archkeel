// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a trait of a dependency can be in scope in a file (#1571, AD-804). A trait method can
//! win a method call at an earlier step than an inherent method of a deref target, or than an
//! inherent method that needs an autoref. A trait is called only when it is in scope: the
//! prelude, or a `use` of the module. The traits of the prelude and of `std` are known, and none
//! of them has a method of a name of the table of `impl_ty.rs` for its types; the traits of the
//! workspace are read (`Typed::trait_members`). So a file is `closed` when no `use` can bring in a
//! trait of another crate:
//! - each `use` leaf starts at `std`, `core` or `alloc`, or in the workspace (`crate`, `self`,
//!   `super`, a crate of the workspace, a module of the file);
//! - a leaf from the workspace names nothing that a module of the workspace re-exports from
//!   another crate, and no module re-exports a glob of another crate;
//! - each glob is a glob of `std` (a glob of the workspace can bring in each `use` of its module);
//! - no `extern crate` and no macro call that is no silent macro of `std` (a macro can write a
//!   `use`).

use std::collections::BTreeSet;

use crate::crates::Workspace;
use crate::impl_globs::workspace_root;
use crate::modules::{Frame, Index};
use crate::scan::{Reference, Via};
use crate::std_macros;
use crate::tree::Module;

/// The names that a module of the workspace re-exports from another crate.
#[derive(Default)]
pub(super) struct Outside {
    names: BTreeSet<String>,
    /// A module re-exports a glob of another crate: any name can come from it.
    glob: bool,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Start {
    Std,
    Workspace,
    Outside,
}

/// Where the path of a `use` leaf starts, after up to four leaves that bind its first name.
fn start(workspace: &Workspace, frame: &Frame<'_>, leaf: &Reference) -> Start {
    let mut leaf = leaf;
    for _ in 0..4 {
        let Some(root) = leaf.names.first() else {
            return Start::Outside;
        };
        let declared = frame.module.scan.counts.contains_key(root);
        match &**root {
            "std" | "core" | "alloc" if !declared || leaf.absolute => return Start::Std,
            "crate" | "self" | "super" => return Start::Workspace,
            _ => {}
        }
        if workspace_root(workspace, frame.module, leaf).is_some() {
            return Start::Workspace;
        }
        match frame.bound(root) {
            [] if declared && !leaf.absolute => return Start::Workspace,
            [next] if !leaf.absolute && !std::ptr::eq(*next, leaf) => leaf = next,
            _ => return Start::Outside,
        }
    }
    Start::Outside
}

fn bound(leaf: &Reference) -> Option<&str> {
    match &leaf.via {
        Via::Use { binding, .. } => binding.as_deref().or(leaf.names.last().map(String::as_str)),
        _ => None,
    }
}

fn reexport(leaf: &Reference) -> bool {
    matches!(leaf.via, Via::Use { reexport: true, .. })
}

/// The names that the workspace re-exports from another crate, also through a renamed re-export.
pub(super) fn outside(index: &Index<'_>, modules: &[Module]) -> Outside {
    let workspace = index.workspace();
    let frames: Vec<&Frame<'_>> = modules
        .iter()
        .filter_map(|m| index.frame(&m.module))
        .collect();
    let mut found: Outside = Outside::default();
    for frame in &frames {
        found.glob |= (frame.globs())
            .any(|glob| reexport(glob) && start(workspace, frame, glob) == Start::Outside);
        for leaf in frame.leaves().filter(|leaf| reexport(leaf)) {
            if let (Start::Outside, Some(name)) = (start(workspace, frame, leaf), bound(leaf)) {
                found.names.insert(name.to_owned());
            }
        }
    }
    loop {
        let renamed: Vec<String> = (frames.iter().flat_map(|frame| frame.leaves()))
            .filter(|leaf| reexport(leaf))
            .filter(|leaf| (leaf.names.last()).is_some_and(|last| found.names.contains(last)))
            .filter_map(|leaf| bound(leaf).map(str::to_owned))
            .collect();
        let before = found.names.len();
        found.names.extend(renamed);
        if found.names.len() == before {
            return found;
        }
    }
}

/// Whether no `use` of the file can bring a trait of another crate into scope (module notes).
pub(super) fn closed(workspace: &Workspace, frame: &Frame<'_>, outside: &Outside) -> bool {
    let scan = &frame.module.scan;
    let silent = |call: &crate::scan::MacroCall| std_macros::has(&call.name, std_macros::NO_BIND);
    if scan.module_macros
        || scan.body_macros
        || !scan.extern_crates.is_empty()
        || !scan.macro_calls.iter().all(silent)
    {
        return false;
    }
    let globs = (frame.globs()).all(|glob| start(workspace, frame, glob) == Start::Std);
    globs
        && frame
            .leaves()
            .all(|leaf| match start(workspace, frame, leaf) {
                Start::Std => true,
                Start::Outside => false,
                Start::Workspace => {
                    !outside.glob
                        && leaf
                            .names
                            .last()
                            .is_none_or(|name| !outside.names.contains(name))
                }
            })
}
