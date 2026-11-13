// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a failed rule, copied from its evaluated violation without a second verdict.

use archkeel_eval::{Cited, Violation};
use serde::Serialize;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct ViolationDetail {
    source: String,
    target: Option<String>,
    cause: &'static str,
    evidence: Vec<String>,
}

impl ViolationDetail {
    fn cited(cause: &'static str, cited: &Cited) -> Self {
        Self {
            source: cited.source_module.clone(),
            target: Some(cited.target_module.clone()),
            cause,
            evidence: cited.evidence.clone(),
        }
    }

    pub(crate) fn of(violation: &Violation) -> Self {
        match violation {
            Violation::Forbidden { cited, .. } => Self::cited("forbidden dependency", cited),
            Violation::OutsideScope { cited, .. } => Self::cited("dependency outside scope", cited),
            Violation::Undeclared { cited, .. } => {
                Self::cited("undeclared external dependency", cited)
            }
            Violation::Peer { cited, .. } => Self::cited("sibling isolation violation", cited),
            Violation::Unrequired { cited, .. } => {
                Self::cited("undeclared component dependency", cited)
            }
            Violation::Unassigned { name, evidence, .. } => Self {
                source: name.clone(),
                target: None,
                cause: "module has no unique owner",
                evidence: vec![evidence.clone()],
            },
            Violation::NotAllowedChild {
                root,
                child,
                evidence,
                ..
            } => Self {
                source: root.clone(),
                target: Some(child.clone()),
                cause: "child outside root layout",
                evidence: vec![evidence.clone()],
            },
            Violation::OuterLayer(layer) => Self {
                source: layer.source_component.clone(),
                target: Some(layer.target_component.clone()),
                cause: "dependency violates layer order",
                evidence: vec![layer.evidence.clone()],
            },
            Violation::Cycle(cycle) => Self {
                source: cycle.members.join(" -> "),
                target: cycle.members.first().cloned(),
                cause: "dependency cycle",
                evidence: cycle.evidence.clone(),
            },
            Violation::Construct(row) => Self {
                source: format!("{} ({})", row.owner, row.construct),
                target: None,
                cause: "forbidden construct",
                evidence: row.evidence.clone(),
            },
        }
    }
}
