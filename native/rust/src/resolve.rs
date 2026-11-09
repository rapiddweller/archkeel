// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Which first segments of a path name a crate.
//!
//! A first segment is a crate when it is a dependency of the crate, or a crate of the sysroot,
//! and the file declares no item of that name. Anything else is a local item, a prelude name, a
//! generic parameter or a `crate::` path, and is no edge. Edges between modules of one crate
//! come with the module graph (AD-335, slice 5b-2).

use std::collections::BTreeSet;

use crate::crates::Crate;

/// The crates that every Rust program can name without a dependency.
const SYSROOT: [&str; 3] = ["std", "core", "alloc"];
/// First segments that never name a crate.
const RELATIVE: [&str; 4] = ["crate", "self", "super", "Self"];

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Named {
    /// A crate of the sysroot, such as `std`.
    Sysroot(String),
    /// A dependency: the package name as source writes it.
    Package(String),
}

pub fn classify(root: &str, krate: &Crate, declared: &BTreeSet<String>) -> Option<Named> {
    if RELATIVE.contains(&root) || declared.contains(root) {
        return None;
    }
    if SYSROOT.contains(&root) {
        return Some(Named::Sysroot(root.to_owned()));
    }
    let package = krate.manifest.dependencies.get(root)?;
    // A binary that uses the library of its own package names it by the package name.
    (package != &krate.ident).then(|| Named::Package(package.clone()))
}

#[cfg(test)]
#[path = "resolve_tests.rs"]
mod tests;
