// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine of one run: it keeps the contract and the reply and gives each request to the
//! module that answers it. Each request has a file of its own (`contract`, `ingest`, `rules`,
//! `sections`, `report`), so that the slices change different files.

use archkeel_contract::Contract;
use archkeel_model::{Model, Reason};
use archkeel_store::Ingested;

use crate::contract::ContractState;
use crate::ingest::ReplyState;
use crate::request::Request;
use crate::rules::RuleAnswer;
use crate::sections::SectionAnswer;

/// The answer to one request.
#[derive(Debug)]
pub(crate) enum Answer {
    Contract(ContractState),
    Reply(ReplyState),
    Sections(Vec<SectionAnswer>),
    Rules(RuleAnswer),
    Report(Reason),
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
            Request::Contract(bytes) => {
                let (state, contract) = crate::contract::answer(&bytes);
                self.contract = contract;
                Answer::Contract(state)
            }
            Request::Ingest {
                reply,
                inflate_limit,
            } => {
                let (state, ingested) = crate::ingest::answer(&reply, inflate_limit);
                self.reply = ingested;
                Answer::Reply(state)
            }
            Request::Sections(sections) => {
                let model = self.model();
                let outcomes = match self.contract.as_ref() {
                    Some(contract) => crate::rules::outcomes(contract, &model),
                    None => Vec::new(),
                };
                Answer::Sections(crate::sections::answer(&model, &outcomes, &sections))
            }
            Request::Rules => {
                Answer::Rules(crate::rules::answer(self.contract.as_ref(), &self.model()))
            }
            Request::Report => Answer::Report(crate::report::answer()),
        }
    }

    /// The parsed contract.
    pub(crate) fn contract(&self) -> Option<&Contract> {
        self.contract.as_ref()
    }

    /// The model, or the reason that the run has none: a missing contract or reply.
    pub(crate) fn model(&self) -> Result<Model, Reason> {
        let contract = self.contract.as_ref();
        let contract = contract.ok_or(Reason::MissingInput(archkeel_model::Input::Contract))?;
        let reply = self.reply.as_ref();
        let reply = reply.ok_or(Reason::MissingInput(archkeel_model::Input::Reply))?;
        Model::derive(contract, reply)
    }
}

#[cfg(test)]
#[path = "engine_tests.rs"]
pub(crate) mod tests;
