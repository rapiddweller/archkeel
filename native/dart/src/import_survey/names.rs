// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed names of the import survey gaps (AD-450) and the one writer of their records.
//! Each gap message starts with its name, so a gap keeps its name in the reply.

use std::collections::BTreeMap;

use archkeel_facts::envelope::Evidence;
use archkeel_facts::ids::FactId;
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::Record;

use crate::discover::Source;
use crate::records::{cite, gap};
use crate::syntax::Span;

/// The closed vocabulary of the gap names: each name is the text of its variant.
macro_rules! gap_names {
    ($($name:ident),+ $(,)?) => {
        /// Each case that the survey does not prove. A gap keeps the scope UNKNOWN.
        #[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
        pub enum GapName {
            $($name),+
        }

        impl GapName {
            /// Each name, in the order of the declaration.
            pub const ALL: &'static [Self] = &[$(Self::$name),+];

            /// The name as the gap message starts with it.
            pub fn as_str(self) -> &'static str {
                match self {
                    $(Self::$name => stringify!($name)),+
                }
            }
        }
    };
}

gap_names! {
    DartTargetMissing,
    DartTargetNotSelected,
    DartTargetOutside,
    DartTargetIsPart,
    DartTargetUnparsed,
    DartUnsupportedUri,
    DartUriNotLiteral,
    DartMirrors,
    DartPartUnowned,
    DartPartNotPart,
    DartPartConflict,
    DartWorkspace,
    DartPathDependency,
    DartNestedPackage,
    DartPackageConfig,
    DartParseBudget,
}

impl GapName {
    /// The protocol kind of the gap record: the nearest existing Dart problem kind.
    fn exception(self) -> ExceptionName {
        match self {
            Self::DartTargetIsPart | Self::DartPartUnowned | Self::DartPartNotPart => {
                ExceptionName::PartError
            }
            Self::DartPartConflict => ExceptionName::PartOwnershipConflict,
            Self::DartWorkspace
            | Self::DartPathDependency
            | Self::DartNestedPackage
            | Self::DartPackageConfig => ExceptionName::SnapshotError,
            Self::DartParseBudget => ExceptionName::DartSyntaxError,
            _ => ExceptionName::DirectiveError,
        }
    }
}

/// One named gap: its name and the id of its record in `unknowns`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NamedGap {
    pub name: GapName,
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
        let text = format!("{}: {message}", name.as_str());
        let (rel, line, cited) = match at {
            Place::Span(source, span) => (
                source.rel_path.as_str(),
                span.line,
                Some(cite(&mut self.evidence, source, span)),
            ),
            Place::File(rel) => (rel, 1, None),
        };
        let (id, record) = gap(rel, line, name.exception(), &text, cited);
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
