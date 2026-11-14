// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The details of a matched symbol entity (AD-508): signature, visibility, modifiers,
//! annotation and initializer.
//!
//! Reference engine: `check/uml_compare.py` `_details`, `_signature` and `_syntax_details` at
//! release 4.0.1. A detail that the record does not state is UNKNOWN; a stated detail that
//! differs is FAIL. A modifier that the record does not state is UNKNOWN, never FAIL.

use archkeel_contract::{Entity, ParameterKind, Signature, VisibilityBasis, VisibilityKind};

use crate::symbols;
use crate::uml_facts::{Assessed, UmlDiff};

/// The assessments of the details that the target entity states.
pub(crate) fn details(wanted: &Entity, actual: &symbols::Entity) -> Vec<Assessed> {
    let fail = |cause: &'static str, fact: String| {
        Assessed::Fail(UmlDiff {
            subject: wanted.id().as_text().to_owned(),
            fact,
            cause,
            evidence: actual.evidence.clone(),
        })
    };
    let mut result = Vec::new();
    if let Some(expected) = wanted.signature() {
        result.push(match signature(expected, actual.signature.as_ref()) {
            Ok(true) => Assessed::Pass,
            Ok(false) => Assessed::Unknown("signature is not recorded".to_owned()),
            Err(cause) => fail(cause, actual.name.clone()),
        });
    }
    let declared = wanted.visibility();
    if *declared.kind() != VisibilityKind::Unknown {
        let recorded = &actual.visibility;
        let unknown =
            recorded.kind == VisibilityKind::Unknown || recorded.basis == VisibilityBasis::Unknown;
        let equal = *declared.kind() == recorded.kind
            && (matches!(
                declared.basis(),
                VisibilityBasis::Unknown | VisibilityBasis::Declared
            ) || *declared.basis() == recorded.basis)
            && declared
                .spelling()
                .as_ref()
                .is_none_or(|spelling| Some(spelling) == recorded.spelling.as_ref());
        result.push(if unknown {
            Assessed::Unknown("visibility is not recorded".to_owned())
        } else if equal {
            Assessed::Pass
        } else {
            fail("visibility or its basis differs", actual.name.clone())
        });
    }
    if !wanted.modifiers().is_empty() {
        let recorded = wanted
            .modifiers()
            .iter()
            .all(|modifier| actual.modifiers.contains(modifier));
        result.push(if recorded {
            Assessed::Pass
        } else {
            Assessed::Unknown("modifiers are not proven".to_owned())
        });
    }
    let syntax = [
        (
            "annotation",
            wanted.annotation(),
            actual.annotation.as_ref(),
        ),
        (
            "initializer",
            wanted.initializer(),
            actual.initializer.as_ref(),
        ),
    ];
    for (label, expected, recorded) in syntax {
        let Some(expected) = expected else {
            continue;
        };
        result.push(match recorded {
            None => Assessed::Unknown(format!("{label} is not recorded")),
            Some(recorded) if recorded == expected => Assessed::Pass,
            Some(recorded) => fail(
                if label == "annotation" {
                    "annotation differs"
                } else {
                    "initializer syntax differs"
                },
                format!("{} {label} {recorded}", actual.name),
            ),
        });
    }
    result
}

/// `_signature`: `Ok(true)` when it matches, `Ok(false)` when it is not decided, else the cause
/// of the difference.
fn signature(
    expected: &Signature,
    actual: Option<&symbols::Signature>,
) -> Result<bool, &'static str> {
    let Some(actual) = actual else {
        return Ok(false);
    };
    if expected.parameters().len() != actual.parameters.len() {
        return Err("parameter count differs");
    }
    let mut decided = true;
    for (wanted, found) in expected.parameters().iter().zip(&actual.parameters) {
        if *wanted.name() != found.name {
            return Err("parameter name or order differs");
        }
        if wanted.annotation().is_some() && *wanted.annotation() != found.annotation {
            return Err("parameter annotation differs");
        }
        if *wanted.kind() != ParameterKind::Unknown {
            if found.kind == ParameterKind::Unknown {
                decided = false;
            } else if *wanted.kind() != found.kind {
                return Err("parameter kind differs");
            }
        }
        if *wanted.default_known() {
            if !found.default_known {
                decided = false;
            } else if *wanted.default() != found.default {
                return Err("unevaluated parameter default differs");
            }
        }
    }
    if expected.returns().is_some() && *expected.returns() != actual.returns {
        return Err("return annotation differs");
    }
    Ok(decided)
}
