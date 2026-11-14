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
use archkeel_model::{Reason, UmlGap, UmlTarget, Unsupported};

/// The most inside contracts of one request. The reference engine has no bound (AD-379).
pub(crate) const MAX_INSIDE_FILES: usize = 1024;
/// The most bytes of all inside contracts of one request. The reference engine has no bound.
pub(crate) const MAX_INSIDE_BYTES: usize = 64 << 20;

/// One inside contract that the shell read: the reference as the mount writes it, the
/// repository-relative path that the shell resolved it to, and the bytes.
#[derive(Clone, Debug)]
pub(crate) struct InsideFile {
    pub(crate) reference: String,
    pub(crate) identity: String,
    pub(crate) bytes: Vec<u8>,
}

/// The root contract at its repository path and the inside contracts that the shell sends.
#[derive(Clone, Debug)]
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

/// A contract that the core can use: the root, the rules of its inside contracts and the
/// assembled tree, from which the model makes one model for each contract (AD-385).
#[derive(Debug)]
pub(crate) struct Usable {
    pub(crate) root: Contract,
    /// The assembled tree of a root that mounts inside contracts.
    pub(crate) tree: Option<ContractTree>,
    /// The scoped id and kind of each rule of each mount, in the order of the mounts.
    pub(crate) inside: Vec<(String, RuleKind)>,
    /// The UML target row input when a contract of the tree has `declarations.uml`.
    pub(crate) uml: Option<UmlTarget>,
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
            let uml = uml_target(&contract, std::iter::empty());
            Usable {
                root: contract,
                tree: None,
                inside: Vec::new(),
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
        Ok(tree) => Ok(usable(tree)),
        Err(error) => Err(match error.missing_paths() {
            Some(paths) if !paths.is_empty() => ContractState::Missing(paths),
            _ => ContractState::Refused(format!("inside-contract tree: {error}")),
        }),
    }
}

fn usable(tree: ContractTree) -> Usable {
    let inside = tree
        .mounts()
        .iter()
        .flat_map(|mount| mount.contract().rules())
        .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
        .collect();
    let mounts = tree.mounts().iter().map(|mount| mount.contract());
    let uml = uml_target(tree.root(), mounts);
    Usable {
        root: tree.root().clone(),
        inside,
        uml,
        tree: Some(tree),
    }
}

/// The input of the one UML target row of a tree: the reference engine names one target for the
/// declared intent of all its contracts (AD-470). The core compares a root target; a target of an
/// inside contract keeps the row UNKNOWN (AD-490). `None` when no contract has `declarations.uml`.
fn uml_target<'a>(
    root: &'a Contract,
    mounts: impl IntoIterator<Item = &'a Contract>,
) -> Option<UmlTarget> {
    let target = |contract: &'a Contract| contract.declarations().as_ref()?.uml().as_ref();
    let mounted = mounts
        .into_iter()
        .any(|contract| target(contract).is_some());
    let Some(found) = target(root) else {
        return mounted.then_some(UmlTarget::Gap(UmlGap::Mounted));
    };
    let empty = found.entities().is_empty()
        && found.relationships().is_empty()
        && found.scopes().is_empty();
    Some(if mounted {
        UmlTarget::Gap(UmlGap::Mounted)
    } else if empty {
        UmlTarget::Gap(UmlGap::Empty)
    } else {
        UmlTarget::Compare(Box::new(found.clone()))
    })
}

/// The reason of a contract state that names a gap, for the rules of the frame.
pub(crate) fn missing_reason(paths: &[String]) -> String {
    format!(
        "{}: {}",
        Reason::Unsupported(Unsupported::InsideTree),
        paths.join(", ")
    )
}

/// The UML target row of a tree with `declarations.uml` in any of its contracts, at `path`: its
/// id and its input (AD-470, AD-490).
pub(crate) fn uml_row(contract: Option<&Usable>, path: &str) -> Option<(String, UmlTarget)> {
    let target = contract?.uml.clone()?;
    Some((uml_target_id(path).as_text().to_owned(), target))
}

#[cfg(test)]
#[path = "contract_tests.rs"]
mod tests;
