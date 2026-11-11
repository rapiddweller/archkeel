// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The violations of the S1 rule kinds, with the ids of the records of the reference engine.
//!
//! Reference engine: the `classified(...)` calls of `check/evaluation/rules.py` `_assignment_violations`,
//! `_external_dependency_violations` and `_external_completeness_violations`
//! (`stable_id("VIO", rule.id, import record id)`),
//! (`stable_id("VIO", rule.id, module record id)`) and `_root_layout_violations`
//! (`stable_id("VIO", rule.id, child)`). The cited record is a module record: its id is
//! `stable_id("MOD", name)` and its evidence is the evidence id of the file.

use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{Import, Module, ModuleId};

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
    /// `external_dependency_scope`: an import of `dependency` from a source that it does not allow.
    OutsideScope {
        id: String,
        rule: String,
        dependency: String,
        cited: Cited,
    },
    /// `complete_external_scope`: an import below `source` of an external `dependency` that no
    /// rule declares.
    Undeclared {
        id: String,
        rule: String,
        source: String,
        dependency: String,
        cited: Cited,
    },
}

/// The import record that a violation cites.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cited {
    pub import: String,
    pub source_module: String,
    pub target_module: String,
    pub evidence: Vec<String>,
}

impl Cited {
    /// The violation id (`stable_id("VIO", rule, import id)`), the rule and the cited import.
    fn of(rule: &str, import: &Import) -> (String, String, Self) {
        let id = stable_id("VIO", &[Part::Text(rule), Part::Text(import.id())]);
        let cited = Cited {
            import: import.id().to_owned(),
            source_module: import.source_module().to_owned(),
            target_module: import.target_module().to_owned(),
            evidence: import.evidence().to_vec(),
        };
        (id, rule.to_owned(), cited)
    }
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

    pub(crate) fn outside_scope(rule: &str, dependency: &str, import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        let dependency = dependency.to_owned();
        Violation::OutsideScope {
            id,
            rule,
            dependency,
            cited,
        }
    }

    pub(crate) fn undeclared(rule: &str, source: &str, dependency: &str, import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        let (source, dependency) = (source.to_owned(), dependency.to_owned());
        Violation::Undeclared {
            id,
            rule,
            source,
            dependency,
            cited,
        }
    }

    /// The id of the violation record.
    pub fn id(&self) -> &str {
        match self {
            Violation::Unassigned { id, .. }
            | Violation::NotAllowedChild { id, .. }
            | Violation::OutsideScope { id, .. }
            | Violation::Undeclared { id, .. } => id,
        }
    }

    /// The rule of the violation.
    pub fn rule(&self) -> &str {
        match self {
            Violation::Unassigned { rule, .. }
            | Violation::NotAllowedChild { rule, .. }
            | Violation::OutsideScope { rule, .. }
            | Violation::Undeclared { rule, .. } => rule,
        }
    }
}
