// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Contract` request: parse the root contract and assemble its inside-contract tree from
//! the bytes that the shell sends (AD-366, AD-379).
//!
//! The core reads no file. A root that mounts inside contracts gives the paths that the shell must
//! still send (`ContractState::Missing`). The shell reads them and sends the request again with
//! each file, in rounds, until the tree assembles or a named error stays. Each round assembles
//! the tree again from the whole input, so a changed file between two rounds gives the tree of
//! the last bytes or a named error, never a mix. A refused or partial tree is never used.

use std::collections::BTreeMap;

use archkeel_contract::policy::{assemble_tree, ContractTree};
use archkeel_contract::{head_of, kind_of, uml_target_id, Contract, ParsedContract, RuleKind};
use archkeel_model::{Reason, Unsupported};

/// The most inside contracts of one request. The reference engine has no bound (AD-379).
pub(crate) const MAX_INSIDE_FILES: usize = 1024;
/// The most bytes of all inside contracts of one request. The reference engine has no bound.
pub(crate) const MAX_INSIDE_BYTES: usize = 64 << 20;

/// One inside contract that the shell read: the reference as the mount writes it, the
/// repository-relative path that the shell resolved it to, and the bytes.
#[derive(Debug)]
pub(crate) struct InsideFile {
    pub(crate) reference: String,
    pub(crate) identity: String,
    pub(crate) bytes: Vec<u8>,
}

/// The root contract at its repository path and the inside contracts that the shell sends.
#[derive(Debug)]
pub(crate) struct ContractInput {
    pub(crate) path: String,
    pub(crate) bytes: Vec<u8>,
    pub(crate) insides: Vec<InsideFile>,
}

#[cfg(test)]
impl ContractInput {
    /// A root contract at `architecture-contract.json` without inside contracts.
    pub(crate) fn root(bytes: Vec<u8>) -> ContractInput {
        ContractInput {
            path: "architecture-contract.json".to_owned(),
            bytes,
            insides: Vec::new(),
        }
    }
}

/// What the engine knows of the contract.
#[derive(Debug)]
pub(crate) enum ContractState {
    /// Parsed, and assembled when it mounts inside contracts: the id and kind of each rule of the
    /// tree.
    Parsed(BTreeMap<String, RuleKind>),
    /// The root mounts inside contracts that the shell has not sent: their repository paths.
    Missing(Vec<String>),
    /// The bytes are not a valid contract, or the tree has a named error.
    Refused(String),
}

/// A contract that the core can use: the root, and the rules of its inside contracts. The core
/// decides only the root rules; each inside rule is a named gap (AD-379).
#[derive(Debug)]
pub(crate) struct Usable {
    pub(crate) root: Contract,
    /// The scoped id and kind of each rule of each mount, in the order of the mounts.
    pub(crate) inside: Vec<(String, RuleKind)>,
    /// True when the root mounts at least one inside contract.
    pub(crate) mounted: bool,
    /// True when a contract of the tree has `declarations.uml`.
    pub(crate) uml: bool,
}

/// The state of the contract input, and the contract when the core can use it.
pub(crate) fn answer(input: ContractInput) -> (ContractState, Option<Usable>) {
    if let Err(message) = bounded(&input.insides) {
        return (ContractState::Refused(message), None);
    }
    let parsed = match archkeel_contract::parse(&input.bytes) {
        Ok(parsed) => parsed,
        Err(error) => return (ContractState::Refused(error.message), None),
    };
    let usable = match parsed {
        ParsedContract::Complete(contract) if input.insides.is_empty() => {
            let uml = has_uml(&contract);
            Usable {
                root: contract,
                inside: Vec::new(),
                mounted: false,
                uml,
            }
        }
        // A root with mounts, or a complete root with files that it does not mount (`Unmounted`).
        parsed => match tree(&input, parsed) {
            Ok(usable) => usable,
            Err(state) => return (state, None),
        },
    };
    let rules = usable
        .root
        .rules()
        .iter()
        .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
        .chain(usable.inside.iter().cloned())
        .collect();
    (ContractState::Parsed(rules), Some(usable))
}

/// The count and size bounds of the inside contracts, checked before any parse.
fn bounded(insides: &[InsideFile]) -> Result<(), String> {
    if insides.len() > MAX_INSIDE_FILES {
        return Err(format!(
            "the request carries {} inside contracts; the core reads at most {MAX_INSIDE_FILES}",
            insides.len()
        ));
    }
    let total = insides
        .iter()
        .fold(0usize, |sum, file| sum.saturating_add(file.bytes.len()));
    if total > MAX_INSIDE_BYTES {
        return Err(format!(
            "the inside contracts hold {total} bytes; the core reads at most {MAX_INSIDE_BYTES}"
        ));
    }
    Ok(())
}

/// Assemble the tree, or the state that names why no tree exists.
fn tree(input: &ContractInput, parsed: ParsedContract) -> Result<Usable, ContractState> {
    let files: Vec<(&str, &str, &[u8])> = input
        .insides
        .iter()
        .map(|file| {
            (
                file.reference.as_str(),
                file.identity.as_str(),
                file.bytes.as_slice(),
            )
        })
        .collect();
    match assemble_tree(&input.path, parsed, &files) {
        Ok(tree) => Ok(usable(&tree)),
        Err(error) => Err(match error.missing_paths() {
            Some(paths) if !paths.is_empty() => ContractState::Missing(paths),
            _ => ContractState::Refused(format!("inside-contract tree: {error}")),
        }),
    }
}

fn usable(tree: &ContractTree) -> Usable {
    let inside = tree
        .mounts()
        .iter()
        .flat_map(|mount| mount.contract().rules())
        .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
        .collect();
    let uml = has_uml(tree.root()) || tree.mounts().iter().any(|m| has_uml(m.contract()));
    Usable {
        root: tree.root().clone(),
        inside,
        mounted: !tree.mounts().is_empty(),
        uml,
    }
}

fn has_uml(contract: &Contract) -> bool {
    contract
        .declarations()
        .as_ref()
        .is_some_and(|declarations| declarations.uml().is_some())
}

/// The reason of a contract state that names a gap, for the rules of the frame.
pub(crate) fn missing_reason(paths: &[String]) -> String {
    format!(
        "{}: {}",
        Reason::Unsupported(Unsupported::InsideTree),
        paths.join(", ")
    )
}

/// The UML target row of a tree with `declarations.uml` in any of its contracts, at `path`, by
/// name: no slice ports it. The reference engine names one target for the whole tree.
pub(crate) fn uml_reason(contract: Option<&Usable>, path: &str) -> Option<(String, Reason)> {
    contract.is_some_and(|usable| usable.uml).then(|| {
        let id = uml_target_id(path).as_text().to_owned();
        (id, Reason::Unsupported(Unsupported::UmlTarget))
    })
}

#[cfg(test)]
#[path = "contract_tests.rs"]
mod tests;
