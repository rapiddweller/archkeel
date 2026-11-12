// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why a part of a run has no result. The enums are closed and only grow at the end.

use std::fmt;

use archkeel_contract::RuleKind;

use crate::causes::{Cause, Part};
use crate::coverage::Incomplete;
use crate::section::{Porting, Section};

/// A part of the core that no slice has ported yet. It is a named answer, never an empty one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Unsupported {
    /// A part of the scope proof that the core cannot read (slice S4, AD-378).
    ScopeProof(Part),
    /// The rows of one section.
    Section(Section),
    /// The rules of one kind (the slice of its family).
    Rule(RuleKind),
    /// The report v2 payload (slice 0d).
    Report,
    /// A contract that mounts inside contracts: the core does not assemble the tree yet.
    InsideTree,
    /// The UML target row of a contract with `declarations.uml`.
    UmlTarget,
    /// The baseline of a request: no slice reads it yet.
    Baseline,
}

/// An input of a run that the core needs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Input {
    /// The bytes of the root contract.
    Contract,
    /// The validated collector reply.
    Reply,
    /// The settings of the shell: the namespace and the standard library (AD-372).
    Settings,
}

/// Why a part has no result.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reason {
    /// The part is not ported to the core yet.
    Unsupported(Unsupported),
    /// A table has more rows than its id can count.
    TooManyRows(&'static str),
    /// The run has no valid input of this kind.
    MissingInput(Input),
    /// The reply proves that the scope of the run is not complete.
    Incomplete(Incomplete),
    /// The rule selects no module of the reply, so no evaluator receipt exists for it.
    NoSubjects,
    /// A child of a layout root has no module record to cite (the reference engine stops).
    UncitedChild(String),
    /// The settings of the shell do not hold for the reply (AD-372).
    Refused(Refusal),
    /// A cause that makes the scope incomplete in the reference engine (slice S4, AD-378).
    NotComplete(Cause),
}

/// Why the core refuses the settings that the shell sends with a reply (AD-372).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Refusal {
    /// The profile of the settings is not the profile of the reply.
    ProfileMismatch,
    /// A module of the reply, or its package, lies outside the namespace.
    OutsideNamespace(String),
    /// The standard library list breaks a rule: its limit, a name, or a duplicate.
    StandardLibrary(&'static str),
}

impl fmt::Display for Refusal {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Refusal::ProfileMismatch => {
                formatter.write_str("the profile of the settings is not the profile of the reply")
            }
            Refusal::OutsideNamespace(module) => {
                write!(formatter, "the module {module} lies outside the namespace")
            }
            Refusal::StandardLibrary(rule) => {
                write!(formatter, "the standard library of the settings has {rule}")
            }
        }
    }
}

impl fmt::Display for Unsupported {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Unsupported::ScopeProof(part) => write!(formatter, "the scope proof: {part}"),
            Unsupported::Section(section) => {
                let by = match section.porting() {
                    Porting::Slice(slice) => format!("slice {slice:?} ports it"),
                    Porting::Store => "the store writes it; the core does not yet".to_owned(),
                    Porting::RuleFamilies => "the slice of each rule family ports it".to_owned(),
                    Porting::Unowned(needs) => format!("no slice owns it yet; {needs}"),
                };
                write!(formatter, "section {}: {by}", section.name())
            }
            Unsupported::Rule(kind) => {
                write!(
                    formatter,
                    "rule kind {kind:?}: the slice of its family ports it"
                )
            }
            Unsupported::Report => formatter.write_str("the report payload: slice 0d ports it"),
            Unsupported::InsideTree => formatter.write_str(
                "the contract mounts inside contracts; the tree assembly is not in the core yet",
            ),
            Unsupported::UmlTarget => {
                formatter.write_str("the UML target of the contract: no slice ports it yet")
            }
            Unsupported::Baseline => {
                formatter.write_str("the baseline of the request: no slice reads it yet")
            }
        }
    }
}

impl fmt::Display for Reason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Reason::Unsupported(part) => write!(formatter, "unsupported: {part}"),
            Reason::TooManyRows(table) => write!(formatter, "the {table} table is too large"),
            Reason::MissingInput(Input::Contract) => {
                formatter.write_str("missing input: no valid contract")
            }
            Reason::MissingInput(Input::Reply) => {
                formatter.write_str("missing input: no valid collector reply")
            }
            Reason::MissingInput(Input::Settings) => {
                formatter.write_str("missing input: no settings from the shell")
            }
            Reason::Incomplete(Incomplete::NoSourceFiles) => {
                formatter.write_str("incomplete scope: the collector selected no source file")
            }
            Reason::Incomplete(Incomplete::CoverageGaps(count)) => write!(
                formatter,
                "incomplete scope: the collector reports {count} coverage gaps"
            ),
            Reason::Incomplete(Incomplete::UnknownImports(count)) => write!(
                formatter,
                "incomplete scope: {count} imports are not resolved and no gap names them"
            ),
            Reason::NoSubjects => formatter
                .write_str("the rule selects no module of the reply: no evaluator receipt exists"),
            Reason::Refused(refusal) => write!(formatter, "refused settings: {refusal}"),
            Reason::NotComplete(cause) => write!(formatter, "incomplete scope: {cause}"),
            Reason::UncitedChild(child) => write!(
                formatter,
                "the layout child {child} has no module record to cite"
            ),
        }
    }
}

impl From<Part> for Reason {
    fn from(part: Part) -> Reason {
        Reason::Unsupported(Unsupported::ScopeProof(part))
    }
}
