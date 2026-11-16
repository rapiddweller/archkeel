// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The resolution features that more than one check of the store reads (a leaf: no check of the
//! store may be imported here, so the checks do not form a cycle).

/// The feature of the Python survey that writes the symbol and the route of each named import
/// (AD-504).
pub(crate) const ROUTES_FEATURE: &str = "import-routes-v1";

/// The feature of the Rust collector that writes the item and the publication route of each
/// import (AD-604).
pub(crate) const RUST_ROUTES_FEATURE: &str = "rust-item-routes-v1";

/// The resolution features whose claims the store checks, for some collector (AD-346, AD-688).
/// A validation block cannot name another one: this is a part of the minimum of the store.
const KNOWN_FEATURES: [&str; 11] = [
    "static-imports",
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
    "inner-uml-v1",
    "script-globals-v1",
    "bundler-mode-v1",
    "rust-crate-edges",
    RUST_ROUTES_FEATURE,
    ROUTES_FEATURE,
];

/// The features that write the symbol of each import, so a symbol statement can hold.
pub(crate) const SYMBOL_FEATURES: [&str; 3] =
    ["script-globals-v1", ROUTES_FEATURE, RUST_ROUTES_FEATURE];

/// A resolution feature whose claims the store checks.
pub(crate) fn known_feature(feature: &str) -> bool {
    KNOWN_FEATURES.contains(&feature)
}
