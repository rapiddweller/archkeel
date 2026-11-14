// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names of the scope proof (slice S4, AD-378): a cause that makes the scope of a run
//! incomplete, and a part of the proof that the core cannot read. `proof.rs` finds them; a
//! `Reason` carries them.

use std::fmt;

/// A missing fact of the interface import verdict, not a lifecycle diagnosis.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InterfaceGap {
    UnreadBinding,
    PublicationRoute,
    PublicationSurface,
    TypePublication,
}

impl fmt::Display for InterfaceGap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::UnreadBinding => "interface_boundary: unread import binding",
            Self::PublicationRoute => "interface_boundary: unproven publication route",
            Self::PublicationSurface => "interface_boundary: incomplete publication surface",
            Self::TypePublication => "interface_boundary: unproven named type publication",
        })
    }
}

/// A cause that makes the scope of a run incomplete in the reference engine for every profile.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Cause {
    /// Gaps between two modules that the contract does not allow and that can change the rule
    /// (slice S7, AD-384): or, for the run, every such gap.
    PairGaps(Held),
    /// Gaps that the drop rule drops for the profile and that can change the rule (AD-418): or,
    /// for the run, that can change a rule of the contract.
    AllowedPairGaps(Held),
    /// The host could not read the head or the state of the work tree.
    WorkTree,
    /// The collector runtime does not satisfy its declared requirement.
    Runtime,
    /// The reply does not come from the bundled collector. The core verifies no pin of an
    /// external collector, so a pinned one is untrusted too (AD-344, AD-388).
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
    /// A component of an inside contract claims a package or a module outside its parent: the
    /// parent key of the mount (`inside_source_domain_incomplete`, AD-385).
    InsideSourceDomain(String),
    /// A component names a module outside the namespace of the settings: the reference engine
    /// refuses such a contract (AD-450).
    OutsideNamespace(String),
    /// A file without a module of its own whose path module and owner module have other
    /// components (AD-468): the path of the file.
    OwnedFileOwner(String),
}

/// The gaps that hold a rule: the first ones as `a -> b` and the number of all.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Held {
    shown: Vec<String>,
    count: usize,
    pairs: Vec<(String, String)>,
}

/// The largest number of gaps that a reason shows.
pub const HELD_SHOWN: usize = 5;

impl Held {
    /// The gaps `(source, target)` that hold a rule, or `None` for no gap. A `Held` is a reason,
    /// not a proof: it can only make a rule UNKNOWN.
    pub fn of<'a>(gaps: impl Iterator<Item = (&'a str, &'a str)>) -> Option<Held> {
        let mut shown = Vec::new();
        let mut pairs = Vec::new();
        let mut count = 0;
        for (source, target) in gaps {
            if shown.len() < HELD_SHOWN {
                shown.push(format!("{source} -> {target}"));
            }
            pairs.push((source.to_owned(), target.to_owned()));
            count += 1;
        }
        (count > 0).then_some(Held {
            shown,
            count,
            pairs,
        })
    }

    /// The number of gaps.
    pub fn count(&self) -> usize {
        self.count
    }

    /// Each gap `(source, target)` that holds the rule (AD-484).
    pub fn pairs(&self) -> &[(String, String)] {
        &self.pairs
    }

    /// The gaps that the reason shows, as `a -> b`.
    pub fn shown(&self) -> &[String] {
        &self.shown
    }

    /// `{count} {what}: a -> b, ...` and the number of the gaps that it does not show.
    fn write(&self, formatter: &mut fmt::Formatter<'_>, what: &str) -> fmt::Result {
        write!(
            formatter,
            "{} {what}: {}",
            self.count,
            self.shown.join(", ")
        )?;
        match self.count - self.shown.len() {
            0 => Ok(()),
            more => write!(formatter, " and {more} more"),
        }
    }
}

/// A part of the scope proof that the core cannot read. The rule is a named gap.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Part {
    /// A runtime requirement form or state that the core does not read.
    RuntimeRequirement,
    /// A limit of some profiles only: the subject that it names.
    ProfileLimit(String),
    /// A `forbidden_construct` rule that selects no module: a symbol can be its subject.
    ConstructSubjects(String),
    /// The rule is not a rule of the contract of this model.
    ForeignRule,
    /// The contract mounts inside contracts, and the model reads no mount (`Model::of`, AD-379).
    /// The reference engine reads the mounts for the root verdicts; `ModelTree::tree` reads them
    /// (AD-385).
    MountedTree,
    /// The receipt needs the scan roots of the configuration, and the request has none
    /// (`scope_receipts_complete`, `_cycle_scan_coverage`).
    ScanRoots,
    /// `complete_requires`: a coverage gap that the dependency scope proof of the host can
    /// accept (`ir/decisions.py` `_scoped_dependency_receipt`). Only a runtime that can carry the
    /// proof names it; for any other runtime the gap is a fact (AD-418).
    ScopedRequires,
    /// `layer_order`: the request carries no source of the contract with the parsed bytes.
    ContractSource,
    /// The receipt maps module files to directories by a rule of the profile that the core does
    /// not port (slice S7, AD-384).
    ScanLayout,
    /// `complete_requires`: the receipt scope of a rule of a kind that no slice decides
    /// (`scope_receipts_complete` reads the sources of selector rules).
    ReceiptSources,
    /// A `layer_order` rule of an inside contract: its row and receipt cite the file of the inside
    /// contract, which the core does not bind (AD-385).
    MountedLayerOrder,
    /// A mount whose parent the core does not find in the clipped contract of its owner: the
    /// parent key (AD-385). The assembly of the tree makes this case impossible today.
    MountParent(String),
}

impl fmt::Display for Cause {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cause::PairGaps(held) => held.write(
                formatter,
                "gaps between two modules that the contract does not allow",
            ),
            Cause::AllowedPairGaps(held) => held.write(
                formatter,
                "gaps between two modules that the contract allows and that can change the rule",
            ),
            Cause::WorkTree => formatter.write_str("the host could not read the work tree"),
            Cause::Runtime => {
                formatter.write_str("the collector runtime does not satisfy its requirement")
            }
            Cause::Producer => formatter.write_str(
                "the reply does not come from the bundled collector, and the collector pin \
                     is not verified by the core",
            ),
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
            Cause::InsideSourceDomain(parent) => write!(
                formatter,
                "a component inside {parent} claims a module outside its parent"
            ),
            Cause::OutsideNamespace(reference) => write!(
                formatter,
                "the contract names {reference}, which lies outside the namespace"
            ),
            Cause::OwnedFileOwner(path) => write!(
                formatter,
                "the file {path} belongs to a module of another component than its own path"
            ),
        }
    }
}

impl fmt::Display for Part {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
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
            Part::MountedTree => formatter
                .write_str("the contract mounts inside contracts; this model reads no mount"),
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
            Part::MountedLayerOrder => formatter.write_str(
                "a layer_order rule of an inside contract cites the inside contract file; the \
                 core does not bind it",
            ),
            Part::MountParent(parent) => write!(
                formatter,
                "the parent of the mount {parent} is not in the contract of its owner"
            ),
        }
    }
}
