// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Contract` request: parse the contract bytes that the shell sends.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, Contract, ErrorKind, ParseError, RuleKind};
use archkeel_model::{Reason, Unsupported};

/// What the engine knows of the contract.
#[derive(Debug)]
pub(crate) enum ContractState {
    /// Parsed: the id and kind of each rule.
    Parsed(BTreeMap<String, RuleKind>),
    /// A part of the grammar that is not ported yet.
    Unsupported(Reason),
    /// The bytes are not a valid contract.
    Refused(String),
}

/// The state of the contract bytes, and the contract when it parses.
pub(crate) fn answer(bytes: &[u8]) -> (ContractState, Option<Contract>) {
    match archkeel_contract::parse(bytes) {
        Ok(contract) => {
            let rules = contract
                .rules()
                .iter()
                .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
                .collect();
            (ContractState::Parsed(rules), Some(contract))
        }
        Err(ParseError {
            kind: ErrorKind::Unsupported(part),
            ..
        }) => {
            let reason = Reason::Unsupported(Unsupported::Contract(part));
            (ContractState::Unsupported(reason), None)
        }
        Err(error) => (ContractState::Refused(error.message), None),
    }
}

/// The reason of each rule of the parsed contract: no rule family is ported yet.
pub(crate) fn rule_reasons(contract: Option<&Contract>) -> BTreeMap<String, Reason> {
    contract
        .into_iter()
        .flat_map(Contract::rules)
        .map(|rule| {
            let reason = Reason::Unsupported(Unsupported::Rule(kind_of(rule)));
            (head_of(rule).id().as_text().to_owned(), reason)
        })
        .collect()
}
