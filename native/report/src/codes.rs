// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed code lists of the payload (AD-361 point 10).
//!
//! A code is the position of a value in its list (`x-codes` of the schema). A list only grows at
//! the end within a major version, so a payload can hold a code beyond the list of this crate. A
//! `Code` keeps any number for the round trip; `Code::known` gives the value of the list or
//! `None`, and the check refuses a code that this crate cannot read (never as clean).

pub use crate::code::{Code, CodeList};

macro_rules! code_list {
    // `NAME` is the schema name (`$defs`): the type name, or the name after `as` when they differ.
    (@name $name:ident $schema:literal) => { $schema };
    (@name $name:ident) => { stringify!($name) };
    ($(#[$doc:meta])* $name:ident $(as $schema:literal)? {
        $($(#[$vdoc:meta])* $variant:ident = $text:literal),+ $(,)?
    }) => {
        $(#[$doc])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
        pub enum $name { $($(#[$vdoc])* $variant),+ }

        impl CodeList for $name {
            const NAME: &'static str = code_list!(@name $name $($schema)?);
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
    NodeLevel as "Level" {
        /// The whole system.
        System = "system",
        /// A package.
        Package = "package",
        /// A component of the contract.
        Component = "component",
        /// A module.
        Module = "module",
    }
);
code_list!(
    /// The kind of a unit or a crossing name.
    Kind {
        /// A struct.
        Struct = "struct",
        /// An enum.
        Enum = "enum",
        /// A trait.
        Trait = "trait",
        /// A class.
        Class = "class",
        /// An interface.
        Interface = "interface",
        /// A type alias.
        TypeAlias = "type_alias",
        /// A constant.
        Constant = "constant",
        /// A function.
        Function = "function",
        /// A method.
        Method = "method",
        /// A macro.
        Macro = "macro",
        /// A variable.
        Variable = "variable",
        /// A component.
        Component = "component",
        /// A static item.
        Static = "static",
        /// A module.
        Module = "module",
        /// A kind that the collector does not tell.
        Unknown = "unknown",
    }
);
code_list!(
    /// The visibility of a unit.
    Vis {
        /// Public.
        Public = "public",
        /// Visible in the package.
        Package = "package",
        /// Private.
        Private = "private",
        /// Not known.
        Unknown = "unknown",
    }
);
code_list!(
    /// The state of a measure row.
    MeasureState {
        /// The core measured the value.
        Measured = "measured",
        /// The value is not known.
        Unknown = "unknown",
        /// The contract declares no budget.
        Undeclared = "undeclared",
        /// The measure does not apply to the node.
        NotApplicable = "not_applicable",
    }
);
code_list!(
    /// The budget verdict of a measure row.
    BudgetVerdict as "Verdict" {
        /// There is no verdict.
        None = "none",
        /// The value is within the budget.
        Within = "within",
        /// The value is over the budget.
        Over = "over",
    }
);
code_list!(
    /// The permission of the component pair of an edge.
    EdgeTarget {
        /// The contract has no target for the edge.
        NoTarget = "no_target",
        /// The contract declares the edge.
        Declared = "declared",
        /// The contract does not declare the edge.
        Undeclared = "undeclared",
        /// The contract forbids the edge.
        Forbidden = "forbidden",
    }
);
code_list!(
    /// The kind of a finding.
    FindingKind {
        /// A node that many nodes import.
        FanInHub = "fan_in_hub",
        /// A node that imports many nodes.
        FanOutHub = "fan_out_hub",
        /// A cycle of imports.
        Cycle = "cycle",
        /// A violation of a rule.
        Violation = "violation",
        /// A name that is used but not in the public list.
        ApiOutsideList = "api_outside_list",
        /// A value over its budget.
        OverBudget = "over_budget",
        /// A declared requirement that no import uses.
        UnusedRequires = "unused_requires",
    }
);
code_list!(
    /// How a finding is shown.
    Disposition {
        /// The report ranks the finding.
        Ranked = "ranked",
        /// The contract declares the finding.
        Declared = "declared",
        /// The finding only gives context.
        Context = "context",
    }
);
code_list!(
    /// Why a finding has its disposition.
    FindingReason as "Reason" {
        /// The cause is an open question.
        OpenQuestion = "open_question",
        /// The node is a kernel that many nodes use by design.
        Kernel = "kernel",
        /// The node is an orchestrator that uses many nodes by design.
        Orchestrator = "orchestrator",
        /// The node is the facade of a crate.
        CrateFacade = "crate_facade",
        /// Only tests use the node.
        TestOnly = "test_only",
        /// A rule that passes covers the finding.
        RulePasses = "rule_passes",
        /// The contract leaves the declaration open.
        LeftDeclaration = "left_declaration",
    }
);
code_list!(
    /// A measure definition.
    MeasureDef as "Measure" {
        /// Whether the code is clear to read.
        RClear = "R.clear",
        /// Whether each part has an owner.
        ROwned = "R.owned",
        /// Whether each part states its responsibility.
        RStated = "R.stated",
        /// The size of the node.
        RSize = "R.size",
        /// The interfaces that the contract declares.
        IDeclared = "I.declared",
        /// The size of the public API.
        IApi = "I.api",
        /// The size of the surface that other nodes use.
        ISurface = "I.surface",
        /// The calls that the core resolves.
        DResolved = "D.resolved",
        /// The positions that have a type.
        DTypes = "D.types",
        /// The signatures that the collector reads.
        DSignatures = "D.signatures",
        /// The dependencies that the contract declares.
        DDeclared = "D.declared",
        /// The files that the scan knows.
        EKnown = "E.known",
        /// The files that the scan parses.
        EParsed = "E.parsed",
        /// The files that the scan excludes.
        EExcluded = "E.excluded",
    }
);
code_list!(
    /// A named gap: a fact or a declaration that the payload does not have.
    Gap {
        /// The payload has no count of code lines.
        CodeLines = "G-CODE-LINES",
        /// The payload has no signatures.
        Signatures = "G-SIGNATURES",
        /// The payload has no origin of the names.
        Origin = "G-ORIGIN",
        /// The payload has no uses of the names.
        Uses = "G-USES",
        /// The contract declares no public API.
        PublicApi = "G-PUBLIC-API",
        /// The payload has no boundary types.
        BoundaryTypes = "G-BOUNDARY-TYPES",
        /// The contract declares no budgets.
        Budgets = "G-BUDGETS",
        /// The payload has no trend.
        Trend = "G-TREND",
        /// The scan excludes files.
        Excluded = "G-EXCLUDED",
        /// The run has no contract.
        NoContract = "G-NO-CONTRACT",
        /// The payload has no count of contract lines.
        ContractLines = "G-CONTRACT-LINES",
        /// The contract declares no roles.
        Roles = "G-ROLES",
    }
);
code_list!(
    /// A relation that a payload can carry (`run.not_carried`).
    Relation {
        /// Imports.
        Imports = "imports",
        /// Imports that publish a name again.
        Reexports = "reexports",
        /// The variants of enums.
        Variants = "variants",
        /// Calls.
        Calls = "calls",
        /// References.
        References = "references",
        /// Implements relations.
        Implements = "implements",
        /// Uses of a type.
        UsesType = "uses_type",
        /// Fields.
        Fields = "fields",
        /// Signatures.
        Signatures = "signatures",
        /// Lines of code.
        CodeLines = "code_lines",
        /// Lines of the contract.
        ContractLines = "contract_lines",
    }
);
code_list!(
    /// The permission of an ordered pair of sibling components.
    Permission {
        /// The contract allows the import.
        Allowed = "allowed",
        /// The contract forbids the import.
        Forbidden = "forbidden",
        /// The contract does not decide the import.
        Undecided = "undecided",
    }
);
code_list!(
    /// Where an unknown row comes from.
    UnknownSource {
        /// A record of the facts.
        Record = "record",
        /// A diagnostic of the run.
        Diagnostic = "diagnostic",
        /// The run as a whole.
        Run = "run",
    }
);
code_list!(
    /// Why a fact or a verdict is unknown.
    UnknownReason {
        /// A gap of the collection.
        CollectionGap = "collection_gap",
        /// A gap of the resolution of a source name.
        SourceResolutionGap = "source_resolution_gap",
        /// A file has a syntax error.
        SyntaxError = "SyntaxError",
        /// A file nests deeper than the limit.
        TooDeepError = "TooDeepError",
        /// A file is not valid text.
        UnicodeDecodeError = "UnicodeDecodeError",
        /// A declaration is not supported.
        UnsupportedDeclaration = "UnsupportedDeclaration",
        /// A boundary type is beyond what the core decides.
        BoundaryTypeLimit = "boundary_type_limit",
        /// A boundary position is not read.
        BoundaryTypePosition = "boundary_type_position",
        /// A call argument is beyond what the core decides.
        CallArgumentLimit = "call_argument_limit",
        /// A call owner is beyond what the core decides.
        CallOwnerLimit = "call_owner_limit",
        /// A context alias is beyond what the core decides.
        ContextAliasLimit = "context_alias_limit",
        /// A call is computed at run time.
        DynamicCallLimit = "dynamic_call_limit",
        /// A dependency is computed at run time.
        DynamicDependencyLimit = "dynamic_dependency_limit",
        /// An import is computed at run time.
        DynamicImportLimit = "dynamic_import_limit",
        /// An interface symbol is beyond what the core decides.
        InterfaceSymbolLimit = "interface_symbol_limit",
        /// An access to a private attribute is beyond what the core decides.
        PrivateAttributeAccessLimit = "private_attribute_access_limit",
        /// The UML assessment is not available.
        UmlAssessmentUnavailable = "uml_assessment_unavailable",
        /// The UML conformance is not decided.
        UmlConformance = "uml_conformance",
        /// A tool that the run needs is missing.
        MissingTool = "missing_tool",
        /// A step took too long.
        Timeout = "timeout",
        /// A file did not parse.
        ParseError = "parse_error",
        /// An import has no proven target.
        UnresolvedImport = "unresolved_import",
        /// The scan did not examine the part.
        NotExamined = "not_examined",
        /// The scan is not complete.
        IncompleteScan = "incomplete_scan",
        /// The scope holds no file.
        ScopeEmpty = "scope_empty",
        /// The rule has no subject in the scope.
        RuleWithoutSubjects = "rule_without_subjects",
        /// The profile does not support the rule.
        RuleUnsupportedByProfile = "rule_unsupported_by_profile",
        /// The runtime differs from the one that the project requires.
        RuntimeMismatch = "runtime_mismatch",
        /// The runtime cannot be compared with the requirement.
        IncomparableRuntime = "incomparable_runtime",
        /// The contract is not valid.
        ContractInvalid = "contract_invalid",
        /// The scan limits itself to existing files.
        ExistingFiles = "existing_files",
        /// A filter of the run is not known.
        FilterUnknown = "filter_unknown",
        /// The contract has no target.
        NoTarget = "no_target",
        /// Any other reason; the raw text is kept.
        Other = "other",
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
