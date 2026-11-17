// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The box of the Explorer tree (AD-606, AD-630): one type for the tree builder and for the
//! grouping of a level, so that neither module needs the other.

/// One box of the Explorer: a component of the contract, or a layer of its layer order.
pub(super) struct Node {
    pub(super) id: String,
    pub(super) label: String,
    pub(super) parent: Option<usize>,
    pub(super) layer: Option<String>,
    pub(super) public: Vec<String>,
    pub(super) path: String,
    /// What the box is responsible for; a layer names the count of its components.
    pub(super) about: Vec<String>,
    /// What the component must not do, and its planned surface, as the contract states them.
    pub(super) forbidden: Vec<String>,
    pub(super) planned: Vec<String>,
    /// The documents that give the reasons of the box, as the contract names them.
    pub(super) provenance: Vec<String>,
    /// The number of components that a layer or group holds; `None` for a component.
    pub(super) members: Option<usize>,
    /// The place of a layer in its layer order, from the inner layer; `None` for a component.
    pub(super) rank: Option<usize>,
    /// A box that the report makes for one directory of the modules of a large component: no
    /// contract text is its own.
    pub(super) directory: bool,
}
