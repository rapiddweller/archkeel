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
    assert!(matches!(
        decision(&outcomes, "LAYOUT").map(|d| d.verdict()),
        Some(Verdict::Pass(_))
    ));
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
        let decided = matches!(
            kind,
            archkeel_contract::RuleKind::CompleteAssignment
                | archkeel_contract::RuleKind::RootLayout
                | archkeel_contract::RuleKind::ExternalDependencyScope
                | archkeel_contract::RuleKind::CompleteExternalScope
        );
        let expected = (!decided).then_some(Reason::Unsupported(Unsupported::Rule(kind)));
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
