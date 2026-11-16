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
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The source side that the rule names.
        source: String,
        /// The module record that the violation is about.
        module: ModuleId,
        /// The name of the module.
        name: String,
        /// The id of the fact record that the violation cites.
        fact_id: String,
        /// The evidence rows that back the violation.
        evidence: String,
    },
    /// `root_layout`: a direct child of `root` that is not an allowed child.
    NotAllowedChild {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The root whose layout the rule fixes.
        root: String,
        /// The direct child of the root that the rule rejects.
        child: String,
        /// The children that the rule allows.
        allowed: Vec<String>,
        /// The module record that the violation cites.
        record: ModuleId,
        /// The id of the fact record that the violation cites.
        fact_id: String,
        /// The evidence rows that back the violation.
        evidence: String,
    },
    /// `external_dependency_scope`: an import of `dependency` from a source that it does not allow.
    OutsideScope {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The external dependency that the rule names.
        dependency: String,
        /// The import or module record that the violation cites.
        cited: Cited,
    },
    /// `complete_external_scope`: an import below `source` of an external `dependency` that no
    /// rule declares.
    Undeclared {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The source side that the rule names.
        source: String,
        /// The external dependency that the rule names.
        dependency: String,
        /// The import or module record that the violation cites.
        cited: Cited,
    },
    /// `forbidden_dependency`: an import that the rule rejects.
    Forbidden {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The import or module record that the violation cites.
        cited: Cited,
        /// The imported name, when the import names one.
        symbol: Option<String>,
        /// True when the import sits under `TYPE_CHECKING`.
        under_type_checking: bool,
    },
    /// `sibling_isolation`: an import from the member `source` to another member.
    Peer {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The import or module record that the violation cites.
        cited: Cited,
        /// The source side that the rule names.
        source: String,
    },
    /// `complete_requires`: an import between two components that no `requires` entry covers.
    Unrequired {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The import or module record that the violation cites.
        cited: Cited,
        /// The component of the importing module.
        source_component: String,
        /// The component of the imported module.
        target_component: String,
    },
    /// `layer_order`: a `requires` entry from an inner to an outer layer.
    OuterLayer(Box<Layered>),
    /// `no_component_cycles`: a component or a module cycle (slice S7, AD-384).
    Cycle(Box<Cyclic>),
    /// A forbidden construct, with the original observation's identity and evidence.
    Construct(Box<ConstructViolation>),
    /// `boundary_types`: a written type of a public position that breaks the rule (AD-550).
    BoundaryType(Box<BoundaryViolation>),
    /// An import outside the target component's public interface.
    PrivateImport {
        /// The id of the violation record.
        id: String,
        /// The id of the rule that the violation breaks.
        rule: String,
        /// The import or module record that the violation cites.
        cited: Cited,
        /// The imported name, when the import names one.
        symbol: Option<String>,
        /// The component of the importing module.
        source_component: String,
        /// The component of the imported module.
        target_component: String,
    },
}

/// The record of one position that breaks `boundary_types` (AD-550).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BoundaryViolation {
    /// The id of the violation record.
    pub id: String,
    /// The id of the rule that the violation breaks.
    pub rule: String,
    /// `<facade name>:<position>`.
    pub subject: String,
    /// The qualified name of the symbol.
    pub qualified_name: String,
    /// The parameter name, or `return`.
    pub position: String,
    /// The written type.
    pub text: String,
    /// One reason for each leaf that breaks the rule.
    pub reasons: Vec<String>,
    /// The evidence rows that back the violation.
    pub evidence: Vec<String>,
}

/// The row data of a forbidden construct, without a verdict or a scope claim.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConstructViolation {
    /// The id of the violation record.
    pub id: String,
    /// The id of the rule that the violation breaks.
    pub rule: String,
    /// The source side that the rule names.
    pub source: String,
    /// The component that owns the construct.
    pub owner: String,
    /// The name of the construct.
    pub construct: String,
    /// The ids of the facts that the violation rests on.
    pub facts: Vec<String>,
    /// The evidence rows that back the violation.
    pub evidence: Vec<String>,
    /// Where the facts of the violation come from.
    pub provenance: Vec<String>,
    /// The selector of the construct rule.
    pub selector: Option<archkeel_contract::ConstructSelector>,
}

/// The record of a cycle violation: its members and the imports between two members.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cyclic {
    /// The id of the violation record.
    pub id: String,
    /// The id of the rule that the violation breaks.
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
    /// One closed path through the members, in order (AD-484): empty only when the members have
    /// no closed path of imports.
    pub path: Vec<CycleStep>,
}

/// One step of the path of a cycle: two members and the imports that make the step.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CycleStep {
    /// The importing side of the edge.
    pub from: String,
    /// The target of the import as written.
    pub to: String,
    /// The one component that owns each end of a module step; the id of the member of a
    /// component step. `None` for a module without exactly one owner.
    pub from_component: Option<String>,
    /// The component of the target, when it has one.
    pub to_component: Option<String>,
    /// The ids of the imports of the step, sorted.
    pub imports: Vec<String>,
    /// The evidence of those imports, sorted.
    pub evidence: Vec<String>,
}

/// The record of a `layer_order` violation: the components, their layers and the contract cites.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Layered {
    /// The id of the violation record.
    pub id: String,
    /// The id of the rule that the violation breaks.
    pub rule: String,
    /// The id of the receipt of the rule (`stable_id("RULE-EVALUATION", scope, rule)`).
    pub receipt: String,
    /// The evidence of the contract file.
    pub evidence: String,
    /// Where the facts of the violation come from.
    pub provenance: Vec<String>,
    /// The component of the importing module.
    pub source_component: String,
    /// The component of the imported module.
    pub target_component: String,
    /// The layer of the source module.
    pub source_layer: String,
    /// The layer of the target module.
    pub target_layer: String,
    /// Why the rule exists, as the contract states it.
    pub rationale: String,
}

/// The import record that a violation cites.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cited {
    /// The import that the violation cites.
    pub import: String,
    /// The module that holds the import.
    pub source_module: String,
    /// The module that the import reaches.
    pub target_module: String,
    /// The evidence rows that back the violation.
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
    pub(crate) fn private_import(rule: &str, components: [&str; 2], import: &Import) -> Self {
        let (id, rule, cited) = Cited::of(rule, import);
        let [source_component, target_component] = components.map(str::to_owned);
        Self::PrivateImport {
            id,
            rule,
            cited,
            source_component,
            target_component,
            symbol: import.symbol().map(str::to_owned),
        }
    }

    /// The id of the violation record.
    pub(crate) fn boundary(rule: &str, position: &archkeel_model::Position) -> Self {
        let id = stable_id("VIO", &[Part::Text(rule), Part::Text(&position.subject)]);
        let reasons = position
            .leaves
            .iter()
            .map(|leaf| format!("{} is {}", leaf.text, leaf.why))
            .collect();
        Violation::BoundaryType(Box::new(BoundaryViolation {
            id,
            rule: rule.to_owned(),
            subject: position.subject.clone(),
            qualified_name: position.qualified_name.clone(),
            position: position.position.clone(),
            text: position.text.clone(),
            reasons,
            evidence: position.evidence.clone(),
        }))
    }

    /// The id of the violation record, whatever its kind.
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
            | Violation::Unrequired { id, rule, .. }
            | Violation::PrivateImport { id, rule, .. } => [id, rule],
            Violation::OuterLayer(layered) => [&layered.id, &layered.rule],
            Violation::Cycle(cyclic) => [&cyclic.id, &cyclic.rule],
            Violation::Construct(row) => [&row.id, &row.rule],
            Violation::BoundaryType(row) => [&row.id, &row.rule],
        }
    }
}
