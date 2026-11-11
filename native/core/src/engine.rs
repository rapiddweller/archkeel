// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine of one run: it keeps the contract and the reply and answers each request.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, Contract, ErrorKind, ParseError, RuleKind};
use archkeel_model::{Model, Reason, Section, Unsupported};
use archkeel_store::Ingested;

use crate::request::Request;

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

/// The answer to one request.
#[derive(Debug)]
pub(crate) enum Answer {
    Contract(ContractState),
    /// The reply is valid: its file count.
    Ingested(usize),
    /// The store refused the reply.
    ReplyRefused(String),
    /// Each requested section with its rows or the reason that it has none.
    Sections(Vec<(Section, Reason)>),
    /// A request that the core cannot answer yet.
    Unsupported(Reason),
}

/// One run: the parsed contract and the validated reply.
#[derive(Default)]
pub(crate) struct Engine {
    contract: Option<Contract>,
    reply: Option<Ingested>,
}

impl Engine {
    pub(crate) fn answer(&mut self, request: Request) -> Answer {
        match request {
            Request::Contract(bytes) => Answer::Contract(self.contract(&bytes)),
            Request::Ingest {
                reply,
                inflate_limit,
            } => match archkeel_store::ingest_reply(&reply, inflate_limit) {
                Ok(ingested) => {
                    let files = ingested.file_count();
                    self.reply = Some(ingested);
                    Answer::Ingested(files)
                }
                Err(message) => Answer::ReplyRefused(message),
            },
            Request::Sections(sections) => Answer::Sections(self.sections(&sections)),
            Request::Report => Answer::Unsupported(Reason::Unsupported(Unsupported::Report)),
        }
    }

    fn contract(&mut self, bytes: &[u8]) -> ContractState {
        match archkeel_contract::parse(bytes) {
            Ok(contract) => {
                let rules = contract
                    .rules()
                    .iter()
                    .map(|rule| (head_of(rule).id().as_text().to_owned(), kind_of(rule)))
                    .collect();
                self.contract = Some(contract);
                ContractState::Parsed(rules)
            }
            Err(ParseError {
                kind: ErrorKind::Unsupported(part),
                ..
            }) => ContractState::Unsupported(Reason::Unsupported(Unsupported::Contract(part))),
            Err(error) => ContractState::Refused(error.message),
        }
    }

    /// The model, when both the contract and the reply are in.
    fn model(&self) -> Option<Result<Model, Reason>> {
        Some(Model::derive(self.contract.as_ref()?, self.reply.as_ref()?))
    }

    fn sections(&self, sections: &[Section]) -> Vec<(Section, Reason)> {
        let model = self.model();
        sections
            .iter()
            .map(|section| {
                let reason = match &model {
                    Some(Ok(model)) => match model.rows(*section) {
                        Ok(rows) => match rows {},
                        Err(reason) => reason,
                    },
                    Some(Err(reason)) => reason.clone(),
                    None => Reason::Unsupported(Unsupported::Section(*section)),
                };
                (*section, reason)
            })
            .collect()
    }

    /// The reason of each rule of the parsed contract: no rule family is ported yet.
    pub(crate) fn rule_reasons(&self) -> BTreeMap<String, Reason> {
        self.contract
            .iter()
            .flat_map(Contract::rules)
            .map(|rule| {
                let reason = Reason::Unsupported(Unsupported::Rule(kind_of(rule)));
                (head_of(rule).id().as_text().to_owned(), reason)
            })
            .collect()
    }
}

#[cfg(test)]
#[path = "engine_tests.rs"]
pub(crate) mod tests;
