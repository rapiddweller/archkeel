// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status fold of one rule.
//!
//! Reference engine: `ir/decisions.py` `_rule_status` and `rule_assessments`. The order is its
//! order: violations give FAIL (a violation is a fact also in an incomplete scope); else the
//! scope proof of the model decides (`Scope::complete`, AD-378): an incomplete observation, a
//! rule without a receipt and a rule with an undecided position give UNKNOWN with the reason;
//! a complete scope gives PASS.

use archkeel_contract::Rule;
use archkeel_model::{Decision, Model};

use crate::violation::Violation;

/// The decision of a rule with these violations.
pub(crate) fn decide(model: &Model, rule: &Rule, violations: &[Violation]) -> Decision {
    if !violations.is_empty() {
        return Decision::fail();
    }
    model.scope(|scope| match scope.complete(rule) {
        Ok(proof) => scope.pass(proof),
        Err(reason) => Decision::unknown(reason),
    })
}
