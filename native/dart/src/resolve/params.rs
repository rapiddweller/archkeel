// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The formals of a constructor (AD-796; `resolve_parameters` of release 4.0.1): a field formal
//! takes the type of its field, a super formal the type of the formal of the superclass, and a
//! redirecting factory the formals of its target. A formal that the resolver cannot prove keeps
//! its written form, has no default and gets a problem, so its signature is not complete.

use std::collections::BTreeSet;

use super::formals::{field_annotation, matching, super_parameter, unknown, value};
use super::types::{key, names, substitute};
use super::{Decl, Resolver, Substitutions};
use crate::declarations::types::{Constructor, Problem, ProblemKind, ResolvedParameter};
use crate::syntax::{Definition, Member, MemberKind, Parameter};

/// The types that the resolver accepts without a binding (`_type_is_proven`).
const BUILTINS: [&str; 19] = [
    "String", "int", "double", "num", "bool", "Object", "dynamic", "void", "Never", "Null",
    "Function", "List", "Map", "Set", "Iterable", "Future", "FutureOr", "Stream", "Record",
];

/// One formal and its problem, if the resolver cannot prove it.
type Formal = (ResolvedParameter, Option<Problem>);

/// What a formal resolution reads besides the formal.
struct Reading<'s> {
    at: usize,
    substitutions: &'s Substitutions,
    seen: &'s BTreeSet<String>,
    known: &'s BTreeSet<String>,
}

impl Resolver<'_> {
    /// The resolution of the constructor `member` of `definition` in the file at `at`.
    pub(crate) fn constructor(
        &self,
        at: usize,
        definition: &Definition,
        member: &Member,
    ) -> Constructor {
        let start = member.span.start_byte;
        let Some(decl) = self.declaration(at, definition) else {
            return self.failure(
                at,
                start,
                &member.parameters,
                ProblemKind::SourceResolutionGap,
                "constructor owner is unresolved",
            );
        };
        if member.factory && member.redirect.is_some() {
            return self.redirected(at, &decl, member);
        }
        let none = Vec::new();
        let empty = BTreeSet::new();
        let reading = Reading {
            at,
            substitutions: &none,
            seen: &empty,
            known: &empty,
        };
        let (parameters, problems) = member
            .parameters
            .iter()
            .map(|parameter| self.formal(&reading, &decl, parameter))
            .unzip::<_, _, Vec<_>, Vec<_>>();
        Constructor {
            start,
            parameters,
            problems: problems.into_iter().flatten().collect(),
        }
    }

    fn formal(&self, reading: &Reading<'_>, decl: &Decl<'_>, parameter: &Parameter) -> Formal {
        if parameter.super_formal {
            return self.super_formal(reading, decl, parameter);
        }
        let mut annotation = substitute(parameter.annotation.as_deref(), reading.substitutions);
        if parameter.field_formal && annotation.is_none() {
            annotation = substitute(
                field_annotation(decl.definition, &parameter.name),
                reading.substitutions,
            );
            if annotation.is_none() {
                return self.unknown(
                    reading.at,
                    parameter,
                    None,
                    ProblemKind::UnsupportedParameter,
                    "field-formal parameter type is unavailable",
                );
            }
        }
        (
            value(
                parameter,
                annotation,
                parameter.default.clone(),
                parameter.default_known,
            ),
            None,
        )
    }

    fn super_formal(
        &self,
        reading: &Reading<'_>,
        decl: &Decl<'_>,
        parameter: &Parameter,
    ) -> Formal {
        let identity = self.identity(decl);
        if reading.seen.contains(&identity) {
            return self.unknown(
                reading.at,
                parameter,
                None,
                ProblemKind::UnsupportedParameter,
                "super-formal chain contains a cycle",
            );
        }
        let parent = decl
            .definition
            .extends
            .first()
            .and_then(|text| self.class_for_type(decl.module, text));
        let Some((parent, substitutions, _)) = parent else {
            return self.unknown(
                reading.at,
                parameter,
                None,
                ProblemKind::SourceResolutionGap,
                "superclass source is unresolved",
            );
        };
        let Some(source) = super_parameter(parent.definition, &parameter.name) else {
            return self.unknown(
                reading.at,
                parameter,
                None,
                ProblemKind::UnsupportedParameter,
                "superclass formal is not proven",
            );
        };
        let mut seen = reading.seen.clone();
        seen.insert(identity);
        let inner = Reading {
            at: parent.at,
            substitutions: &substitutions,
            seen: &seen,
            known: reading.known,
        };
        let (resolved, issue) = self.formal(&inner, &parent, source);
        if let Some(issue) = issue {
            return self.unknown(reading.at, parameter, None, issue.kind, &issue.message);
        }
        let annotation = substitute(resolved.annotation.as_deref(), &substitutions);
        let proven = annotation.as_deref().is_some_and(|text| {
            self.type_proven(text, parent.module, parent.definition, reading.known)
        });
        if !proven {
            return self.unknown(
                reading.at,
                parameter,
                None,
                ProblemKind::UnsupportedParameter,
                "inherited formal type is unresolved",
            );
        }
        (
            value(
                parameter,
                annotation,
                resolved.default,
                resolved.default_known,
            ),
            None,
        )
    }

    fn redirected(&self, at: usize, owner: &Decl<'_>, factory: &Member) -> Constructor {
        let start = factory.span.start_byte;
        let Some((target, member, substitutions)) = self.redirect_terminal(owner, factory) else {
            return self.failure(
                at,
                start,
                &factory.parameters,
                ProblemKind::UnsupportedParameter,
                "factory redirect is unproven",
            );
        };
        let known: BTreeSet<String> = owner.definition.type_parameters.iter().cloned().collect();
        let empty = BTreeSet::new();
        let mut parameters = Vec::new();
        let mut problems = Vec::new();
        for (position, parameter) in factory.parameters.iter().enumerate() {
            let Some(source) = matching(&member.parameters, parameter, position) else {
                let (resolved, problem) = self.unknown(
                    at,
                    parameter,
                    None,
                    ProblemKind::UnsupportedParameter,
                    "redirected formal does not match",
                );
                parameters.push(resolved);
                problems.extend(problem);
                continue;
            };
            let reading = Reading {
                at: target.at,
                substitutions: &substitutions,
                seen: &empty,
                known: &known,
            };
            let (resolved, issue) = self.formal(&reading, &target, source);
            let annotation = substitute(resolved.annotation.as_deref(), &substitutions);
            let declared = parameter.annotation.clone();
            let differs =
                matches!((&declared, &annotation), (Some(a), Some(b)) if key(a) != key(b));
            let message = issue
                .as_ref()
                .map_or("redirected formal type does not match", |issue| {
                    String::as_str(&issue.message)
                });
            if issue.is_some() || differs {
                let (resolved, problem) = self.unknown(
                    at,
                    parameter,
                    declared,
                    ProblemKind::UnsupportedParameter,
                    message,
                );
                parameters.push(resolved);
                problems.extend(problem);
                continue;
            }
            parameters.push(value(
                parameter,
                declared.or(annotation),
                resolved.default,
                resolved.default_known,
            ));
        }
        Constructor {
            start,
            parameters,
            problems,
        }
    }

    /// The generative constructor at the end of a chain of redirecting factories, or `None`
    /// when a step is not one proven constructor (`_redirect_terminal`).
    fn redirect_terminal<'m>(
        &'m self,
        owner: &Decl<'m>,
        factory: &Member,
    ) -> Option<(Decl<'m>, &'m Member, Substitutions)> {
        let mut owner = *owner;
        let mut visited = BTreeSet::from([format!(
            "{}:{}",
            self.identity(&owner),
            factory.span.start_byte
        )]);
        let mut target_type = factory.redirect.clone()?;
        loop {
            let (target, substitutions, requested) =
                self.class_for_type(owner.module, &target_type)?;
            let constructors = target
                .definition
                .members
                .iter()
                .filter(|item| item.kind == MemberKind::Constructor);
            let candidates: Vec<&Member> = match &requested {
                None => constructors
                    .filter(|item| {
                        item.name == target.definition.name || String::is_empty(&item.name)
                    })
                    .collect(),
                Some(name) => constructors
                    .filter(|item| {
                        item.name.contains('.') && item.name.rsplit('.').next() == Some(name)
                    })
                    .collect(),
            };
            let [next] = candidates.as_slice() else {
                return None;
            };
            if !visited.insert(format!(
                "{}:{}",
                self.identity(&target),
                next.span.start_byte
            )) {
                return None;
            }
            match (&next.redirect, next.factory) {
                (_, false) => return Some((target, next, substitutions)),
                (None, true) => {
                    let optional = next
                        .parameters
                        .iter()
                        .any(|item| item.optional || item.default.is_some());
                    return (!optional).then_some((target, next, substitutions));
                }
                (Some(redirect), true) => {
                    owner = target;
                    target_type.clone_from(redirect);
                }
            }
        }
    }

    /// True when each name of `annotation` is a builtin type, a type parameter or a name that
    /// the library scope binds (`_type_is_proven`).
    fn type_proven(
        &self,
        annotation: &str,
        module: &str,
        definition: &Definition,
        known: &BTreeSet<String>,
    ) -> bool {
        let found = names(annotation);
        !Vec::is_empty(&found)
            && found.iter().all(|name| {
                BUILTINS.contains(name)
                    || definition.type_parameters.iter().any(|item| item == name)
                    || known.contains(*name)
                    || !Vec::is_empty(&self.in_library(module, name))
            })
    }

    fn unknown(
        &self,
        at: usize,
        parameter: &Parameter,
        annotation: Option<String>,
        kind: ProblemKind,
        message: &str,
    ) -> Formal {
        let problem = Problem {
            path: self.rel(at).to_owned(),
            kind,
            message: message.to_owned(),
            span: Some(parameter.span.clone()),
        };
        (unknown(parameter, annotation), Some(problem))
    }

    fn failure(
        &self,
        at: usize,
        start: usize,
        parameters: &[Parameter],
        kind: ProblemKind,
        message: &str,
    ) -> Constructor {
        let (parameters, problems) = parameters
            .iter()
            .map(|parameter| self.unknown(at, parameter, None, kind, message))
            .unzip::<_, _, Vec<_>, Vec<_>>();
        Constructor {
            start,
            parameters,
            problems: problems.into_iter().flatten().collect(),
        }
    }
}
