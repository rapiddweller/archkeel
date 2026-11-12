// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status fold of one rule of S1.
//!
//! Reference engine: `ir/decisions.py` `_rule_status` and `rule_assessments`. The order is its
//! order: violations give FAIL; an incomplete observation gives UNKNOWN; a rule without a receipt
//! (`rules.py` `_rule_evaluation_facts_for_rule` issues none for an empty selection) gives
//! UNKNOWN; else PASS. The core does not see every cause of an incomplete observation yet
//! (the rule subject failures of all rules, the unknown imports, the profile limits): only the
//! scope proof of S4 sees them, so a PASS goes through `Scope::complete`.

use archkeel_model::{Decision, Model, Reason};

use crate::violation::Violation;

/// The decision of a rule with these violations, and whether it selects a module of the reply.
pub(crate) fn decide(model: &Model, violations: &[Violation], selected: bool) -> Decision {
    if !violations.is_empty() {
        return Decision::fail();
    }
    if let Some(incomplete) = model.graph().incomplete() {
        return Decision::unknown(Reason::Incomplete(incomplete));
    }
    if !selected {
        return Decision::unknown(Reason::NoSubjects);
    }
    model.scope(|scope| match scope.complete() {
        Ok(proof) => scope.pass(proof),
        Err(reason) => Decision::unknown(reason),
    })
}
