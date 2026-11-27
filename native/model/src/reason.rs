// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why a part of a run has no result. The enums are closed and only grow at the end.

use std::fmt;

use archkeel_contract::RuleKind;

use crate::causes::InterfaceHold;
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
    /// A contract that mounts inside contracts that the shell has not sent yet (AD-379).
    InsideTree,
    /// The baseline of a request: no slice reads it yet.
    Baseline,
    /// A rule of an inside contract without the domain of its mount: `Model::of` refuses an
    /// inside contract, and only `ModelTree::tree` makes its model (AD-385).
    InsideRule,
    /// A PASS of a rule of a tree whose models do not hold every mount: the second line of the
    /// core after the scope proof (AD-385).
    TreeScope,
    /// No outcome of the contract tree has a decision; declarations do not decide (AD-416).
    NoRules,
    /// A contract hygiene check that applies to the contract and that the core does not port
    /// yet: the codes of the reference engine that it names (AD-466).
    Hygiene(&'static str),
    /// The contract hygiene of a request that carries no provenance documents: only the scan
    /// request reads the repository (AD-466).
    HygieneInput,
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
    /// A cause that holds the rule or makes the scope incomplete (AD-378, AD-418).
    NotComplete(Cause),
    /// A fact needed to decide an interface crossing is absent.
    Interface(InterfaceHold),
    /// A contract hygiene check of the core found a defect (AD-466).
    Hygiene(Hygiene),
    /// The UML target row of a contract tree is UNKNOWN for this cause (AD-470).
    Uml(UmlGap),
}

/// One contract hygiene defect: the code of the reference engine (`graph.drift`, ...) and the
/// text that names the subject and the defect.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Hygiene {
    code: &'static str,
    detail: String,
    /// The contract file and the stable parts of the subject (AD-546). The display detail can
    /// hold a pointer or a count, so the key reads these.
    place: String,
    parts: Vec<String>,
    /// What the user can do about the defect, when the code has more than one answer (#1963).
    action: Option<&'static str>,
}

impl Hygiene {
    /// The defect `code` with its `detail`. It has no stable key of its own.
    pub fn new(code: &'static str, detail: String) -> Hygiene {
        Hygiene {
            code,
            detail,
            place: String::new(),
            parts: Vec::new(),
            action: None,
        }
    }

    /// The defect `code` in the contract file `place`, with one stable `part` for each thing that
    /// it names.
    pub fn keyed(code: &'static str, detail: String, place: &str, parts: Vec<String>) -> Hygiene {
        Hygiene {
            code,
            detail,
            place: place.to_owned(),
            parts,
            action: None,
        }
    }

    /// The defect with the word of the action that it asks for.
    pub fn acting(mut self, action: &'static str) -> Hygiene {
        self.action = Some(action);
        self
    }

    /// The word of the action that the defect asks for, if its code has more than one.
    pub fn action(&self) -> Option<&'static str> {
        self.action
    }

    /// The code of the reference engine, such as `graph.drift`.
    pub fn code(&self) -> &'static str {
        self.code
    }

    /// The entries of the stable key: one for each part, in the contract file of the defect.
    pub(crate) fn parts(&self) -> (&str, &[String]) {
        (&self.place, &self.parts)
    }
}

/// The largest number of absent symbols that the reason of a UML target names.
const UML_ABSENT_SHOWN: usize = 5;

/// Why the UML target row of a contract tree is UNKNOWN (AD-470, AD-494).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum UmlGap {
    /// The target declares no entity, relationship or scope (the reference `UML-EMPTY` row).
    Empty,
    /// The declared intent that the core does not compare: no model decides the run.
    NotCompared {
        /// How many entities the target declares.
        entities: usize,
        /// How many relationships the target declares.
        relationships: usize,
        /// How many scopes the target declares.
        scopes: usize,
    },
    /// The targets of the tree contradict each other or leave a mount (AD-526): the reason.
    Nested(String),
    /// The target gives no assessment that the core can make.
    NothingCompared,
    /// Assessments that the core cannot decide from module and import facts: their number and
    /// the element kinds that need other facts.
    Undecided {
        /// How many assessments the core cannot decide.
        count: usize,
        /// The element kinds that need other facts.
        kinds: Vec<String>,
        /// The symbols of the target that the symbol inventory does not hold, sorted (#2089).
        absent: Vec<String>,
    },
    /// Each assessment passes, but the scope of the run is not complete: its reason.
    Incomplete(String),
}

impl fmt::Display for UmlGap {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            UmlGap::Empty => formatter.write_str("it declares no entity, relationship or scope"),
            UmlGap::NotCompared {
                entities,
                relationships,
                scopes,
            } => write!(
                formatter,
                "the core does not compare {entities} entities, {relationships} relationships \
                 and {scopes} scopes with the source facts"
            ),
            UmlGap::Nested(reason) => formatter.write_str(reason),
            UmlGap::NothingCompared => {
                formatter.write_str("the target gives no assessment that the core can make")
            }
            UmlGap::Undecided {
                count,
                kinds,
                absent,
            } => {
                write!(
                    formatter,
                    "{count} assessments cannot be decided: {}",
                    kinds.join(", ")
                )?;
                if absent.is_empty() {
                    return Ok(());
                }
                let shown: Vec<&str> = absent
                    .iter()
                    .take(UML_ABSENT_SHOWN)
                    .map(String::as_str)
                    .collect();
                write!(
                    formatter,
                    "; not in the symbol inventory: {}",
                    shown.join(", ")
                )?;
                match absent.len() - shown.len() {
                    0 => Ok(()),
                    more => write!(formatter, " and {more} more"),
                }
            }
            UmlGap::Incomplete(reason) => {
                write!(formatter, "the scope of the run is not complete: {reason}")
            }
        }
    }
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
    /// The scan roots are not the scope labels that the collector wrote (AD-384).
    ScanRoots,
    /// The provenance of the compiler type-reach facts does not hold (AD-1116).
    TypeReach(&'static str),
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
            Refusal::ScanRoots => {
                formatter.write_str("the scan roots of the settings are not the scope of the reply")
            }
            Refusal::TypeReach(rule) => {
                formatter.write_str(&["the type-reach facts of the reply have ", rule].concat())
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
            Unsupported::InsideTree => formatter
                .write_str("the contract mounts inside contracts that the shell has not sent"),
            Unsupported::Baseline => {
                formatter.write_str("the baseline of the request: no slice reads it yet")
            }
            Unsupported::InsideRule => {
                formatter.write_str("a rule of an inside contract without the domain of its mount")
            }
            Unsupported::TreeScope => formatter.write_str(
                "the scope proof of a contract tree: the models do not hold every mount",
            ),
            Unsupported::NoRules => formatter.write_str("contract has no decided rule"),
            Unsupported::HygieneInput => formatter.write_str(
                "the contract hygiene of the request: it carries no provenance documents",
            ),
            Unsupported::Hygiene(codes) => {
                write!(
                    formatter,
                    "the contract hygiene checks {codes}: no slice ports them yet"
                )
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
            Reason::Incomplete(Incomplete::CoverageGaps { whole, reported }) => {
                let gaps = if *reported == 1 { "gap" } else { "gaps" };
                write!(
                    formatter,
                    "incomplete scope: the collector reports {reported} coverage {gaps}"
                )?;
                // The other gaps state their effect or lie between two modules (AD-564).
                match (whole == reported, *whole == 1) {
                    (true, _) => Ok(()),
                    (false, true) => {
                        formatter.write_str("; 1 of them leaves the whole scope unknown")
                    }
                    (false, false) => {
                        write!(formatter, "; {whole} of them leave the whole scope unknown")
                    }
                }
            }
            Reason::Incomplete(Incomplete::UnknownImports(count)) => write!(
                formatter,
                "incomplete scope: {count} {} not resolved and no gap names {}",
                if *count == 1 {
                    "import is"
                } else {
                    "imports are"
                },
                if *count == 1 { "it" } else { "them" }
            ),
            Reason::NoSubjects => formatter
                .write_str("the rule selects no module of the reply: no evaluator receipt exists"),
            Reason::Refused(refusal) => write!(formatter, "refused settings: {refusal}"),
            Reason::NotComplete(cause) => write!(formatter, "incomplete scope: {cause}"),
            Reason::Interface(hold) => write!(formatter, "incomplete scope: {hold}"),
            Reason::Hygiene(found) => {
                write!(
                    formatter,
                    "contract hygiene {}: {}",
                    found.code, found.detail
                )
            }
            Reason::Uml(gap) => write!(formatter, "the UML target: {gap}"),
            Reason::UncitedChild(child) => write!(
                formatter,
                "the layout child {child} has no module record to cite"
            ),
        }
    }
}

impl From<Cause> for Reason {
    fn from(cause: Cause) -> Reason {
        Reason::NotComplete(cause)
    }
}

impl From<Part> for Reason {
    fn from(part: Part) -> Reason {
        Reason::Unsupported(Unsupported::ScopeProof(part))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_count_of_one_has_the_singular_form() {
        let text = |reason: Reason| reason.to_string();
        let gaps =
            |whole, reported| Reason::Incomplete(Incomplete::CoverageGaps { whole, reported });
        assert_eq!(
            text(gaps(1, 1)),
            "incomplete scope: the collector reports 1 coverage gap"
        );
        assert_eq!(
            text(gaps(2, 2)),
            "incomplete scope: the collector reports 2 coverage gaps"
        );
        // The line counts each gap that the report lists, and names the gaps of the whole scope.
        assert_eq!(
            text(gaps(3, 4)),
            "incomplete scope: the collector reports 4 coverage gaps; 3 of them leave the whole \
             scope unknown"
        );
        assert_eq!(
            text(gaps(1, 2)),
            "incomplete scope: the collector reports 2 coverage gaps; 1 of them leaves the whole \
             scope unknown"
        );
        assert_eq!(
            text(Reason::Incomplete(Incomplete::UnknownImports(1))),
            "incomplete scope: 1 import is not resolved and no gap names it"
        );
        assert_eq!(
            text(Reason::Incomplete(Incomplete::UnknownImports(3))),
            "incomplete scope: 3 imports are not resolved and no gap names them"
        );
    }
}
