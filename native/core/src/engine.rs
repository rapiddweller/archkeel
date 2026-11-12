// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine of one run: it keeps the contract and the reply and gives each request to the
//! module that answers it. Each request has a file of its own (`contract`, `ingest`, `rules`,
//! `sections`, `report`), so that the slices change different files.

use archkeel_contract::Contract;
use archkeel_model::{Graph, Input, Model, Reason, Settings};
use archkeel_store::Ingested;

use crate::contract::{ContractInput, ContractState, Usable};
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
    Settings,
}

/// One run: the parsed contract, the validated reply, the settings and what they derive.
#[derive(Default)]
pub(crate) struct Engine {
    /// The root contract and the rules of its inside contracts (AD-379).
    contract: Option<Usable>,
    reply: Option<Ingested>,
    settings: Option<Settings>,
    /// The derivation of the inputs above, made at the first request that needs it and dropped
    /// when an input changes. So a run derives its model one time (#1059).
    derived: Option<Derived>,
    /// The number of derivations of this run; a test reads it.
    derivations: usize,
}

/// What the inputs of a run derive: the model, or only its reply part, or neither, with the
/// reason of each missing part.
pub(crate) enum Derived {
    Model(Box<Model>),
    Graph(Box<Graph>, Reason),
    Neither { graph: Reason, model: Reason },
}

impl Derived {
    /// The reply part of the model, or the reason that the run has none.
    pub(crate) fn graph(&self) -> Result<&Graph, Reason> {
        match self {
            Derived::Model(model) => Ok(model.graph()),
            Derived::Graph(graph, _) => Ok(graph.as_ref()),
            Derived::Neither { graph, .. } => Err(graph.clone()),
        }
    }

    /// The model, or the reason that the run has none: a missing contract, reply or settings.
    pub(crate) fn model(&self) -> Result<&Model, Reason> {
        match self {
            Derived::Model(model) => Ok(model),
            Derived::Graph(_, model) | Derived::Neither { model, .. } => Err(model.clone()),
        }
    }
}

impl Engine {
    pub(crate) fn answer(&mut self, request: Request) -> Answer {
        match request {
            Request::Contract(input) => self.take_contract(input),
            Request::Ingest {
                reply,
                inflate_limit,
            } => {
                let (state, ingested) = crate::ingest::answer(&reply, inflate_limit);
                self.reply = ingested;
                self.derived = None;
                Answer::Reply(state)
            }
            Request::Settings(settings) => {
                self.settings = Some(settings);
                self.derived = None;
                Answer::Settings
            }
            Request::Sections(sections) => {
                let (contract, derived) = self.derived();
                let outcomes = match contract {
                    Some(_) => crate::rules::outcomes(derived.model()),
                    None => Vec::new(),
                };
                let derivation = (derived.graph(), derived.model());
                Answer::Sections(crate::sections::answer(derivation, &outcomes, &sections))
            }
            Request::Rules => {
                let tree = self.contract.as_ref().map(crate::rules::Tree::of);
                let (contract, derived) = self.derived();
                Answer::Rules(crate::rules::answer(contract, derived.model(), tree))
            }
            Request::Report => Answer::Report(crate::report::answer()),
        }
    }

    fn take_contract(&mut self, input: ContractInput) -> Answer {
        let (state, contract) = crate::contract::answer(input);
        self.contract = contract;
        self.derived = None;
        Answer::Contract(state)
    }

    /// The usable contract: the root and the rules of its inside contracts.
    pub(crate) fn usable(&self) -> Option<&Usable> {
        self.contract.as_ref()
    }

    /// The contract and the derivation of the inputs. The derivation is made one time and kept
    /// until an input changes.
    pub(crate) fn derived(&mut self) -> (Option<&Contract>, &Derived) {
        let contract = self.contract.as_ref().map(|usable| &usable.root);
        let (reply, settings) = (&self.reply, &self.settings);
        let derivations = &mut self.derivations;
        let derived = self.derived.get_or_insert_with(|| {
            *derivations += 1;
            derive(contract, reply.as_ref(), settings.as_ref())
        });
        (contract, derived)
    }

    /// The number of derivations of this run.
    #[cfg(test)]
    pub(crate) fn derivations(&self) -> usize {
        self.derivations
    }
}

/// Derive the reply part, then the model when the run has a contract.
fn derive(
    contract: Option<&Contract>,
    reply: Option<&Ingested>,
    settings: Option<&Settings>,
) -> Derived {
    let graph = match (reply, settings) {
        (Some(reply), Some(settings)) => Graph::derive(reply, settings.clone()),
        (None, _) => Err(Reason::MissingInput(Input::Reply)),
        (_, None) => Err(Reason::MissingInput(Input::Settings)),
    };
    let Some(contract) = contract else {
        let model = Reason::MissingInput(Input::Contract);
        return match graph {
            Ok(graph) => Derived::Graph(Box::new(graph), model),
            Err(graph) => Derived::Neither { graph, model },
        };
    };
    match graph.map(|graph| Model::of(contract, graph)) {
        Ok(Ok(model)) => Derived::Model(Box::new(model)),
        Ok(Err(refused)) => {
            let (graph, model) = *refused;
            Derived::Graph(Box::new(graph), model)
        }
        Err(graph) => Derived::Neither {
            model: graph.clone(),
            graph,
        },
    }
}

#[cfg(test)]
#[path = "engine_tests.rs"]
pub(crate) mod tests;
