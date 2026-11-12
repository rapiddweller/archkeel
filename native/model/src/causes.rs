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
    /// Gaps between two modules that the contract does not allow (their number).
    PairGaps(usize),
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
}

impl fmt::Display for Cause {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cause::PairGaps(count) => write!(
                formatter,
                "{count} gaps between two modules that the contract does not allow"
            ),
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
        }
    }
}
