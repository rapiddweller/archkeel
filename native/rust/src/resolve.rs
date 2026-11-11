// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Which first segments of a path name a crate.
//!
//! One safe rule, with no model of Rust name resolution. A first segment that names a crate which
//! the scanned crate reaches (a dependency, a rename, or `std`) is an edge. When the file also
//! declares or imports that name anywhere, the path is UNKNOWN, and the scan does not decide which
//! one Rust picks. A path that starts with `::` is the crate. `crate`, `self` and `super` are
//! local. Edges between modules of one crate come with the module graph (AD-335, slice 5b-2).

use std::collections::BTreeSet;

use crate::crates::Crate;

/// The crates that every Rust program can name without a dependency.
/// One string, so that no literal of this file is itself the name of a crate (the safety net).
const SYSROOT: &str = "std core alloc";
/// The crates of the sysroot that only `extern crate` brings in.
const EXTERN_SYSROOT: &str = "proc_macro test";
/// First segments that never name a crate.
const RELATIVE: [&str; 4] = ["crate", "self", "super", "Self"];

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Named {
    /// A crate of the sysroot, such as `std`.
    Sysroot(String),
    /// A dependency: the package name as source writes it.
    Package(String),
}

/// What a first segment is.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Found {
    /// A crate that the scanned crate reaches: an edge.
    Edge(Named),
    /// The root names a reachable crate and the file also declares or imports that name. The scan
    /// does not decide which one Rust picks, so the path is UNKNOWN.
    Shadowed,
}

/// `absolute` is a path that starts with `::`: it names a crate and nothing local (Rust 2018 and
/// later), so it is an edge whatever the file declares. A path that starts with `crate`, `self` or
/// `super` is local. Any other root that is no reachable crate is no edge.
pub fn classify(
    root: &str,
    krate: &Crate,
    names: &BTreeSet<String>,
    absolute: bool,
) -> Option<Found> {
    if !absolute && RELATIVE.contains(&root) {
        return None;
    }
    let named = if SYSROOT.split(' ').any(|name| name == root) {
        Named::Sysroot(root.to_owned())
    } else {
        let package = krate.manifest.dependencies.get(root)?;
        // A binary that uses the library of its own package names it by the package name.
        if package == &krate.ident {
            return None;
        }
        Named::Package(package.clone())
    };
    Some(if !absolute && names.contains(root) {
        Found::Shadowed
    } else {
        Found::Edge(named)
    })
}

/// Whether the build gives `extern crate name;` without a link that a `build.rs` prints: a crate
/// of the sysroot, an entry of the manifest, or the library of the own package.
pub fn linked(name: &str, krate: &Crate) -> bool {
    let sysroot = SYSROOT.split(' ').chain(EXTERN_SYSROOT.split(' '));
    sysroot
        .chain([krate.ident.as_str()])
        .any(|known| known == name)
        || krate.manifest.dependencies.contains_key(name)
}

#[cfg(test)]
#[path = "resolve_tests.rs"]
mod tests;
