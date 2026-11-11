// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Contract` request: parse the contract bytes that the shell sends.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, uml_target_id, Contract, ParsedContract, RuleKind};
use archkeel_model::{Reason, Unsupported};

/// What the engine knows of the contract.
#[derive(Debug)]
pub(crate) enum ContractState {
    /// Parsed: the id and kind of each rule.
    Parsed(BTreeMap<String, RuleKind>),
    /// A contract that the core cannot use yet: it mounts inside contracts.
    Unsupported(Reason),
    /// The bytes are not a valid contract.
    Refused(String),
}

/// The state of the contract bytes, and the contract when it parses.
pub(crate) fn answer(bytes: &[u8]) -> (ContractState, Option<Contract>) {
    match archkeel_contract::parse(bytes) {
        Ok(ParsedContract::Complete(contract)) => {
            let rules = contract
                .rules()
                .iter()
                .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
                .collect();
            (ContractState::Parsed(rules), Some(contract))
        }
        // The core takes a complete contract only: a contract with mounts is never used in part.
        Ok(ParsedContract::NeedsTree(_)) => {
            let reason = Reason::Unsupported(Unsupported::InsideTree);
            (ContractState::Unsupported(reason), None)
        }
        Err(error) => (ContractState::Refused(error.message), None),
    }
}

/// The reason of each rule of the parsed contract: no rule family is ported yet. A contract with
/// `declarations.uml` also has the UML target row of the contract at `path`, by name.
pub(crate) fn rule_reasons(contract: Option<&Contract>, path: &str) -> BTreeMap<String, Reason> {
    let mut reasons: BTreeMap<String, Reason> = contract
        .into_iter()
        .flat_map(Contract::rules)
        .map(|rule| {
            let reason = Reason::Unsupported(Unsupported::Rule(kind_of(rule)));
            (head_of(rule).id().as_text().to_owned(), reason)
        })
        .collect();
    let uml = contract
        .and_then(|item| item.declarations().as_ref())
        .is_some_and(|declarations| declarations.uml().is_some());
    if uml {
        let id = uml_target_id(path).as_text().to_owned();
        reasons.insert(id, Reason::Unsupported(Unsupported::UmlTarget));
    }
    reasons
}
