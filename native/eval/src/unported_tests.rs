// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A rule kind that no slice decides gives UNKNOWN by name, never PASS (#619, #880).
//!
//! The rules come from the contract of `F-architecture`, which holds a rule of each kind except
//! `complete_requires`. The kinds have no list to iterate (`RuleKind` is a closed enum), so the
//! only second list is the `match` of `ported`: a new kind does not compile until it is placed.

use archkeel_contract::{head_of, kind_of, Contract, ParsedContract, RuleKind as K};
use archkeel_model::{Decision, Model, Reason, Unsupported};
use serde_json::Value;

use crate::evaluate;
use crate::tests::{reply, shop_settings};

/// Whether a slice of the evaluator decides the kind (an arm of `outcome` in `lib.rs`).
fn ported(kind: K) -> bool {
    match kind {
        K::CompleteAssignment
        | K::RootLayout
        | K::InterfaceBoundary
        | K::ExternalDependencyScope
        | K::CompleteExternalScope
        | K::ForbiddenDependency
        | K::SiblingIsolation
        | K::CompleteRequires
        | K::LayerOrder
        | K::NoComponentCycles
        | K::ForbiddenConstruct
        | K::AllowedDependency => true,
        K::SymbolPlacement
        | K::SourceOwnership
        | K::BoundedNumericOperand
        | K::CallOwner
        | K::ForbiddenCallArgument
        | K::CatalogArgument
        | K::CatalogUse
        | K::ForbiddenEffectUnderCondition
        | K::ProtocolDeclarations
        | K::BoundaryTypes => false,
    }
}

fn contract_of_every_kind() -> Option<Contract> {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fixtures/F-architecture/architecture-contract.json"
    );
    let mut value: Value = serde_json::from_slice(&std::fs::read(path).ok()?).ok()?;
    // A mount needs its tree; the rules of the root contract are what this test reads.
    for component in value["components"].as_array_mut()? {
        component.as_object_mut()?.remove("inside");
    }
    match archkeel_contract::parse(value.to_string().as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        _ => None,
    }
}

#[test]
fn each_kind_that_no_slice_decides_is_unknown_by_name() {
    let (Some(contract), Some(reply)) = (contract_of_every_kind(), reply(|_| {})) else {
        return assert_eq!("the inputs load", "");
    };
    let Ok(model) = Model::derive(&contract, &reply, shop_settings()) else {
        return assert_eq!("the model derives", "");
    };
    let outcomes = evaluate(&model);
    assert_eq!(outcomes.len(), contract.rules().len());
    let mut seen = 0;
    for (rule, outcome) in contract.rules().iter().zip(&outcomes) {
        let kind = kind_of(rule);
        assert_eq!(outcome.rule(), head_of(rule).id().as_text());
        if ported(kind) {
            continue;
        }
        seen += 1;
        let expected = Decision::unknown(Reason::Unsupported(Unsupported::Rule(kind)));
        assert_eq!(outcome.decision(), Some(&expected), "{kind:?}");
        assert!(outcome.violations().is_empty(), "{kind:?}");
    }
    // The contract holds the 10 kinds, so a kind that moves to `ported` or leaves it shows here.
    assert_eq!(seen, 10);
}
