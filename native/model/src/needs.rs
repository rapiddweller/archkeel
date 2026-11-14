// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a run needs beyond the module and import facts (AD-502).
//!
//! The core derives one `Needs` value from the contract tree (`core/src/contract.rs`). A run
//! without a need builds no symbol table, so its reply part and its frame do not change. A new
//! reason to read the symbols, such as a rule kind or the drill-down of the report, is one new
//! variant of `Need`.

use std::collections::BTreeSet;

/// One reason of a run to read more facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Need {
    /// The root contract has a UML target that the core compares (AD-494).
    UmlTarget,
}

impl Need {
    /// True when this need reads the symbol, call and reference facts.
    fn symbols(self) -> bool {
        match self {
            Need::UmlTarget => true,
        }
    }
}

/// The needs of one run. The default is no need.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Needs(BTreeSet<Need>);

impl Needs {
    /// The needs of a run, from its reasons.
    pub fn of(needs: impl IntoIterator<Item = Need>) -> Self {
        Needs(needs.into_iter().collect())
    }

    /// True when a need of the run reads the symbol facts.
    pub fn symbols(&self) -> bool {
        self.0.iter().any(|need| need.symbols())
    }
}
