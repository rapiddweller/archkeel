// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The box of the Explorer tree (AD-606, AD-630): one type for the tree builder and for the
//! grouping of a level, so that neither module needs the other.

/// The most boxes of one level (AD-794): a 1440 x 900 screen in full view holds 6 x 5 module boxes
/// at the readable zoom of 85 percent (a box of 200 x 144 with the spacing of the layout). A larger
/// level is grouped by its structure: a name prefix, a directory, a file prefix.
pub(super) const ON_SCREEN: usize = 30;

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
    /// A box that the report makes to split a level with more boxes than stay readable (AD-630):
    /// the report decided it, not the contract (#1644).
    pub(super) grouped: bool,
}

impl Node {
    /// Who decided that the box exists: the report for a directory or a group box that it makes,
    /// else the architect, whose contract declares the component or the layer.
    pub(super) fn decided_by(&self) -> &'static str {
        if self.directory || self.grouped {
            "report"
        } else {
            "architect"
        }
    }
}
