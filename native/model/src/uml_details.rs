// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The details of a matched symbol entity (AD-512): signature, visibility, modifiers,
//! annotation and initializer.
//!
//! Reference engine: `check/uml_compare.py` `_details`, `_signature` and `_syntax_details` at
//! release 4.0.1. A detail that the record does not state is UNKNOWN; a stated detail that
//! differs is FAIL. A modifier that the record does not state is UNKNOWN, never FAIL.

use archkeel_contract::{
    Entity, EntityKind, ModifierKind, ParameterKind, Signature, VisibilityBasis, VisibilityKind,
};

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
    // A drawn operation with no modifier is read as a plain one: a static or class method of the
    // code is not that, so the row stays undecided (AD-518).
    let operation = matches!(wanted.kind(), EntityKind::Method | EntityKind::Function);
    let marked = [ModifierKind::Static, ModifierKind::Class];
    if operation
        && wanted.modifiers().is_empty()
        && marked
            .iter()
            .any(|modifier| actual.modifiers.contains(modifier))
    {
        result.push(Assessed::Unknown(
            "a static or class method is drawn without a modifier".to_owned(),
        ));
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
    if let Some(expected) = wanted.annotation() {
        result.push(annotation(expected, actual, fail));
    }
    if let Some(expected) = wanted.initializer() {
        result.push(match actual.initializer.as_ref() {
            None => Assessed::Unknown("initializer is not recorded".to_owned()),
            Some(recorded) if recorded == expected => Assessed::Pass,
            Some(recorded) => fail(
                "initializer syntax differs",
                format!("{} initializer {recorded}", actual.name),
            ),
        });
    }
    result
}

/// Compare the written annotation first. Without one, require both builtin identities.
fn annotation(
    expected: &str,
    actual: &symbols::Entity,
    fail: impl Fn(&'static str, String) -> Assessed,
) -> Assessed {
    if let Some(recorded) = actual.annotation.as_ref() {
        return if recorded == expected {
            Assessed::Pass
        } else {
            fail(
                "annotation differs",
                format!("{} annotation {recorded}", actual.name),
            )
        };
    }
    match actual
        .inferred_builtin_type
        .as_ref()
        .and_then(|(inferred, names)| names.get(expected).map(|target| (inferred, target)))
    {
        Some((inferred, target)) if inferred == target => Assessed::Pass,
        Some((inferred, _)) => fail(
            "inferred type differs",
            format!("{} inferred type {inferred}", actual.name),
        ),
        None => Assessed::Unknown("annotation is not recorded".to_owned()),
    }
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
