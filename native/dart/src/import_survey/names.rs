// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed names of the import survey gaps (AD-454) and the one writer of their records.
//! Each gap message starts with its name, so a gap keeps its name in the reply.

use std::collections::BTreeMap;

use archkeel_facts::data::GapEffect;
use archkeel_facts::envelope::Evidence;
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::GapFact;
use archkeel_facts::Record;

use crate::discover::Source;
use crate::records::{cite, gap};
use crate::syntax::Span;

/// The closed vocabulary of the gap names: each name has the Dart prefix.
macro_rules! gap_names {
    ($vis:vis, $($name:ident),+ $(,)?) => {
        /// Each case that the survey does not prove. A gap keeps the scope UNKNOWN.
        #[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
        $vis enum GapName {
            $(#[doc = concat!("The gap `", stringify!($name), "`.")] $name),+
        }

        impl GapName {
            /// Each name, in the order of the declaration.
            #[cfg(test)]
            $vis const ALL: &'static [Self] = &[$(Self::$name),+];

            /// The name as the gap message starts with it.
            $vis fn as_str(self) -> &'static str {
                match self {
                    $(Self::$name => concat!("Dart", stringify!($name))),+
                }
            }
        }
    };
}

gap_names! {
    pub(crate),
    TargetMissing,
    TargetNotSelected,
    TargetOutside,
    TargetIsPart,
    TargetUnparsed,
    UnsupportedUri,
    UriNotLiteral,
    Mirrors,
    Isolate,
    PartUnowned,
    PartNotPart,
    PartConflict,
    Workspace,
    PathDependency,
    NestedPackage,
    PackageConfig,
    LocalPackage,
    UndeclaredPackage,
    ParseBudget,
}

impl GapName {
    /// The protocol kind of the gap record: the nearest existing Dart problem kind.
    fn exception(self) -> ExceptionName {
        match self {
            Self::TargetIsPart | Self::PartUnowned | Self::PartNotPart => ExceptionName::PartError,
            Self::PartConflict => ExceptionName::PartOwnershipConflict,
            Self::Workspace
            | Self::PathDependency
            | Self::NestedPackage
            | Self::PackageConfig
            | Self::LocalPackage
            | Self::UndeclaredPackage => ExceptionName::SnapshotError,
            Self::ParseBudget => ExceptionName::DartSyntaxError,
            _ => ExceptionName::DirectiveError,
        }
    }
}

impl GapName {
    /// What the gap leaves unknown (AD-564), when the survey can state it. `module` is the
    /// library that holds the site, if the gap has one.
    ///
    /// - A package key or file can make a `package:` URI of any library name another file: the
    ///   edges of every library are unknown. The files below the roots and their names are not.
    /// - A directive, a mirror or an isolate site leaves the targets and the exports of its own
    ///   library unknown. So does an import of a package that the package map does not prove
    ///   external (AD-800): only that import can name a local file. Dart code cannot change another library, and an isolate shares no
    ///   library with the code that spawns it.
    /// - A part whose owner is not proven, a second package in a root, an unparsed target and a
    ///   file over the parse budget can put code or a file in a library that the gap does not
    ///   name: no statement, so the whole scope stays unknown.
    fn effect(self, module: Option<&str>) -> Option<GapEffect> {
        let own = || {
            module.map(|name| GapEffect::Modules {
                modules: vec![ModuleName::new(name)],
            })
        };
        match self {
            Self::Workspace | Self::PathDependency | Self::PackageConfig => {
                Some(GapEffect::EveryModule)
            }
            Self::TargetMissing
            | Self::TargetNotSelected
            | Self::TargetOutside
            | Self::UnsupportedUri
            | Self::UriNotLiteral
            | Self::Mirrors
            | Self::Isolate
            | Self::LocalPackage
            | Self::UndeclaredPackage => own(),
            Self::TargetIsPart
            | Self::TargetUnparsed
            | Self::PartUnowned
            | Self::PartNotPart
            | Self::PartConflict
            | Self::NestedPackage
            | Self::ParseBudget => None,
        }
    }
}

/// One named gap: its name and the id of its record in `unknowns`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct NamedGap {
    /// The name of the gap.
    pub name: GapName,
    /// The id of the gap record in `unknowns`.
    pub id: FactId,
}

/// The gap records and the evidence of one survey, each keyed by its id. The first record of an
/// id stays.
#[derive(Default)]
pub(crate) struct Gaps {
    pub(crate) records: BTreeMap<String, Record<GapFact>>,
    pub(crate) named: BTreeMap<String, GapName>,
    pub(crate) evidence: BTreeMap<String, Evidence>,
}

impl Gaps {
    /// A gap of the discovery or the parse: it has a problem kind and no survey name.
    pub(crate) fn plain(
        &mut self,
        (rel, line): (&str, usize),
        kind: ExceptionName,
        message: &str,
        cited: Option<String>,
    ) {
        let (id, record) = gap(rel, line, kind, message, cited);
        self.records.entry(id).or_insert(record);
    }

    /// A named gap at `span` of `source`, or at line 1 of `rel` when there is no span.
    pub(crate) fn named(&mut self, name: GapName, at: Place<'_>, message: &str) {
        self.named_with_related(name, at, message, std::iter::empty());
    }

    /// A named gap with the source spans that contribute to its cause.
    pub(crate) fn named_with_related<'a>(
        &mut self,
        name: GapName,
        at: Place<'_>,
        message: &str,
        related: impl Iterator<Item = (&'a Source, &'a Span)>,
    ) {
        let text = format!("{}: {message}", name.as_str());
        let (rel, line, cited, module) = match at {
            Place::Span(source, span) => (
                source.rel_path.as_str(),
                span.line,
                Some(cite(&mut self.evidence, source, span)),
                Some(source.module.as_str()),
            ),
            Place::File(rel) => (rel, 1, None, None),
        };
        let (id, mut record) = gap(rel, line, name.exception(), &text, cited);
        if let GapFact::ExceptionGap { data, .. } = &mut record.data {
            data.effect = name.effect(module);
        }
        record.evidence_ids.extend(
            related.map(|(source, span)| EvidenceId::new(cite(&mut self.evidence, source, span))),
        );
        self.named.entry(id.clone()).or_insert(name);
        self.records.entry(id).or_insert(record);
    }
}

/// Where a named gap is: a span of a source, or a whole file without evidence.
#[derive(Clone, Copy)]
pub(crate) enum Place<'a> {
    Span(&'a Source, &'a Span),
    File(&'a str),
}

#[cfg(test)]
#[path = "names_tests.rs"]
mod tests;
