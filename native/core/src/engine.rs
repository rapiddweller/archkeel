// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine of one run: it keeps the contract and the reply and gives each request to the
//! module that answers it. Each request has a file of its own (`contract`, `ingest`, `rules`,
//! `sections`, `report`), so that the slices change different files.

use archkeel_contract::Contract;
use archkeel_model::{Graph, Input, Model, Reason, Settings};
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
    Settings,
}

/// One run: the parsed contract, the validated reply, the settings and what they derive.
#[derive(Default)]
pub(crate) struct Engine {
    contract: Option<Contract>,
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
    Model(Model),
    Graph(Graph, Reason),
    Neither { graph: Reason, model: Reason },
}

impl Derived {
    /// The reply part of the model, or the reason that the run has none.
    pub(crate) fn graph(&self) -> Result<&Graph, Reason> {
        match self {
            Derived::Model(model) => Ok(model.graph()),
            Derived::Graph(graph, _) => Ok(graph),
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
            Request::Contract(bytes) => {
                let (state, contract) = crate::contract::answer(&bytes);
                self.contract = contract;
                self.derived = None;
                Answer::Contract(state)
            }
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
                    Some(contract) => crate::rules::outcomes(contract, derived.model()),
                    None => Vec::new(),
                };
                Answer::Sections(crate::sections::answer(derived, &outcomes, &sections))
            }
            Request::Rules => {
                let (contract, derived) = self.derived();
                Answer::Rules(crate::rules::answer(contract, derived.model()))
            }
            Request::Report => Answer::Report(crate::report::answer()),
        }
    }

    /// The parsed contract.
    pub(crate) fn contract(&self) -> Option<&Contract> {
        self.contract.as_ref()
    }

    /// The contract and the derivation of the inputs. The derivation is made one time and kept
    /// until an input changes.
    pub(crate) fn derived(&mut self) -> (Option<&Contract>, &Derived) {
        let (contract, reply, settings) = (&self.contract, &self.reply, &self.settings);
        let derivations = &mut self.derivations;
        let derived = self.derived.get_or_insert_with(|| {
            *derivations += 1;
            derive(contract.as_ref(), reply.as_ref(), settings.as_ref())
        });
        (contract.as_ref(), derived)
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
            Ok(graph) => Derived::Graph(graph, model),
            Err(graph) => Derived::Neither { graph, model },
        };
    };
    match (graph, Model::components_of(contract)) {
        (Ok(graph), Ok(components)) => Derived::Model(Model::of(components, graph)),
        (Ok(graph), Err(model)) => Derived::Graph(graph, model),
        (Err(graph), _) => Derived::Neither {
            model: graph.clone(),
            graph,
        },
    }
}

#[cfg(test)]
#[path = "engine_tests.rs"]
pub(crate) mod tests;
