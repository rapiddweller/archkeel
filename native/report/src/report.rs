// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The decided mark of the engine ruling.

use crate::head::Status;
use archkeel_model::{Decision, RunPass};

/// The mark of a report built from the Decision of the evaluator. It keeps that Decision.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decided {
    pub(crate) status: Status,
    pub(crate) pass: Option<RunPass>,
    pub(crate) observation: Status,
    pub(crate) rules: Vec<(String, Option<Decision>)>,
}

impl Decided {
    /// The status of the run.
    pub fn status(&self) -> Status {
        self.status
    }

    /// The run proof of the model (L-35b, AD-381); only a PASS status has one.
    pub fn pass(&self) -> Option<&RunPass> {
        self.pass.as_ref()
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
