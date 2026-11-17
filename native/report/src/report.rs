// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The decided mark of the engine ruling.

use crate::head::Status;
use archkeel_model::{Decision, RunPass};

/// The status of a run with its proof: a PASS carries the run proof of the model (L-35b, AD-381),
/// so a PASS without a proof and a proof without a PASS cannot be written.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum RunStatus {
    /// Every rule passes and the model proves the scope.
    Pass(RunPass),
    /// A rule is violated.
    Fail,
    /// Something is not decided.
    Unknown,
}

/// The mark of a report built from the Decision of the evaluator. It keeps that Decision.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decided {
    pub(crate) run: RunStatus,
    pub(crate) observation: Status,
    pub(crate) rules: Vec<(String, Option<Decision>)>,
}

impl Decided {
    /// The status of the run, derived from its `RunStatus`.
    pub fn status(&self) -> Status {
        match self.run {
            RunStatus::Pass(_) => Status::Pass,
            RunStatus::Fail => Status::Fail,
            RunStatus::Unknown => Status::Unknown,
        }
    }

    /// The run proof of the model; only a PASS status has one.
    pub fn pass(&self) -> Option<&RunPass> {
        match &self.run {
            RunStatus::Pass(proof) => Some(proof),
            RunStatus::Fail | RunStatus::Unknown => None,
        }
    }

    /// The completeness of the observation: PASS only for a complete scope of the model.
    pub fn observation(&self) -> Status {
        self.observation
    }

    /// The Decision of one rule by id; `None` inside for a permission declaration.
    pub fn rule(&self, id: &str) -> Option<Option<&Decision>> {
        self.rules
            .iter()
            .find(|(rule, _)| rule == id)
            .map(|(_, decision)| decision.as_ref())
    }
}
