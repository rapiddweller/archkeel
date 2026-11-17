// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The profile statements that a linked collector makes about its own reply (AD-500, AD-749).
//! A wire reply carries none.

/// Whether a documented profile limit applies to this collection.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LimitSupport {
    /// The collector supports it.
    Supported,
    /// The collector does not support it.
    Unsupported,
}

/// The profile differences that the linked collector can state for its own reply.
/// These statements never replace coverage gaps or a rule's scope proof.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProfileLimits {
    /// Whether the profile reads the imported names of a dependency.
    pub dependency_symbols: LimitSupport,
    /// Whether the profile reads the types of an interface.
    pub interface_boundary: LimitSupport,
    /// Whether the profile states the publication surface of each import without the names of
    /// every dependency (AD-749): each name that the import binds with the first hop of its
    /// route, or else a record without a name and without known names, which binds every name
    /// of its target module; whether each route is complete; and each name that a re-export
    /// publishes outside the package. A `public` symbol entry is then read by
    /// `interface_boundary` alone. A profile with `dependency_symbols` needs no such statement.
    pub publication_surface: LimitSupport,
}
