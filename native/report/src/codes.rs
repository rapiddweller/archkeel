// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed code lists of the payload (AD-361 point 10).
//!
//! A code is the position of a value in its list (`x-codes` of the schema). A list only grows at
//! the end within a major version, so a payload can hold a code beyond the list of this crate. A
//! `Code` keeps any number for the round trip; `Code::known` gives the value of the list or
//! `None`, and the check refuses a code that this crate cannot read (never as clean).

use std::cmp::Ordering;
use std::fmt;
use std::marker::PhantomData;

use serde::{Deserialize, Deserializer, Serialize, Serializer};

/// One closed code list of the schema.
pub trait CodeList: Copy + 'static {
    /// The name of the list in `$defs` of the schema.
    const NAME: &'static str;
    /// The values, in code order.
    const VALUES: &'static [Self];
    /// The text of each value, in code order (`x-codes`).
    const TEXTS: &'static [&'static str];
    /// The code of this value.
    fn code(self) -> u32;
}

/// A code of the list `L`, as the payload holds it.
pub struct Code<L> {
    value: u32,
    list: PhantomData<L>,
}

impl<L: CodeList> Code<L> {
    /// The code of one value of the list.
    pub fn of(value: L) -> Code<L> {
        Code::raw(value.code())
    }

    /// A code as read from a payload; it can lie beyond the list.
    pub fn raw(value: u32) -> Code<L> {
        Code {
            value,
            list: PhantomData,
        }
    }

    /// The number of the code.
    pub fn value(self) -> u32 {
        self.value
    }

    /// The value of the list, or `None` for a code beyond the list of this crate.
    pub fn known(self) -> Option<L> {
        usize::try_from(self.value)
            .ok()
            .and_then(|index| L::VALUES.get(index).copied())
    }

    /// True when the code is this value.
    pub fn is(self, value: L) -> bool {
        self.value == value.code()
    }
}

impl<L> Clone for Code<L> {
    fn clone(&self) -> Self {
        *self
    }
}

impl<L> Copy for Code<L> {}

impl<L> PartialEq for Code<L> {
    fn eq(&self, other: &Self) -> bool {
        self.value == other.value
    }
}

impl<L> Eq for Code<L> {}

impl<L> PartialOrd for Code<L> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl<L> Ord for Code<L> {
    fn cmp(&self, other: &Self) -> Ordering {
        self.value.cmp(&other.value)
    }
}

impl<L: CodeList> fmt::Debug for Code<L> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let text = usize::try_from(self.value)
            .ok()
            .and_then(|index| L::TEXTS.get(index));
        match text {
            Some(text) => write!(formatter, "{}:{text}", L::NAME),
            None => write!(formatter, "{}:{}?", L::NAME, self.value),
        }
    }
}

impl<L> Serialize for Code<L> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_u32(self.value)
    }
}

impl<'de, L> Deserialize<'de> for Code<L> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(Code {
            value: u32::deserialize(deserializer)?,
            list: PhantomData,
        })
    }
}

macro_rules! code_list {
    ($(#[$doc:meta])* $name:ident { $($variant:ident = $text:literal),+ $(,)? }) => {
        $(#[$doc])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
        #[allow(missing_docs)]
        pub enum $name { $($variant),+ }

        impl CodeList for $name {
            const NAME: &'static str = stringify!($name);
            const VALUES: &'static [Self] = &[$($name::$variant),+];
            const TEXTS: &'static [&'static str] = &[$($text),+];
            fn code(self) -> u32 {
                self as u32
            }
        }
    };
}

code_list!(
    /// The level of a node or an edge.
    Level { System = "system", Package = "package", Component = "component", Module = "module" }
);
code_list!(
    /// The kind of a unit or a crossing name.
    Kind {
        Struct = "struct", Enum = "enum", Trait = "trait", Class = "class",
        Interface = "interface", TypeAlias = "type_alias", Constant = "constant",
        Function = "function", Method = "method", Macro = "macro", Variable = "variable",
        Component = "component", Static = "static", Module = "module", Unknown = "unknown",
    }
);
code_list!(
    /// The visibility of a unit.
    Vis { Public = "public", Package = "package", Private = "private", Unknown = "unknown" }
);
code_list!(
    /// The state of a measure row.
    MeasureState {
        Measured = "measured", Unknown = "unknown", Undeclared = "undeclared",
        NotApplicable = "not_applicable",
    }
);
code_list!(
    /// The budget verdict of a measure row.
    Verdict { None = "none", Within = "within", Over = "over" }
);
code_list!(
    /// The permission of the component pair of an edge.
    EdgeTarget {
        NoTarget = "no_target", Declared = "declared", Undeclared = "undeclared",
        Forbidden = "forbidden",
    }
);
code_list!(
    /// The kind of a finding.
    FindingKind {
        FanInHub = "fan_in_hub", FanOutHub = "fan_out_hub", Cycle = "cycle",
        Violation = "violation", ApiOutsideList = "api_outside_list",
        OverBudget = "over_budget", UnusedRequires = "unused_requires",
    }
);
code_list!(
    /// How a finding is shown.
    Disposition { Ranked = "ranked", Declared = "declared", Context = "context" }
);
code_list!(
    /// Why a finding has its disposition.
    Reason {
        OpenQuestion = "open_question", Kernel = "kernel", Orchestrator = "orchestrator",
        CrateFacade = "crate_facade", TestOnly = "test_only", RulePasses = "rule_passes",
        LeftDeclaration = "left_declaration",
    }
);
code_list!(
    /// A measure definition.
    Measure {
        RClear = "R.clear", ROwned = "R.owned", RStated = "R.stated", RSize = "R.size",
        IDeclared = "I.declared", IApi = "I.api", ISurface = "I.surface",
        DResolved = "D.resolved", DTypes = "D.types", DSignatures = "D.signatures",
        DDeclared = "D.declared", EKnown = "E.known", EParsed = "E.parsed",
        EExcluded = "E.excluded",
    }
);
code_list!(
    /// A named gap: a fact or a declaration that the payload does not have.
    Gap {
        CodeLines = "G-CODE-LINES", Signatures = "G-SIGNATURES", Origin = "G-ORIGIN",
        Uses = "G-USES", PublicApi = "G-PUBLIC-API", BoundaryTypes = "G-BOUNDARY-TYPES",
        Budgets = "G-BUDGETS", Trend = "G-TREND", Excluded = "G-EXCLUDED",
        NoContract = "G-NO-CONTRACT", ContractLines = "G-CONTRACT-LINES", Roles = "G-ROLES",
    }
);
code_list!(
    /// A relation that a payload can carry (`run.not_carried`).
    Relation {
        Imports = "imports", Reexports = "reexports", Variants = "variants", Calls = "calls",
        References = "references", Implements = "implements", UsesType = "uses_type",
        Fields = "fields", Signatures = "signatures", CodeLines = "code_lines",
        ContractLines = "contract_lines",
    }
);
code_list!(
    /// The permission of an ordered pair of sibling components.
    Permission { Allowed = "allowed", Forbidden = "forbidden", Undecided = "undecided" }
);
code_list!(
    /// Where an unknown row comes from.
    UnknownSource { Record = "record", Diagnostic = "diagnostic", Run = "run" }
);
code_list!(
    /// Why a fact or a verdict is unknown.
    UnknownReason {
        CollectionGap = "collection_gap", SourceResolutionGap = "source_resolution_gap",
        SyntaxError = "SyntaxError", TooDeepError = "TooDeepError",
        UnicodeDecodeError = "UnicodeDecodeError",
        UnsupportedDeclaration = "UnsupportedDeclaration",
        BoundaryTypeLimit = "boundary_type_limit",
        BoundaryTypePosition = "boundary_type_position",
        CallArgumentLimit = "call_argument_limit", CallOwnerLimit = "call_owner_limit",
        ContextAliasLimit = "context_alias_limit", DynamicCallLimit = "dynamic_call_limit",
        DynamicDependencyLimit = "dynamic_dependency_limit",
        DynamicImportLimit = "dynamic_import_limit",
        InterfaceSymbolLimit = "interface_symbol_limit",
        PrivateAttributeAccessLimit = "private_attribute_access_limit",
        UmlAssessmentUnavailable = "uml_assessment_unavailable",
        UmlConformance = "uml_conformance", MissingTool = "missing_tool", Timeout = "timeout",
        ParseError = "parse_error", UnresolvedImport = "unresolved_import",
        NotExamined = "not_examined", IncompleteScan = "incomplete_scan",
        ScopeEmpty = "scope_empty", RuleWithoutSubjects = "rule_without_subjects",
        RuleUnsupportedByProfile = "rule_unsupported_by_profile",
        RuntimeMismatch = "runtime_mismatch", IncomparableRuntime = "incomparable_runtime",
        ContractInvalid = "contract_invalid", ExistingFiles = "existing_files",
        FilterUnknown = "filter_unknown", NoTarget = "no_target", Other = "other",
    }
);

impl UnknownReason {
    /// The reason of a raw kind; a kind outside the list is `other` and keeps its raw text.
    pub fn of_kind(kind: &str) -> UnknownReason {
        UnknownReason::TEXTS
            .iter()
            .position(|text| *text == kind)
            .and_then(|index| UnknownReason::VALUES.get(index).copied())
            .unwrap_or(UnknownReason::Other)
    }

    /// A diagnostic of this reason revokes the proofs of an incomplete run (AD-361 point 4).
    pub fn revokes(self) -> bool {
        matches!(
            self,
            UnknownReason::RuntimeMismatch
                | UnknownReason::IncomparableRuntime
                | UnknownReason::ContractInvalid
        )
    }
}

/// The relations that a payload of this version does not carry (`run.not_carried`).
pub const NOT_CARRIED: [Relation; 8] = [
    Relation::Calls,
    Relation::References,
    Relation::Implements,
    Relation::UsesType,
    Relation::Fields,
    Relation::Signatures,
    Relation::CodeLines,
    Relation::ContractLines,
];
