// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a path of the module resolver names: a module edge, a type, or nothing the scan can say.

/// A module that a path names: the file that holds it and the first segment after it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Edge {
    /// The module id of the file that holds the target.
    pub module: String,
    /// The module of the target itself: an inline `mod` has its own, below its file.
    pub lexical: String,
    /// The segment after the deepest module, or `None` when the path ends at a module.
    pub symbol: Option<String>,
    /// 0 for `crate::`, 1 for `self::` and a child name, `n + 1` for `super::` n times.
    pub level: i64,
}

/// The type that a path names, for the members of its `impl` blocks (#953).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum TypeOf {
    /// The lexical module that defines the type, and its name.
    Known(String, String),
    /// The scan cannot say which type it is: a glob may bring it in, or the path is UNKNOWN.
    Unknown,
    /// No type of this crate: another crate, `Self`, or an associated item.
    Other,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Outcome {
    /// The path names no module of this crate (a crate, a type, a function).
    None,
    Edge(Edge),
    /// The scan cannot say which module the path names, and says why.
    Unknown(String),
}
