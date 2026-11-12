// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receipt and the rule check of `Scope::complete` (slice S4, AD-378): a proof is only for a
//! rule of the contract of the model, of a kind whose receipt the model knows.

use archkeel_model::{Decision, Model, Part, Reason, Unsupported, Verdict};
use serde_json::{json, Value};

use crate::tests::{contract, decision, reply, set_component, set_rule, shop_settings};

fn unchanged(_: &mut Value) {}

fn unread(part: Part) -> Reason {
    Reason::Unsupported(Unsupported::ScopeProof(part))
}

#[test]
fn a_planned_module_passes_the_subject_check_but_gives_no_receipt() {
    // The planned module matches the source, so the observation stays complete; no module of
    // the reply lies below the source, so the rule has no receipt (`NoSubjects`).
    let outcomes = crate::tests::run(
        |c| {
            set_component(c, "COMP-DATA", "planned", json!(["shop.absent.later"]));
            set_rule(c, "ASSIGNMENT", "source", json!("shop.absent"));
        },
        unchanged,
    );
    let expected = Decision::unknown(Reason::NoSubjects);
    assert_eq!(decision(&outcomes, "ASSIGNMENT"), Some(expected));
    assert!(decision(&outcomes, "LAYOUT").is_some_and(|d| matches!(d.verdict(), Verdict::Pass(_))));
}

#[test]
fn a_rule_of_another_contract_gets_no_proof() {
    let (Some(own), Some(other), Some(reply)) = (
        contract(unchanged),
        contract(|c| c["rules"][1]["source"] = json!("shop.src")),
        reply(unchanged),
    ) else {
        return assert_eq!("the inputs load", "");
    };
    let Ok(model) = Model::derive(&own, &reply, shop_settings()) else {
        return assert_eq!("the model derives", "");
    };
    let rule = &other.rules()[1];
    let reason = model.scope(|scope| scope.complete(rule).err());
    assert_eq!(reason, Some(unread(Part::ForeignRule)));
    let own_rule = &own.rules()[1];
    assert!(model.scope(|scope| scope.complete(own_rule).is_ok()));
}

#[test]
fn a_kind_whose_receipt_the_model_does_not_know_gets_no_proof() {
    let (Some(own), Some(reply)) = (contract(unchanged), reply(unchanged)) else {
        return assert_eq!("the inputs load", "");
    };
    let Ok(model) = Model::derive(&own, &reply, shop_settings()) else {
        return assert_eq!("the model derives", "");
    };
    for rule in own.rules() {
        let kind = archkeel_contract::kind_of(rule);
        let reason = model.scope(|scope| scope.complete(rule).err());
        use archkeel_contract::RuleKind as K;
        let expected = match kind {
            K::CompleteAssignment
            | K::RootLayout
            | K::ExternalDependencyScope
            | K::CompleteExternalScope
            | K::ForbiddenDependency
            | K::SiblingIsolation => None,
            // S5: the receipt of `complete_requires` reads the scan roots (AD-380).
            K::CompleteRequires => Some(Reason::Unsupported(Unsupported::ScopeProof(
                archkeel_model::Part::ScanRoots,
            ))),
            other => Some(Reason::Unsupported(Unsupported::Rule(other))),
        };
        assert_eq!(reason, expected);
    }
}

#[test]
fn a_layout_root_that_only_a_planned_module_matches_gives_no_receipt() {
    // The planned module passes the subject check; no module of the reply lies below the root,
    // so the rule has no receipt (review of #1066, finding 4).
    let outcomes = crate::tests::run(
        |c| {
            set_component(c, "COMP-DATA", "planned", json!(["shop.later.thing"]));
            set_rule(c, "LAYOUT", "root", json!("shop.later"));
            set_rule(c, "LAYOUT", "allowed_children", json!([]));
        },
        unchanged,
    );
    let expected = Decision::unknown(Reason::NoSubjects);
    assert_eq!(decision(&outcomes, "LAYOUT"), Some(expected));
}

#[test]
fn a_pass_names_its_rule_and_its_model() {
    // Review of #1066, finding 6: a value can move, so the identity of a PASS is checked.
    let (Some(own), Some(first), Some(second)) =
        (contract(unchanged), reply(unchanged), reply(unchanged))
    else {
        return assert_eq!("the inputs load", "");
    };
    let (Ok(a), Ok(b)) = (
        Model::derive(&own, &first, shop_settings()),
        Model::derive(&own, &second, shop_settings()),
    ) else {
        return assert_eq!("the models derive", "");
    };
    let rule = &own.rules()[1];
    let pass = a.scope(|scope| scope.complete(rule).ok().map(|proof| scope.pass(proof)));
    let Some(pass) = pass else {
        return assert_eq!("the rule passes", "");
    };
    assert!(pass.passes(&a, "ASSIGNMENT"));
    assert!(!pass.passes(&b, "ASSIGNMENT"));
    assert!(!pass.passes(&a, "LAYOUT"));
    assert!(!Decision::fail().passes(&a, "ASSIGNMENT"));
    assert!(!pass.clone().passes(&b, "ASSIGNMENT"));
}
