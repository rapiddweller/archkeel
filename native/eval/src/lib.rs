// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-eval: the rule families over the model (AD-359, AD-363, AD-370; epic #880).
//!
//! Each rule gives one `Outcome`. An outcome holds a `Decision`, never a bare `Verdict`: a PASS
//! comes only from the scope proof of the model (AD-363). A rule kind that no slice has ported
//! answers `Unsupported::Rule` by name.
//!
//! Slice S1 decides `complete_assignment` and `root_layout`: they read only the modules, the
//! packages and the owners of the model. A violation is a fact also in an incomplete scope, so
//! FAIL needs no proof. Each other verdict comes from the scope proof of the model (slice S4,
//! AD-378): PASS with the proof, else UNKNOWN with its reason.
//!
//! Slice S2 decides `external_dependency_scope` and `complete_external_scope`: they read only the
//! resolved imports with their typed targets, the modules and the owners (AD-372).
//!
//! An inside-contract tree (AD-385): each contract of the tree has its own model with the source
//! domain of its mount, and each rule reads the model of its own contract (`evaluate_tree`).
//!
//! Slice S5 decides the direction kinds (AD-380): `forbidden_dependency`, `sibling_isolation`,
//! `complete_requires` and `layer_order`. An `allowed_dependency` rule is a permission
//! declaration: the reference engine gives it no verdict (`ir/decisions.py` `_rule_status`), so
//! its outcome holds no decision.
//!
//! Slice S7 decides `no_component_cycles` at component and module level (AD-384).
//!
//! # The barrier of the evaluator (AD-381)
//!
//! The twin that compiles:
//!
//! ```
//! fn outcomes(model: &archkeel_model::Model) -> Vec<archkeel_eval::Outcome> {
//!     archkeel_eval::evaluate(model)
//! }
//! ```
//!
//! E1. The rules of another contract next to a model: `evaluate` reads only the contract of
//!     the model, so a sibling rule of the caller cannot change a verdict (E0061).
//!
//! ```compile_fail,E0061
//! use archkeel_contract::Contract;
//! use archkeel_model::Model;
//! fn forge(other: &Contract, model: &Model) -> Vec<archkeel_eval::Outcome> {
//!     archkeel_eval::evaluate(other, model)
//! }
//! ```

#![deny(unreachable_pub)]

mod assignment;
mod constructs;
mod cycles;
mod decide;
mod direction;
mod external;
mod interface;
mod layout;
mod violation;

#[cfg(test)]
mod construct_tests;

#[cfg(test)]
mod layout_citation_tests;

use archkeel_contract::{head_of, kind_of, Rule, RuleKind};
use archkeel_model::{Decision, Model, ModelTree, Part, Reason, Unsupported, Verdict};

pub use violation::{Cited, ConstructViolation, Cyclic, Layered, Violation};

/// The result of one rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    rule: String,
    kind: RuleKind,
    /// `None` for a permission declaration, which has no verdict.
    decision: Option<Decision>,
    violations: Vec<Violation>,
}

impl Outcome {
    /// The rule id.
    pub fn rule(&self) -> &str {
        &self.rule
    }

    /// The rule kind.
    pub fn kind(&self) -> RuleKind {
        self.kind
    }

    /// The decision: the verdict, and the reason of an UNKNOWN. A permission declaration
    /// (`allowed_dependency`) has none: it is neither PASS, FAIL nor UNKNOWN.
    pub fn decision(&self) -> Option<&Decision> {
        self.decision.as_ref()
    }

    /// The violations of the rule, in the order of their ids.
    pub fn violations(&self) -> &[Violation] {
        &self.violations
    }
}

/// The outcome of each rule of the contract of the model, in contract order. The rules and the
/// sibling rules come only from `model.contract()`: a caller cannot pass another contract, so a
/// rule of another contract cannot change a verdict (AD-381, B1 of the review of #1080).
pub fn evaluate(model: &Model) -> Vec<Outcome> {
    let rules = model.contract().rules();
    rules
        .iter()
        .map(|rule| outcome(rule, rules, model))
        .collect()
}

/// The outcome of each rule of each contract of a tree: the root rules first, then the rules of
/// each mount in the order of the walk. Each rule reads the model of its own contract (AD-385).
pub fn evaluate_tree(tree: &ModelTree) -> Vec<Outcome> {
    tree.models().flat_map(evaluate).collect()
}

fn outcome(rule: &Rule, rules: &[Rule], model: &Model) -> Outcome {
    let id = head_of(rule).id().as_text();
    let kind = kind_of(rule);
    let found = match rule {
        Rule::CompleteAssignment(rule) => Ok(assignment::check(id, rule, model)),
        Rule::RootLayout(rule) => layout::check(id, rule, model),
        Rule::ExternalDependencyScope(rule) => Ok(external::dependency_scope(id, rule, model)),
        Rule::CompleteExternalScope(rule) => Ok(external::complete_scope(id, rule, rules, model)),
        Rule::ForbiddenDependency(rule) => Ok(direction::forbidden(id, rule, model)),
        Rule::SiblingIsolation(rule) => Ok(direction::siblings(id, rule, model)),
        Rule::CompleteRequires(rule) => Ok(direction::requires(id, rule, model)),
        Rule::LayerOrder(rule) => direction::layers(id, rule, model),
        Rule::AllowedDependency(_) => return outcome_of(id, kind, None, Vec::new()),
        // Each kind that no slice decides names its kind; a new kind needs an arm here.
        Rule::NoComponentCycles(rule) => Ok(cycles::check(id, rule, model)),
        Rule::InterfaceBoundary(rule) => Ok(interface::check(id, rule, model)),
        Rule::ForbiddenConstruct(rule) => constructs::check(id, rule, model),
        Rule::SymbolPlacement(_) => unported(kind), // S12, Cut B
        Rule::SourceOwnership(_) => unported(kind),
        Rule::BoundedNumericOperand(_) => unported(kind),
        Rule::CallOwner(_) => unported(kind),             // S13
        Rule::ForbiddenCallArgument(_) => unported(kind), // S14
        Rule::CatalogArgument(_) => unported(kind),
        Rule::CatalogUse(_) => unported(kind),
        Rule::ForbiddenEffectUnderCondition(_) => unported(kind), // S15
        Rule::ProtocolDeclarations(_) => unported(kind),          // S16
        Rule::BoundaryTypes(_) => unported(kind),                 // S17
    };
    let violations = match found {
        Ok(found) => found,
        Err(reason) => return outcome_of(id, kind, Some(Decision::unknown(reason)), Vec::new()),
    };
    let mut decision = decide::decide(model, rule, &violations);
    // AD-378: a PASS must name this rule of this model; a type cannot stop a value of another
    // rule or model from moving here, so the identity is checked.
    if matches!(decision.verdict(), Verdict::Pass(_)) && !decision.passes(model, id) {
        decision = Decision::unknown(Part::ForeignRule.into());
    }
    outcome_of(id, kind, Some(decision), violations)
}

/// The reason of a kind that no slice decides yet.
fn unported(kind: RuleKind) -> Result<Vec<Violation>, Reason> {
    Err(Reason::Unsupported(Unsupported::Rule(kind)))
}

fn outcome_of(
    id: &str,
    kind: RuleKind,
    decision: Option<Decision>,
    violations: Vec<Violation>,
) -> Outcome {
    Outcome {
        rule: id.to_owned(),
        kind,
        decision,
        violations,
    }
}

#[cfg(test)]
#[path = "eval_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "external_tests.rs"]
mod external_tests;

#[cfg(test)]
#[path = "graph_tests.rs"]
mod graph_tests;

#[cfg(test)]
#[path = "scope_tests.rs"]
mod scope_tests;

#[cfg(test)]
#[path = "receipt_tests.rs"]
mod receipt_tests;

#[cfg(test)]
#[path = "direction_tests.rs"]
mod direction_tests;

#[cfg(test)]
#[path = "direction_scope_tests.rs"]
mod direction_scope_tests;

#[cfg(test)]
#[path = "gap_scope_tests.rs"]
mod gap_scope_tests;

#[cfg(test)]
#[path = "cycle_receipt_tests.rs"]
mod cycle_receipt_tests;

#[cfg(test)]
#[path = "drop_rule_tests.rs"]
mod drop_rule_tests;

#[cfg(test)]
#[path = "tree_tests.rs"]
mod tree_tests;

#[cfg(test)]
#[path = "tree_scope_tests.rs"]
mod tree_scope_tests;

#[cfg(test)]
#[path = "tree_edge_tests.rs"]
mod tree_edge_tests;

#[cfg(test)]
#[path = "dropped_gap_tests.rs"]
mod dropped_gap_tests;

#[cfg(test)]
#[path = "scoped_requires_tests.rs"]
mod scoped_requires_tests;
