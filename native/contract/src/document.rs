// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The whole parsed contract.

use crate::model::{Component, ContractDigest, InsidePath, ItemId};
use crate::model_declarations::Declarations;
use crate::premises::PremiseName;
use crate::rule::Rule;
use crate::version::ContractVersion;

record!(
    pub(crate),
    /// One parsed contract. Its digest is the SHA-256 of the bytes: the contract identity of a run.
    Contract {
        /// The schema version of the contract.
        version: ContractVersion,
        /// The URL of the JSON schema that the contract names, if any.
        schema: Option<String>,
        /// The components of the contract.
        components: Vec<Component>,
        /// The rules of the contract.
        rules: Vec<Rule>,
        /// The declarations that are not rules.
        declarations: Option<Declarations>,
        /// The digest of the contract file.
        digest: ContractDigest,
        /// The parent key of an inside contract that the tree assembly scoped, else `None`. Only
        /// the assembly sets it and no crate clears it, so a model can refuse an inside contract
        /// without the domain of its mount (AD-385). Not part of the canonical bytes.
        #[serde(skip)]
        mount: Option<String>,
    }
);

record!(
    pub(crate),
    /// One mount: the component that names an inside contract, and the path of that contract.
    InsideRef {
        /// The component that names the inside contract.
        component: ItemId,
        /// The path of the inside contract.
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
    /// The contract has no inside contract that is missing.
    Complete(Contract),
    /// The contract names inside contracts that the caller must read first.
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

/// The names of the premises that `contract` declares, in contract order.
pub fn declared_premises(contract: &Contract) -> Vec<PremiseName> {
    let mut names: Vec<PremiseName> = Vec::new();
    if let Some(declarations) = &contract.declarations {
        for premise in &declarations.premises {
            names.push(premise.name);
        }
    }
    names
}
