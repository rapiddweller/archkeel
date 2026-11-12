// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names of the scope proof (slice S4, AD-378): a cause that makes the scope of a run
//! incomplete, and a part of the proof that the core cannot read. `proof.rs` finds them; a
//! `Reason` carries them.

use std::fmt;

/// A cause that makes the scope of a run incomplete in the reference engine for every profile.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Cause {
    /// Gaps between two modules that the contract does not allow and that can change the rule
    /// (slice S7, AD-384): or, for the run, every such gap.
    PairGaps(Held),
    /// The host could not read the head or the state of the work tree.
    WorkTree,
    /// The collector runtime does not satisfy its declared requirement.
    Runtime,
    /// The reply comes from an external collector without a pinned digest (AD-344).
    Producer,
    /// A profile limit of the contract: the subject that it names.
    ProfileLimit(String),
    /// A `layer_order` rule whose components have no layer of its order: the rule id.
    LayerMetadata(String),
    /// A rule side that matches no module: the rule id.
    NoRuleSubjects(String),
    /// A dynamic import that the collector could not resolve reaches the rule.
    DynamicImport,
    /// Imports that the rule names whose used names the reply does not prove (their number).
    Undecided(usize),
    /// The receipt of the rule is not complete: why (slice S7, AD-384).
    Receipt(&'static str),
}

/// The gaps that hold a rule: the first ones as `a -> b` and the number of all.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Held {
    shown: Vec<String>,
    count: usize,
}

/// The largest number of gaps that a reason shows.
pub const HELD_SHOWN: usize = 5;

impl Held {
    /// The gaps `(source, target)` that hold a rule.
    pub(crate) fn of<'a>(gaps: impl Iterator<Item = (&'a str, &'a str)>) -> Option<Held> {
        let mut shown = Vec::new();
        let mut count = 0;
        for (source, target) in gaps {
            if shown.len() < HELD_SHOWN {
                shown.push(format!("{source} -> {target}"));
            }
            count += 1;
        }
        (count > 0).then_some(Held { shown, count })
    }

    /// The number of gaps.
    pub fn count(&self) -> usize {
        self.count
    }

    /// The gaps that the reason shows, as `a -> b`.
    pub fn shown(&self) -> &[String] {
        &self.shown
    }
}

/// A part of the scope proof that the core cannot read. The rule is a named gap.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Part {
    /// A gap between two modules that the contract allows: the host drops it for one profile.
    AllowedPairGap,
    /// A runtime requirement form or state that the core does not read.
    RuntimeRequirement,
    /// A limit of some profiles only: the subject that it names.
    ProfileLimit(String),
    /// A `forbidden_construct` rule that selects no module: a symbol can be its subject.
    ConstructSubjects(String),
    /// The rule is not a rule of the contract of this model.
    ForeignRule,
    /// The contract mounts inside contracts. The reference engine reads the mounts for the root
    /// verdicts (a mount failure makes a root rule UNKNOWN); the core does not (AD-379).
    MountedTree,
    /// The receipt needs the scan roots of the configuration, and the request has none
    /// (`scope_receipts_complete`, `_cycle_scan_coverage`).
    ScanRoots,
    /// `complete_requires`: a coverage gap that the dependency scope proof of the host can
    /// accept (`ir/decisions.py` `_scoped_dependency_receipt`).
    ScopedRequires,
    /// `layer_order`: the request carries no source of the contract with the parsed bytes.
    ContractSource,
    /// The receipt maps module files to directories by a rule of the profile that the core does
    /// not port (slice S7, AD-384).
    ScanLayout,
    /// `complete_requires`: the receipt scope of a rule of a kind that no slice decides
    /// (`scope_receipts_complete` reads the sources of selector rules).
    ReceiptSources,
}

impl fmt::Display for Cause {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cause::PairGaps(held) => {
                write!(
                    formatter,
                    "{} gaps between two modules that the contract does not allow: {}",
                    held.count,
                    held.shown.join(", ")
                )?;
                match held.count - held.shown.len() {
                    0 => Ok(()),
                    more => write!(formatter, " and {more} more"),
                }
            }
            Cause::WorkTree => formatter.write_str("the host could not read the work tree"),
            Cause::Runtime => {
                formatter.write_str("the collector runtime does not satisfy its requirement")
            }
            Cause::Producer => {
                formatter.write_str("the reply comes from an external collector without a pin")
            }
            Cause::ProfileLimit(subject) => {
                write!(formatter, "the profile cannot decide {subject}")
            }
            Cause::LayerMetadata(rule) => {
                write!(formatter, "a component of {rule} has no layer of its order")
            }
            Cause::NoRuleSubjects(rule) => write!(formatter, "the rule {rule} selects no module"),
            Cause::DynamicImport => {
                formatter.write_str("an unresolved dynamic import reaches the rule")
            }
            Cause::Undecided(count) => {
                write!(formatter, "the rule left {count} imports undecided")
            }
            Cause::Receipt(why) => {
                write!(formatter, "the receipt of the rule is not complete: {why}")
            }
        }
    }
}

impl fmt::Display for Part {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Part::AllowedPairGap => formatter.write_str(
                "a gap between two modules that the contract allows; the host drops it for one \
                 profile, the core does not know the profile",
            ),
            Part::RuntimeRequirement => {
                formatter.write_str("a runtime requirement that the core does not read")
            }
            Part::ProfileLimit(subject) => write!(
                formatter,
                "{subject} is a limit of some profiles; the core does not know the profile"
            ),
            Part::ConstructSubjects(rule) => write!(
                formatter,
                "{rule} selects no module; the core does not read the symbols of its source"
            ),
            Part::ForeignRule => formatter.write_str("the rule is not a rule of this model"),
            Part::MountedTree => formatter.write_str(
                "the contract mounts inside contracts; the core does not read their coverage",
            ),
            Part::ScanRoots => {
                formatter.write_str("the receipt needs the scan roots; the request has none")
            }
            Part::ScopedRequires => formatter.write_str(
                "a coverage gap that the dependency scope proof of complete_requires can accept",
            ),
            Part::ContractSource => {
                formatter.write_str("the request has no source of the contract bytes")
            }
            Part::ScanLayout => formatter.write_str(
                "the receipt maps the files of this profile by a rule that the core does not port",
            ),
            Part::ReceiptSources => formatter.write_str(
                "the receipt reads the source of a rule of a kind that the core does not decide",
            ),
        }
    }
}
