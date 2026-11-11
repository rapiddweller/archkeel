// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The violations of the S1 rule kinds, with the ids of the Python records.
//!
//! Python: the `classified(...)` calls of `check/evaluation/rules.py` `_assignment_violations`
//! (`stable_id("VIO", rule.id, module record id)`) and `_root_layout_violations`
//! (`stable_id("VIO", rule.id, child)`). The cited record is a module record: its id is
//! `stable_id("MOD", name)` and its evidence is the evidence id of the file.

use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{Module, ModuleId};

/// One violation of a rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Violation {
    /// `complete_assignment`: a module below `source` with zero or many owners.
    Unassigned {
        id: String,
        rule: String,
        source: String,
        module: ModuleId,
        name: String,
        fact_id: String,
        evidence: String,
    },
    /// `root_layout`: a direct child of `root` that is not an allowed child.
    NotAllowedChild {
        id: String,
        rule: String,
        root: String,
        child: String,
        allowed: Vec<String>,
        record: ModuleId,
        fact_id: String,
        evidence: String,
    },
}

impl Violation {
    pub(crate) fn unassigned(rule: &str, source: &str, module: ModuleId, row: &Module) -> Self {
        Violation::Unassigned {
            id: stable_id("VIO", &[Part::Text(rule), Part::Text(row.fact_id())]),
            rule: rule.to_owned(),
            source: source.to_owned(),
            module,
            name: row.name().to_owned(),
            fact_id: row.fact_id().to_owned(),
            evidence: row.evidence().to_owned(),
        }
    }

    pub(crate) fn not_allowed(
        rule: &str,
        root: &str,
        child: &str,
        allowed: &[&str],
        record: ModuleId,
        row: &Module,
    ) -> Self {
        let mut allowed: Vec<String> = allowed.iter().map(|item| (*item).to_owned()).collect();
        allowed.sort();
        Violation::NotAllowedChild {
            id: stable_id("VIO", &[Part::Text(rule), Part::Text(child)]),
            rule: rule.to_owned(),
            root: root.to_owned(),
            child: child.to_owned(),
            allowed,
            record,
            fact_id: row.fact_id().to_owned(),
            evidence: row.evidence().to_owned(),
        }
    }

    /// The id of the violation record.
    pub fn id(&self) -> &str {
        match self {
            Violation::Unassigned { id, .. } | Violation::NotAllowedChild { id, .. } => id,
        }
    }

    /// The rule of the violation.
    pub fn rule(&self) -> &str {
        match self {
            Violation::Unassigned { rule, .. } | Violation::NotAllowedChild { rule, .. } => rule,
        }
    }
}
