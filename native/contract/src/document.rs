// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The whole parsed contract.

use crate::model::{Component, ContractDigest, InsidePath, ItemId};
use crate::model_declarations::Declarations;
use crate::rule::Rule;
use crate::version::ContractVersion;

record!(
    pub(crate),
    /// One parsed contract. Its digest is the SHA-256 of the bytes: the contract identity of a run.
    Contract {
        version: ContractVersion,
        schema: Option<String>,
        components: Vec<Component>,
        rules: Vec<Rule>,
        declarations: Option<Declarations>,
        digest: ContractDigest,
    }
);

record!(
    pub(crate),
    /// One mount: the component that names an inside contract, and the path of that contract.
    InsideRef {
        component: ItemId,
        path: InsidePath,
    }
);

/// A contract whose components mount inside contracts. It is not complete: the tree assembly of
/// the inside contracts must read and check each mounted contract first. It gives its mounts, but
/// no `Contract`, so a caller cannot use it as a complete contract.
///
/// ```compile_fail
/// use archkeel_contract::{Contract, ParsedContract};
/// fn complete(parsed: ParsedContract) -> Contract {
///     match parsed {
///         ParsedContract::Complete(contract) => contract,
///         ParsedContract::NeedsTree(tree) => tree.contract,
///     }
/// }
/// ```
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NeedsTree {
    pub(crate) contract: Contract,
    pub(crate) mounts: Vec<InsideRef>,
}

impl NeedsTree {
    /// The mounts that the tree assembly must resolve, in the order of the components.
    pub fn mounts(&self) -> &[InsideRef] {
        &self.mounts
    }
}

/// The result of `parse`: a complete contract, or a contract that needs its inside tree.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ParsedContract {
    Complete(Contract),
    NeedsTree(NeedsTree),
}

/// A complete contract when no component mounts an inside contract.
pub(crate) fn classify(contract: Contract) -> ParsedContract {
    let mounts: Vec<InsideRef> = contract
        .components
        .iter()
        .filter_map(|component| {
            component.inside.as_ref().map(|path| InsideRef {
                component: component.id.clone(),
                path: path.clone(),
            })
        })
        .collect();
    if mounts.is_empty() {
        ParsedContract::Complete(contract)
    } else {
        ParsedContract::NeedsTree(NeedsTree { contract, mounts })
    }
}
