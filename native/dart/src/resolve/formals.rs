// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The formal helpers of the resolver (AD-796): the formal that a super formal or a redirect
//! passes to, the type of a field, and the resolved form of a formal.

use crate::declarations::types::ResolvedParameter;
use crate::syntax::{Definition, MemberKind, Parameter, ParameterKind};

/// The one constructor formal of `definition` named `name` (`_super_parameter`).
pub(super) fn super_parameter<'d>(definition: &'d Definition, name: &str) -> Option<&'d Parameter> {
    let mut found = definition
        .members
        .iter()
        .filter(|member| member.kind == MemberKind::Constructor)
        .flat_map(|member| &member.parameters)
        .filter(|parameter| parameter.name == name);
    let first = found.next()?;
    found.next().is_none().then_some(first)
}

/// The formal of the target that a formal of the factory passes to (`_matching_parameter`).
pub(super) fn matching<'p>(
    values: &'p [Parameter],
    parameter: &Parameter,
    position: usize,
) -> Option<&'p Parameter> {
    if parameter.kind == ParameterKind::Named {
        let mut found = values
            .iter()
            .filter(|item| item.kind == ParameterKind::Named && item.name == parameter.name);
        let first = found.next()?;
        return found.next().is_none().then_some(first);
    }
    values
        .iter()
        .filter(|item| item.kind == ParameterKind::Positional)
        .nth(position)
}

/// The annotation of the one field named `name` (`_field_annotation`).
pub(super) fn field_annotation<'d>(definition: &'d Definition, name: &str) -> Option<&'d str> {
    let mut found = definition
        .members
        .iter()
        .filter(|member| member.kind == MemberKind::Field && member.name == name);
    let first = found.next()?;
    found
        .next()
        .is_none()
        .then_some(first.annotation.as_deref())
        .flatten()
}

pub(super) fn value(
    parameter: &Parameter,
    annotation: Option<String>,
    default: Option<String>,
    known: bool,
) -> ResolvedParameter {
    let default = match default {
        None if known && parameter.optional => Some("null".to_owned()),
        other => other,
    };
    ResolvedParameter {
        name: parameter.name.clone(),
        annotation,
        kind: parameter.kind,
        default,
        default_known: known,
        span: parameter.span.clone(),
        field_formal: parameter.field_formal,
    }
}

pub(super) fn unknown(parameter: &Parameter, annotation: Option<String>) -> ResolvedParameter {
    ResolvedParameter {
        name: parameter.name.clone(),
        annotation: annotation.or_else(|| parameter.annotation.clone()),
        kind: parameter.kind,
        default: None,
        default_known: false,
        span: parameter.span.clone(),
        field_formal: parameter.field_formal,
    }
}
