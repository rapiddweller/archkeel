// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why a part of a run has no result. The enums are closed and only grow at the end.

use std::fmt;

use archkeel_contract::RuleKind;

use crate::coverage::Incomplete;
use crate::section::{Porting, Section};

/// A part of the core that no slice has ported yet. It is a named answer, never an empty one.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unsupported {
    /// The scope proof that makes `ScopeComplete` (slice S4).
    ScopeProof,
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
}

/// An input of a run that the core needs.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Input {
    /// The bytes of the root contract.
    Contract,
    /// The validated collector reply.
    Reply,
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
}

impl fmt::Display for Unsupported {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Unsupported::ScopeProof => formatter.write_str("the scope proof: slice S4 ports it"),
            Unsupported::Section(section) => {
                let by = match section.porting() {
                    Porting::Slice(slice) => format!("slice {slice:?} ports it"),
                    Porting::Store => "the store writes it; the core does not yet".to_owned(),
                    Porting::RuleFamilies => "the slice of each rule family ports it".to_owned(),
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
            Reason::Incomplete(Incomplete::NoSourceFiles) => {
                formatter.write_str("incomplete scope: the collector selected no source file")
            }
            Reason::Incomplete(Incomplete::CoverageGaps(count)) => write!(
                formatter,
                "incomplete scope: the collector reports {count} coverage gaps"
            ),
            Reason::NoSubjects => formatter
                .write_str("the rule selects no module of the reply: no evaluator receipt exists"),
        }
    }
}
