// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a run needs beyond the module and import facts (AD-512).
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
    /// The contract has a `boundary_types` rule: the core reads the signature shapes (AD-550).
    BoundaryTypes,
    /// The contract has an `interface_boundary` rule: a type that a declared signature names
    /// reaches a `public` entry (AD-580).
    InterfaceBoundary,
    /// The contract has an `unused_public` rule: the core reads the public items (AD-670).
    UnusedPublic,
    /// The contract has a `symbol_placement` rule.
    SymbolPlacement,
    /// The contract reads the exact function calls of a linked producer.
    CallOwner,
}

impl Need {
    /// True when this need reads the symbol, call and reference facts.
    fn symbols(self) -> bool {
        match self {
            Need::UmlTarget => true,
            Need::BoundaryTypes
            | Need::InterfaceBoundary
            | Need::UnusedPublic
            | Need::SymbolPlacement
            | Need::CallOwner => false,
        }
    }
}

/// The needs of one run. The default is no need.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Needs(BTreeSet<Need>, Vec<archkeel_contract::DoorReach>);

impl Needs {
    /// The needs of a run, from its reasons.
    pub fn from_reasons(needs: impl IntoIterator<Item = Need>) -> Self {
        Needs(needs.into_iter().collect(), Vec::new())
    }

    /// These needs and the declared reach of the door sites of the root contract (AD-664): the
    /// graph matches them to the doors of the reply and reads the declared imports as edges.
    pub fn with_doors(self, doors: Vec<archkeel_contract::DoorReach>) -> Self {
        Needs(self.0, doors)
    }

    /// The declared reach of the door sites.
    pub(crate) fn doors(&self) -> &[archkeel_contract::DoorReach] {
        &self.1
    }

    /// True when a need of the run reads the symbol facts.
    pub fn symbols(&self) -> bool {
        self.0.iter().any(|need| need.symbols())
    }

    /// True when the run reads the public module-level items (AD-670).
    pub fn published(&self) -> bool {
        self.0.contains(&Need::UnusedPublic)
    }

    /// True when the run reads the shapes of the written signature types (AD-550, AD-580).
    pub fn boundary(&self) -> bool {
        self.0.contains(&Need::BoundaryTypes) || self.0.contains(&Need::InterfaceBoundary)
    }

    /// True when the run reads class declarations for placement.
    pub fn placement(&self) -> bool {
        self.0.contains(&Need::SymbolPlacement)
    }

    pub(crate) fn call_owner(&self) -> bool {
        self.0.contains(&Need::CallOwner)
    }
}
