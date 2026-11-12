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
//!
//! Slice S5 (AD-380): `_dependency_violations` (`rules.py:99`), `_sibling_violations`
//! (`rules.py:1387`) and `requires_violations` (`rules.py:1877`) cite one import;
//! `_layer_order_violations` (`rules.py:2008`) cites the receipt of the rule and the contract file.
//!
//! Slice S7 (AD-384): `_component_cycle_violations` and `_module_cycle_violations` cite the
//! imports between two members of a cycle.

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
    /// `forbidden_dependency`: an import that the rule rejects.
    Forbidden {
        id: String,
        rule: String,
        cited: Cited,
        symbol: Option<String>,
        under_type_checking: bool,
    },
    /// `sibling_isolation`: an import from the member `source` to another member.
    Peer {
        id: String,
        rule: String,
        cited: Cited,
        source: String,
    },
    /// `complete_requires`: an import between two components that no `requires` entry covers.
    Unrequired {
        id: String,
        rule: String,
        cited: Cited,
        source_component: String,
        target_component: String,
    },
    /// `layer_order`: a `requires` entry from an inner to an outer layer.
    OuterLayer(Box<Layered>),
    /// `no_component_cycles`: a component or a module cycle (slice S7, AD-384).
    Cycle(Box<Cyclic>),
}

/// The record of a cycle violation: its members and the imports between two members.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cyclic {
    pub id: String,
    pub rule: String,
    /// The members, sorted: component labels or module names.
    pub members: Vec<String>,
    /// The ids of the imports between two members, sorted.
    pub facts: Vec<String>,
    /// The evidence of those imports, sorted, with each repeat.
    pub evidence: Vec<String>,
    /// The distinct `(source, target)` module pairs of a module cycle, sorted; `None` for a
    /// component cycle.
    pub edges: Option<Vec<[String; 2]>>,
}

/// The record of a `layer_order` violation: the components, their layers and the contract cites.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Layered {
    pub id: String,
    pub rule: String,
    /// The id of the receipt of the rule (`stable_id("RULE-EVALUATION", scope, rule)`).
    pub receipt: String,
    /// The evidence of the contract file.
    pub evidence: String,
    pub provenance: Vec<String>,
    pub source_component: String,
    pub target_component: String,
    pub source_layer: String,
    pub target_layer: String,
    pub rationale: String,
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

    pub(crate) fn forbidden(rule: &str, import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        Violation::Forbidden {
            id,
            rule,
            cited,
            symbol: import.symbol().map(str::to_owned),
            under_type_checking: import.under_type_checking(),
        }
    }

    pub(crate) fn peer(rule: &str, source: &str, import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        Violation::Peer {
            id,
            rule,
            cited,
            source: source.to_owned(),
        }
    }

    pub(crate) fn unrequired(rule: &str, components: [&str; 2], import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        let [source_component, target_component] = components.map(str::to_owned);
        Violation::Unrequired {
            id,
            rule,
            cited,
            source_component,
            target_component,
        }
    }

    /// The id of the violation record.
    pub fn id(&self) -> &str {
        self.head()[0]
    }

    /// The rule of the violation.
    pub fn rule(&self) -> &str {
        self.head()[1]
    }

    /// The id and the rule.
    fn head(&self) -> [&str; 2] {
        match self {
            Violation::Unassigned { id, rule, .. }
            | Violation::NotAllowedChild { id, rule, .. }
            | Violation::OutsideScope { id, rule, .. }
            | Violation::Undeclared { id, rule, .. }
            | Violation::Forbidden { id, rule, .. }
            | Violation::Peer { id, rule, .. }
            | Violation::Unrequired { id, rule, .. } => [id, rule],
            Violation::OuterLayer(layered) => [&layered.id, &layered.rule],
            Violation::Cycle(cyclic) => [&cyclic.id, &cyclic.rule],
        }
    }
}
