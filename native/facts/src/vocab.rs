// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabularies of protocol 9. A value that a list does not hold is a decode error.
//!
//! The value sets come from the WP1 inventory of issue #880: the observed values of 148 953 Python,
//! 1 652 Dart and 1 034 TypeScript records, and the kinds that the collector code builds.
//!
//! `Kind`, `ExceptionName` and `Signal` have `impl` blocks of their own, so they are written as
//! plain enums, each in its own file. The scan of the Rust collector cannot place a type that a
//! macro defines.

#[path = "vocab_exception.rs"]
mod exception;
#[path = "vocab_kind.rs"]
mod kind;
#[path = "vocab_signal.rs"]
mod signal;

pub use exception::ExceptionName;
pub use kind::Kind;
pub use signal::Signal;

closed! {
    /// The area of a record. One concept can have two areas: an import is `source` in TypeScript
    /// and Rust, and `dependencies` in Python and Dart.
    pub enum Area {
        Source = "source",
        Dependencies = "dependencies",
        RepositoryTopology = "repository_topology",
        CallHierarchy = "call_hierarchy",
        Constructs = "constructs",
        TypeArchitecture = "type_architecture",
        AnalysisCoverage = "analysis_coverage",
    }
}

closed! {
    /// The evidence class of a source record. A source record is a fact or an UNKNOWN gap.
    pub enum EvidenceClass {
        Fact = "FACT",
        Unknown = "UNKNOWN",
    }
}

closed! {
    /// How far a call, a reference or a selector is resolved.
    pub enum Status {
        Resolved = "resolved",
        PartiallyResolved = "partially_resolved",
        Unresolved = "unresolved",
        Unknown = "unknown",
        Decided = "decided",
    }
}

closed! {
    pub enum ClassKind {
        Class = "class",
        Dataclass = "dataclass",
        Enum = "enum",
        Protocol = "protocol",
        PydanticModel = "pydantic_model",
    }
}

closed! {
    pub enum MethodKind {
        Instance = "instance",
        Static = "static",
        Class = "class",
        Constructor = "constructor",
        Factory = "factory",
    }
}

closed! {
    /// How a reference uses its target.
    pub enum Use {
        Value = "value",
        Attribute = "attribute",
        Member = "member",
        Read = "read",
        Write = "write",
        Type = "type",
        SourceRole = "source_role",
    }
}

closed! {
    pub enum SymbolCategory {
        Class = "class",
        Constant = "constant",
        DynamicBinding = "dynamic_binding",
        Function = "function",
        Macro = "macro",
        Method = "method",
        TypeAlias = "type_alias",
    }
}

closed! {
    pub enum Visibility {
        Private = "private",
        PublicName = "public_name",
    }
}

closed! {
    pub enum ReferenceContext {
        Annotation = "annotation",
        Value = "value",
        Unknown = "unknown",
    }
}

closed! {
    pub enum SelectorRole {
        Call = "call",
        Constructor = "constructor",
        Endswith = "endswith",
        Equality = "equality",
        Membership = "membership",
        Read = "read",
        Startswith = "startswith",
        TypeProbe = "type_probe",
        Write = "write",
        Match = "match",
        Reflect = "reflect",
    }
}

closed! {
    pub enum Operation {
        Call = "call",
        Compare = "compare",
        Construct = "construct",
        Modulo = "modulo",
        Probe = "probe",
        Read = "read",
        Write = "write",
    }
}

closed! {
    pub enum Role {
        Definition = "definition",
        Delete = "delete",
        Fallback = "fallback",
        ParameterDefault = "parameter_default",
        ValueTransfer = "value_transfer",
        Write = "write",
    }
}

closed! {
    /// What a source resolution gap leaves unknown.
    pub enum ResolutionDimension {
        Imports = "imports",
        RuntimeEffects = "runtime_effects",
        Signature = "signature",
    }
}

closed! {
    pub enum ExpressionKind {
        Literal = "literal",
        Reference = "reference",
        Unsupported = "unsupported",
    }
}

closed! {
    pub enum TransferKind {
        DictionaryValue = "dictionary_value",
        UnsupportedDictionaryValue = "unsupported_dictionary_value",
    }
}

closed! {
    /// Whether a numeric operand is proven.
    pub enum Proof {
        Known = "known",
        Unknown = "unknown",
    }
}

closed! {
    /// The written form of a construct or of a numeric operand (Python).
    pub enum ConstructForm {
        Binary = "binary",
        Compare = "compare",
        Endswith = "endswith",
        Membership = "membership",
        Startswith = "startswith",
        Match = "match",
    }
}

closed! {
    /// The two function bodies that the collector identifies as placeholders.
    pub enum PlaceholderForm {
        Empty = "empty",
        NotImplemented = "not_implemented",
    }
}

closed! {
    /// How a class relates to a base declaration.
    pub enum RelationshipKind {
        Inherits = "inherits",
        Realizes = "realizes",
    }
}

closed! {
    /// The members that a member inventory lists (`facts.MemberKind`).
    pub enum MemberKind {
        Attribute = "attribute",
        Method = "method",
    }
}

closed! {
    /// Whether a member inventory lists every member (`facts.InventoryStatus`).
    pub enum InventoryStatus {
        Complete = "complete",
        Partial = "partial",
    }
}

#[cfg(test)]
#[path = "vocab_tests.rs"]
mod tests;
