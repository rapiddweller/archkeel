// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names of the scope proof (slice S4, AD-378): a cause that makes the scope of a run
//! incomplete, and a part of the proof that the core cannot read. `proof.rs` finds them; a
//! `Reason` carries them.

use std::collections::{BTreeMap, HashSet};
use std::fmt;

use archkeel_facts::vocab::RouteWithheld;

/// A cause that holds a rule or makes the scope of a run incomplete.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Cause {
    /// Gaps between two modules that the contract does not allow and that can change the rule
    /// (slice S7, AD-384): or, for the run, every such gap.
    PairGaps(Held),
    /// Gaps that the drop rule drops for the profile and that can change the rule (AD-418): or,
    /// for the run, that can change a rule of the contract.
    AllowedPairGaps(Held),
    /// Gaps that state their effect, and the effect meets what the rule reads (AD-564): or,
    /// for the run, every such gap.
    ScopedGaps(crate::gap_class::Scoped),
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
    /// The core cannot prove the dependency scope when the collector reports a coverage gap.
    DependencyScopeUnproven,
    /// A call that can create a class at run time leaves the placement of that class unproven
    /// (#1713): the site, as `path:line (callee)`.
    ClassSite(String),
}

/// The module pairs that hold a rule: the first ones as `a -> b`, the number of distinct pairs and
/// the number of gap records. A pair can have several gap records, so the two numbers can differ.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Held {
    shown: Vec<String>,
    distinct: usize,
    records: usize,
    pairs: Vec<(String, String)>,
    /// The origin of each record, when the rule states it (an interface rule); else empty.
    origins: Vec<PairOrigin>,
}

/// The largest number of gaps that a reason shows.
const HELD_SHOWN: usize = 5;
const HELD_KEPT: usize = 20;

impl Held {
    /// The gap records `(source, target)` that hold a rule, or `None` for no gap. A `Held` is a
    /// reason, not a proof: it can only make a rule UNKNOWN.
    pub fn of<'a>(gaps: impl Iterator<Item = (&'a str, &'a str)>) -> Option<Held> {
        Held::collect(gaps.map(|(source, target)| (source, target, None)))
    }

    /// The records of an interface rule, each with its origin.
    pub fn with_origins<'a>(
        gaps: impl Iterator<Item = (&'a str, &'a str, PairOrigin)>,
    ) -> Option<Held> {
        Held::collect(gaps.map(|(source, target, origin)| (source, target, Some(origin))))
    }

    fn collect<'a>(
        gaps: impl Iterator<Item = (&'a str, &'a str, Option<PairOrigin>)>,
    ) -> Option<Held> {
        let mut shown = Vec::new();
        let mut pairs = Vec::new();
        let mut origins = Vec::new();
        let mut seen: HashSet<(&str, &str)> = HashSet::new();
        let mut distinct = 0;
        let mut records = 0;
        for (source, target, origin) in gaps {
            pairs.push((source.to_owned(), target.to_owned()));
            origins.extend(origin);
            records += 1;
            if !seen.insert((source, target)) {
                continue;
            }
            distinct += 1;
            if shown.len() < HELD_SHOWN {
                shown.push(format!("{source} -> {target}"));
            }
        }
        (records > 0).then_some(Held {
            shown,
            distinct,
            records,
            pairs,
            origins,
        })
    }

    /// The origin of each record, in the order of `pairs`; empty when the rule states none.
    pub fn origins(&self) -> &[PairOrigin] {
        &self.origins
    }

    /// The number of distinct module pairs.
    pub fn count(&self) -> usize {
        self.distinct
    }

    /// Each gap record `(source, target)` that holds the rule (AD-484).
    pub fn pairs(&self) -> &[(String, String)] {
        &self.pairs
    }

    /// The pairs that the reason shows, as `a -> b`.
    pub fn shown(&self) -> &[String] {
        &self.shown
    }

    /// `{pairs} module pairs {what}: a -> b, ...`. When the pairs have more records, the text adds
    /// `from {records} gap records`. A cut list says `(showing N)` and ends with the number of the
    /// pairs that it leaves out.
    fn write(&self, formatter: &mut fmt::Formatter<'_>, what: &str) -> fmt::Result {
        let shown = self.shown.len();
        let hidden = self.distinct - shown;
        let unit = if self.distinct == 1 { "pair" } else { "pairs" };
        write!(formatter, "{} module {unit} {what}", self.distinct)?;
        if self.records != self.distinct {
            write!(formatter, " (from {} gap records)", self.records)?;
        }
        if hidden > 0 {
            write!(formatter, " (showing {shown})")?;
        }
        write!(formatter, ": {}", self.shown.join(", "))?;
        match hidden {
            0 => Ok(()),
            more => write!(formatter, " and {more} more pairs"),
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
            Cause::PairGaps(held) => {
                held.write(formatter, "with gaps that the contract does not allow")
            }
            Cause::AllowedPairGaps(held) => held.write(
                formatter,
                "with gaps that the contract allows and that can change the rule",
            ),
            Cause::ScopedGaps(scoped) => scoped.write(formatter, HELD_SHOWN),
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
            Cause::DependencyScopeUnproven => formatter
                .write_str("the core cannot prove the dependency scope with a coverage gap"),
            Cause::ClassSite(site) => write!(
                formatter,
                "symbol placement: a call can create a class at {site}"
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

#[cfg(test)]
#[path = "causes_tests.rs"]
mod tests;

/// A missing fact of the interface import verdict, not a lifecycle diagnosis.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum InterfaceGap {
    /// The binding of the import is not read.
    UnreadBinding,
    /// The route by which the target publishes the name is not proven.
    PublicationRoute,
    /// The published surface of the target is not read.
    PublicationSurface,
    /// The type that the interface publishes is not proven.
    TypePublication,
}

impl InterfaceGap {
    /// The word of the gap in the frame.
    pub fn word(self) -> &'static str {
        match self {
            Self::UnreadBinding => "unread_binding",
            Self::PublicationRoute => "publication_route",
            Self::PublicationSurface => "publication_surface",
            Self::TypePublication => "type_publication",
        }
    }

    /// The short form of the gap, as one import reads it.
    pub fn form(&self) -> &'static str {
        match self {
            Self::UnreadBinding => "unread import binding",
            Self::PublicationRoute => "unproven publication route",
            Self::PublicationSurface => "incomplete publication surface",
            Self::TypePublication => "unproven named type publication",
        }
    }
}

impl fmt::Display for InterfaceGap {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "interface_boundary: {}", self.form())
    }
}

/// One import that an `interface_boundary` rule could not decide, with the gap and the cause.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeldImport {
    /// The missing fact of the verdict.
    pub gap: InterfaceGap,
    /// The importing module.
    pub source: String,
    /// The module that the import names.
    pub target: String,
    /// The imported name.
    pub name: Option<String>,
    /// The cause that the collector states for the withheld route, and the module or hop it names.
    pub cause: Option<(RouteWithheld, Option<String>)>,
    /// The evidence ids of the import.
    pub evidence: Vec<String>,
}

impl HeldImport {
    /// The text of the import as one line of the hold.
    fn line(&self) -> String {
        let name = (self.name.as_ref())
            .map(|n| format!(":{n}"))
            .unwrap_or_default();
        let cause = match &self.cause {
            None => String::new(),
            Some((cause, at)) => {
                let at = (at.as_ref()).map(|at| format!(" {at}")).unwrap_or_default();
                format!(", {}{at}", cause.as_str())
            }
        };
        format!(
            "{} -> {}{name} ({}{cause})",
            self.source,
            self.target,
            self.gap.form()
        )
    }
}

/// The imports that an `interface_boundary` rule could not decide. The gap of the first one is the
/// stable key of the reason; the display lists the imports (#1963).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterfaceHold {
    gap: InterfaceGap,
    shown: Vec<HeldImport>,
    total: usize,
    classes: BTreeMap<(InterfaceGap, Option<RouteWithheld>), usize>,
}

impl InterfaceHold {
    /// A hold with no import: the gap holds the rule before any import is read.
    pub fn bare(gap: InterfaceGap) -> InterfaceHold {
        InterfaceHold {
            gap,
            shown: Vec::new(),
            total: 0,
            classes: BTreeMap::new(),
        }
    }

    /// The hold of the undecided imports, or `None` for no import.
    pub fn of(undecided: impl Iterator<Item = HeldImport>) -> Option<InterfaceHold> {
        let mut found: Option<InterfaceHold> = None;
        for held in undecided {
            let hold: &mut InterfaceHold =
                found.get_or_insert_with(|| InterfaceHold::bare(held.gap));
            hold.total += 1;
            let class = held.cause.as_ref().map(|(cause, _)| *cause);
            *hold.classes.entry((held.gap, class)).or_default() += 1;
            if Vec::len(&hold.shown) < HELD_KEPT {
                hold.shown.push(held);
            }
        }
        found
    }

    /// The gap of the first undecided import.
    pub fn gap(&self) -> InterfaceGap {
        self.gap
    }

    /// The number of undecided imports.
    pub fn total(&self) -> usize {
        self.total
    }

    /// The first undecided imports.
    pub fn imports(&self) -> &[HeldImport] {
        &self.shown
    }

    /// The count of undecided imports for each gap and class.
    pub fn classes(
        &self,
    ) -> impl Iterator<Item = (InterfaceGap, Option<RouteWithheld>, usize)> + '_ {
        self.classes
            .iter()
            .map(|((gap, class), count)| (*gap, *class, *count))
    }
}

impl fmt::Display for InterfaceHold {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.gap)?;
        if self.total == 0 {
            return Ok(());
        }
        let unit = if self.total == 1 { "import" } else { "imports" };
        write!(f, ": {} {unit}", self.total)?;
        let shown = Vec::len(&self.shown).min(HELD_SHOWN);
        if self.total > shown {
            write!(f, " (showing {shown})")?;
        }
        let lines: Vec<String> = self
            .shown
            .iter()
            .take(shown)
            .map(HeldImport::line)
            .collect();
        write!(f, ": {}", lines.join(", "))?;
        match self.total - shown {
            0 => Ok(()),
            more => write!(f, " and {more} more"),
        }
    }
}

/// Why a module pair holds an `interface_boundary` rule (#2086): the form of the gap or site.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum PairOrigin {
    /// A module of the pair is not a module of the reply.
    UnobservedModule,
    /// An unresolved internal dispatch: a method call whose callee the collector does not name.
    Dispatch,
    /// A gap that is no internal dispatch and not only about executing an impl.
    NotExecutionOnly,
    /// The gap is only about executing an impl, but a module of the pair has no single owner.
    UnownedEnd,
    /// A named import across components whose publication is not proven.
    NamedSite,
}

impl PairOrigin {
    /// The word of the origin in the frame.
    pub fn word(self) -> &'static str {
        match self {
            Self::UnobservedModule => "unobserved_module",
            Self::Dispatch => "dispatch",
            Self::NotExecutionOnly => "not_execution_only",
            Self::UnownedEnd => "unowned_end",
            Self::NamedSite => "named_site",
        }
    }
}
