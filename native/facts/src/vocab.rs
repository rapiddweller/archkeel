// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabularies of protocol 9. A value that a list does not hold is a decode error.
//!
//! The value sets come from the WP1 inventory of issue #880: the observed values of 148 953 Python,
//! 1 652 Dart and 1 034 TypeScript records, and the kinds that the collector code builds.

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
    /// The kind of a record. The section of the record decides its data type (`sections`).
    /// `ExceptionGap` replaces the open kind of protocol 9: there, the kind of an analyzer failure
    /// is the name of the exception class (`SyntaxError`). The name is a field of the record.
    pub enum Kind {
        Import = "import",
        Reexport = "reexport",
        ImportType = "import_type",
        ImportEquals = "import_equals",
        Require = "require",
        DynamicImport = "dynamic_import",
        ScriptGlobal = "script_global",
        Class = "class",
        Function = "function",
        Method = "method",
        Constant = "constant",
        TypeAlias = "type_alias",
        Binding = "binding",
        Alias = "alias",
        DynamicBinding = "dynamic_binding",
        StaticConstant = "static_constant",
        Calls = "calls",
        Call = "call",
        ResolvedCall = "resolved_call",
        PartiallyResolvedCall = "partially_resolved_call",
        UnresolvedCall = "unresolved_call",
        References = "references",
        Reference = "reference",
        ScriptNamespaceEffect = "script_namespace_effect",
        ValueReference = "value_reference",
        AttributeReference = "attribute_reference",
        SourceRole = "source_role",
        Bindings = "bindings",
        UnusedParameter = "unused_parameter",
        UnusedLocal = "unused_local",
        StringLiteralCompare = "string_literal_compare",
        BroadExcept = "broad_except",
        GetattrCall = "getattr_call",
        HasattrCall = "hasattr_call",
        SetattrCall = "setattr_call",
        DelattrCall = "delattr_call",
        VarsCall = "vars_call",
        ConstructSelector = "construct_selector",
        NumericOperand = "numeric_operand",
        AnyAnnotation = "any_annotation",
        DictAnyAnnotation = "dict_any_annotation",
        CallableAnyAnnotation = "callable_any_annotation",
        ObjectAnnotation = "object_annotation",
        CastCall = "cast_call",
        EvalCall = "eval_call",
        ExecCall = "exec_call",
        TypeIgnore = "type_ignore",
        MissingCrossPackageAnnotation = "missing_cross_package_annotation",
        CollectionGap = "collection_gap",
        SourceResolutionGap = "source_resolution_gap",
        DynamicImportLimit = "dynamic_import_limit",
        PrivateAttributeAccessLimit = "private_attribute_access_limit",
        ExceptionGap = "exception_gap",
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

#[cfg(test)]
#[path = "vocab_tests.rs"]
mod tests;
