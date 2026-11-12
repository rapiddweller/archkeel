// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compared sections of `architecture.json` (`tools/dual_run_schema.json`) and the slice of
//! WP6 that ports each one (design WP6-0, section C).

/// A WP6 slice that ports a derived section.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Slice {
    /// Import projection and dependency edges.
    S2,
    /// Cycles.
    S3,
    /// Metrics.
    S10,
    /// Guarded effects with state replay.
    S15,
}

/// Who ports a section to the core.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Porting {
    /// A slice of the model.
    Slice(Slice),
    /// The rows of the collector that the store holds and writes.
    Store,
    /// The rule families: each family slice brings the rows of its rules.
    RuleFamilies,
    /// No slice owns the section yet: what its rows need (AD-378).
    Unowned(&'static str),
}

/// One compared section of `architecture.json`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Section {
    /// `metrics`
    Metrics,
    /// `declarations`
    Declarations,
    /// `scope_observations`
    ScopeObservations,
    /// `packages`
    Packages,
    /// `modules`
    Modules,
    /// `symbols`
    Symbols,
    /// `imports`
    Imports,
    /// `dependency_edges`
    DependencyEdges,
    /// `path_observations`
    PathObservations,
    /// `cycles`
    Cycles,
    /// `calls`
    Calls,
    /// `references`
    References,
    /// `bindings`
    Bindings,
    /// `typing_signals`
    TypingSignals,
    /// `constructs`
    Constructs,
    /// `contexts`
    Contexts,
    /// `context_evidence`
    ContextEvidence,
    /// `violations`
    Violations,
    /// `unknowns`
    Unknowns,
    /// `evidence`
    Evidence,
}

impl Section {
    /// Every section, in the order of the schema.
    pub const ALL: &'static [Section] = &[
        Section::Metrics,
        Section::Declarations,
        Section::ScopeObservations,
        Section::Packages,
        Section::Modules,
        Section::Symbols,
        Section::Imports,
        Section::DependencyEdges,
        Section::PathObservations,
        Section::Cycles,
        Section::Calls,
        Section::References,
        Section::Bindings,
        Section::TypingSignals,
        Section::Constructs,
        Section::Contexts,
        Section::ContextEvidence,
        Section::Violations,
        Section::Unknowns,
        Section::Evidence,
    ];

    /// The name of the section in `architecture.json`.
    pub fn name(self) -> &'static str {
        match self {
            Section::Metrics => "metrics",
            Section::Declarations => "declarations",
            Section::ScopeObservations => "scope_observations",
            Section::Packages => "packages",
            Section::Modules => "modules",
            Section::Symbols => "symbols",
            Section::Imports => "imports",
            Section::DependencyEdges => "dependency_edges",
            Section::PathObservations => "path_observations",
            Section::Cycles => "cycles",
            Section::Calls => "calls",
            Section::References => "references",
            Section::Bindings => "bindings",
            Section::TypingSignals => "typing_signals",
            Section::Constructs => "constructs",
            Section::Contexts => "contexts",
            Section::ContextEvidence => "context_evidence",
            Section::Violations => "violations",
            Section::Unknowns => "unknowns",
            Section::Evidence => "evidence",
        }
    }

    /// Who ports the section.
    pub fn porting(self) -> Porting {
        match self {
            Section::Metrics => Porting::Slice(Slice::S10),
            // Slice S4 makes the scope proof but none of these rows (AD-378).
            Section::Declarations => Porting::Unowned(
                "its module targets need the language of the shell and its public API types the \
                 symbols",
            ),
            Section::ScopeObservations => Porting::Unowned(
                "it holds the component scopes and the receipt of each rule of every family",
            ),
            Section::PathObservations => Porting::Unowned(
                "it holds the declared paths of the contract over the package edges",
            ),
            // The rows hold fan-in, fan-out (S2) and the condensation rank (S3); the modules,
            // packages and owners of slice S1 are in the model.
            Section::Packages | Section::Modules => Porting::Slice(Slice::S3),
            Section::Symbols
            | Section::Calls
            | Section::References
            | Section::Bindings
            | Section::TypingSignals
            | Section::Constructs
            | Section::Evidence => Porting::Store,
            // The rows of `dependency_edges` hold the condensation ranks of S3. The rows of
            // `imports` are the records of the store with the marks of the typed targets.
            Section::DependencyEdges | Section::Cycles => Porting::Slice(Slice::S3),
            Section::Imports => Porting::Store,
            Section::Contexts | Section::ContextEvidence => Porting::Slice(Slice::S15),
            Section::Violations | Section::Unknowns => Porting::RuleFamilies,
        }
    }

    /// The section of a name, or `None` for a name outside the schema.
    pub fn of_name(name: &str) -> Option<Section> {
        Section::ALL
            .iter()
            .copied()
            .find(|section| section.name() == name)
    }
}
