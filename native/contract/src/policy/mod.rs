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
//!
//! `parse_amendment` and `amendment_bytes` read and write an amendment of schema 2.0.0, and
//! `bind` decides whether an amendment covers one comparison (AD-375).

mod amendment;
mod baseline;
mod baseline_entries;
mod baseline_value;
mod baseline_write;
mod binding;
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
mod amendment_tests;
#[cfg(test)]
mod baseline_tests;
#[cfg(test)]
mod compare_tests;
#[cfg(test)]
mod printable_tests;
#[cfg(test)]
mod tree_limit_tests;
#[cfg(test)]
mod tree_tests;

pub use amendment::{
    amendment_bytes, parse_amendment, Amendment, AmendmentDigest, AmendmentError, AmendmentField,
};
pub use baseline::parse_baseline;
pub use baseline_value::{
    BaselineBudget, BaselineError, BaselineFingerprint, BaselineRole, BaselineViolation,
    NameBudgetKind, ValidationBaseline, MAX_BASELINE_BYTES,
};
pub use baseline_write::{baseline_bytes, baseline_digest};
pub use binding::{bind, Baselines, BindError, Binding, GateStatus, OldContract, Verdict};
pub use change::{ChangeDirection, ChangeKind, ContractChange};
pub use compare::{compare_trees, Comparison};
pub use issue::{IssueKind, SourceProblem, TreeError, TreeIssue};
pub use tree::{assemble_tree, ContractTree, InsideMount, MAX_DEPTH};
