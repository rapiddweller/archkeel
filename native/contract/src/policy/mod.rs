// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract policy that spans more than one contract file (AD-366, epic #880).
//!
//! `assemble_tree` builds the tree of a root contract and its inside contracts from bytes that the
//! shell sends, and makes each check of Python `ir/codec_inside.py`. It returns the whole tree or
//! no tree. The comparison digest of the tree is the digest that an amendment binds.

mod heads;
mod issue;
mod reference;
mod scope;
mod tree;

#[cfg(test)]
mod tree_limit_tests;
#[cfg(test)]
mod tree_tests;

pub use issue::{IssueKind, SourceProblem, TreeError, TreeIssue};
pub use tree::{assemble_tree, ContractTree, InsideMount, MAX_DEPTH};
