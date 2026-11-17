// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract policy that spans more than one contract file (AD-366, epic #880).
//!
//! `assemble_tree` builds the tree of a root contract and its inside contracts from bytes that the
//! shell sends and checks each mount. It returns the whole tree or
//! no tree. The comparison digest of the tree is the digest that an amendment binds.
//!

mod baseline;
mod baseline_entries;
mod baseline_unknowns;
mod baseline_value;
mod baseline_write;
mod clip;
mod heads;
mod issue;
mod printable;
mod reference;
mod scope;
mod tree;

#[cfg(test)]
mod baseline_tests;
#[cfg(test)]
mod printable_tests;
#[cfg(test)]
mod tree_limit_tests;
#[cfg(test)]
mod tree_tests;

pub use baseline::parse_baseline;
pub use baseline_value::{
    AcceptedUnknown, BaselineBudget, BaselineError, BaselineFingerprint, BaselineRole,
    BaselineViolation, NameBudgetKind, ValidationBaseline, MAX_BASELINE_BYTES,
};
pub use baseline_write::{baseline_bytes, budget_word};
pub use clip::{clip_inside, Clipped};
pub use issue::{IssueKind, SourceProblem, TreeError, TreeIssue};
pub use scope::provenance_paths;
pub use tree::{assemble_tree, ContractTree, InsideMount};
