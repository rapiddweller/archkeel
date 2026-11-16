// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The vocabularies of the construct, source role and typing signal records.

closed! {
    /// The role that a selector plays at its site.
    pub enum SelectorRole {
        /// The selector is a call.
        Call = "call",
        /// The selector is a constructor call.
        Constructor = "constructor",
        /// The selector is an `endswith` test.
        Endswith = "endswith",
        /// The selector is an equality test.
        Equality = "equality",
        /// The selector is a membership test.
        Membership = "membership",
        /// The selector is a read.
        Read = "read",
        /// The selector is a `startswith` test.
        Startswith = "startswith",
        /// The selector is a type test.
        TypeProbe = "type_probe",
        /// The selector is a write.
        Write = "write",
        /// The selector is a pattern match.
        Match = "match",
        /// The selector is a reflection call.
        Reflect = "reflect",
    }
}

closed! {
    /// What a site does with its receiver.
    pub enum Operation {
        /// A call.
        Call = "call",
        /// A comparison.
        Compare = "compare",
        /// A construction.
        Construct = "construct",
        /// A modulo operation.
        Modulo = "modulo",
        /// A probe of a member.
        Probe = "probe",
        /// A read.
        Read = "read",
        /// A write.
        Write = "write",
    }
}

closed! {
    /// The role that a source value plays.
    pub enum Role {
        /// The value defines the name.
        Definition = "definition",
        /// The value deletes the name.
        Delete = "delete",
        /// The value is a fallback.
        Fallback = "fallback",
        /// The value is the default of a parameter.
        ParameterDefault = "parameter_default",
        /// The value passes to another name.
        ValueTransfer = "value_transfer",
        /// The value is written.
        Write = "write",
    }
}

closed! {
    /// What a source resolution gap leaves unknown.
    pub enum ResolutionDimension {
        /// The imports are not resolved.
        Imports = "imports",
        /// The effects at run time are not known.
        RuntimeEffects = "runtime_effects",
        /// The signature is not read.
        Signature = "signature",
    }
}

closed! {
    /// The kind of an expression that a source role holds.
    pub enum ExpressionKind {
        /// A literal.
        Literal = "literal",
        /// A reference.
        Reference = "reference",
        /// A form that the collector does not read.
        Unsupported = "unsupported",
    }
}

closed! {
    /// How a value passes from a source to a target.
    pub enum TransferKind {
        /// A value of a dictionary.
        DictionaryValue = "dictionary_value",
        /// A value of a dictionary that the collector does not read.
        UnsupportedDictionaryValue = "unsupported_dictionary_value",
    }
}

closed! {
    /// Whether a numeric operand is proven.
    pub enum Proof {
        /// The operand is proven.
        Known = "known",
        /// The operand is not proven.
        Unknown = "unknown",
    }
}

closed! {
    /// The written form of a construct or of a numeric operand (Python).
    pub enum ConstructForm {
        /// A binary operation.
        Binary = "binary",
        /// A comparison.
        Compare = "compare",
        /// An `endswith` call.
        Endswith = "endswith",
        /// A membership test.
        Membership = "membership",
        /// A `startswith` call.
        Startswith = "startswith",
        /// A pattern match.
        Match = "match",
    }
}

closed! {
    /// The two function bodies that the collector identifies as placeholders.
    pub enum PlaceholderForm {
        /// A body with no statement.
        Empty = "empty",
        /// A body that raises `NotImplementedError`.
        NotImplemented = "not_implemented",
    }
}

closed! {
    /// The typing signal of a record of `typing_signals`; the text equals the kind of the record.
    pub enum Signal {
        /// An `Any` annotation.
        AnyAnnotation = "any_annotation",
        /// A dict annotation with `Any` values.
        DictAnyAnnotation = "dict_any_annotation",
        /// A callable annotation with `Any`.
        CallableAnyAnnotation = "callable_any_annotation",
        /// An `object` annotation.
        ObjectAnnotation = "object_annotation",
        /// A call of `cast`.
        CastCall = "cast_call",
        /// A call of `getattr`.
        GetattrCall = "getattr_call",
        /// A call of `hasattr`.
        HasattrCall = "hasattr_call",
        /// A call of `eval`.
        EvalCall = "eval_call",
        /// A call of `exec`.
        ExecCall = "exec_call",
        /// An import that is computed at run time.
        DynamicImport = "dynamic_import",
        /// A `type: ignore` comment.
        TypeIgnore = "type_ignore",
        /// A position that crosses a package with no annotation.
        MissingCrossPackageAnnotation = "missing_cross_package_annotation",
    }
}
