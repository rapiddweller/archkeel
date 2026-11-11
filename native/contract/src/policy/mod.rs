// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract policy that spans more than one contract file (AD-366, epic #880).
//!
//! `assemble_tree` builds the tree of a root contract and its inside contracts from bytes that the
//! shell sends, and makes each check of Python `ir/codec_inside.py`. It returns the whole tree or
//! no tree. The comparison digest of the tree is the digest that an amendment binds.
//!
//! `compare_trees` compares an old and a new tree as `validate --against` does (AD-373).

mod change;
mod compare;
mod heads;
mod issue;
mod printable;
mod pyrepr;
mod reference;
mod scope;
mod tree;
mod widen_components;
mod widen_rule_parts;
mod widen_rules;

#[cfg(test)]
mod compare_tests;
#[cfg(test)]
mod printable_tests;
#[cfg(test)]
mod tree_limit_tests;
#[cfg(test)]
mod tree_tests;

pub use change::{ChangeDirection, ChangeKind, ContractChange};
pub use compare::{compare_trees, Comparison};
pub use issue::{IssueKind, SourceProblem, TreeError, TreeIssue};
pub use tree::{assemble_tree, ContractTree, InsideMount, MAX_DEPTH};
