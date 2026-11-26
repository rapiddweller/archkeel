// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabularies of protocol 9. A value that a list does not hold is a decode error.
//!
//! The value sets come from the WP1 inventory of issue #880: the observed values of 148 953 Python,
//! 1 652 Dart and 1 034 TypeScript records, and the kinds that the collector code builds.

pub use crate::vocab_constructs::{
    ConstructForm, ExpressionKind, Operation, PlaceholderForm, Proof, ResolutionDimension, Role,
    SelectorRole, Signal, TransferKind,
};

closed! {
    /// The area of a record. One concept can have two areas: an import is `source` in TypeScript
    /// and Rust, and `dependencies` in Python and Dart.
    pub enum Area {
        /// Source facts such as imports.
        Source = "source",
        /// Dependency facts of the language.
        Dependencies = "dependencies",
        /// The layout of the repository.
        RepositoryTopology = "repository_topology",
        /// Calls and references.
        CallHierarchy = "call_hierarchy",
        /// Written constructs that a rule can forbid.
        Constructs = "constructs",
        /// Types and their relations.
        TypeArchitecture = "type_architecture",
        /// What the analysis does not cover.
        AnalysisCoverage = "analysis_coverage",
    }
}

closed! {
    /// The evidence class of a source record. A source record is a fact or an UNKNOWN gap.
    pub enum EvidenceClass {
        /// A record that the collector proves.
        Fact = "FACT",
        /// A gap that the collector names.
        Unknown = "UNKNOWN",
    }
}

closed! {
    /// The kind of a record. The section of the record decides its data type (`sections`).
    /// `ExceptionGap` replaces the open kind of protocol 9: there, the kind of an analyzer failure
    /// is the name of the exception class (`SyntaxError`). The name is a field of the record.
    pub enum Kind {
        /// An import statement or imported name.
        Import = "import",
        /// An import that publishes the name again.
        Reexport = "reexport",
        /// A type-only import.
        ImportType = "import_type",
        /// An `import x = require()` form.
        ImportEquals = "import_equals",
        /// A `require` call.
        Require = "require",
        /// An import whose target is computed at run time.
        DynamicImport = "dynamic_import",
        /// A global that a script file binds.
        ScriptGlobal = "script_global",
        /// An import inside a macro body.
        MacroBody = "macro_body",
        /// A class symbol.
        Class = "class",
        /// A function symbol.
        Function = "function",
        /// A method symbol.
        Method = "method",
        /// A constant symbol.
        Constant = "constant",
        /// A type alias symbol.
        TypeAlias = "type_alias",
        /// A name binding.
        Binding = "binding",
        /// An alias symbol.
        Alias = "alias",
        /// A binding that is set at run time.
        DynamicBinding = "dynamic_binding",
        /// A constant with a value that is known statically.
        StaticConstant = "static_constant",
        /// A macro symbol.
        Macro = "macro",
        /// A module-level variable that is not constant (Dart, AD-796).
        Attribute = "attribute",
        /// The calls of one scope.
        Calls = "calls",
        /// A call.
        Call = "call",
        /// A call with one proven target.
        ResolvedCall = "resolved_call",
        /// A call with a target that is only partly proven.
        PartiallyResolvedCall = "partially_resolved_call",
        /// A call with no proven target.
        UnresolvedCall = "unresolved_call",
        /// The references of one scope.
        References = "references",
        /// A reference to a name.
        Reference = "reference",
        /// A write into the namespace of a script.
        ScriptNamespaceEffect = "script_namespace_effect",
        /// A reference that reads a value.
        ValueReference = "value_reference",
        /// A reference to an attribute.
        AttributeReference = "attribute_reference",
        /// The role that a source value plays.
        SourceRole = "source_role",
        /// The bindings of one scope.
        Bindings = "bindings",
        /// A parameter that nothing reads.
        UnusedParameter = "unused_parameter",
        /// A local name that nothing reads.
        UnusedLocal = "unused_local",
        /// A comparison with a string literal.
        StringLiteralCompare = "string_literal_compare",
        /// A broad exception handler.
        BroadExcept = "broad_except",
        /// A call of `getattr`.
        GetattrCall = "getattr_call",
        /// A call of `hasattr`.
        HasattrCall = "hasattr_call",
        /// A call of `setattr`.
        SetattrCall = "setattr_call",
        /// A call of `delattr`.
        DelattrCall = "delattr_call",
        /// A call of `vars`.
        VarsCall = "vars_call",
        /// A selector on a receiver.
        ConstructSelector = "construct_selector",
        /// A numeric operand with its proof.
        NumericOperand = "numeric_operand",
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
        /// A call of `eval`.
        EvalCall = "eval_call",
        /// A call of `exec`.
        ExecCall = "exec_call",
        /// A `type: ignore` comment.
        TypeIgnore = "type_ignore",
        /// A position that crosses a package with no annotation.
        MissingCrossPackageAnnotation = "missing_cross_package_annotation",
        /// A gap of the collection.
        CollectionGap = "collection_gap",
        /// A gap of the resolution of a source name.
        SourceResolutionGap = "source_resolution_gap",
        /// A dynamic import that the collector cannot follow.
        DynamicImportLimit = "dynamic_import_limit",
        /// An access to a private attribute that the collector cannot type.
        PrivateAttributeAccessLimit = "private_attribute_access_limit",
        /// An analyzer failure; the data holds the class name.
        ExceptionGap = "exception_gap",
        /// An `assert` statement.
        AssertStatement = "assert_statement",
        /// A function body that declares no implementation.
        PlaceholderBody = "placeholder_body",
        /// A use of `__dict__`.
        DunderDict = "dunder_dict",
    }
}

closed! {
    /// The protocol 9 kind of an analyzer failure (`Kind::ExceptionGap`). Python writes the class
    /// name of the exception that stopped a file: `OSError` and the subclasses that a file read can
    /// raise, `UnicodeDecodeError`, `SyntaxError` and its subclasses, `ValueError` and
    /// `TooDeepError` (`analyzer/python/source.py`). Dart writes the names of its problem kinds
    /// (`analyzer/dart/collect.py`, `resolve.py`, `snapshot.py`, `syntax.py`).
    pub enum ExceptionName {
        /// The file has a syntax error.
        SyntaxError = "SyntaxError",
        /// The file has a wrong indentation.
        IndentationError = "IndentationError",
        /// The file mixes tabs and spaces.
        TabError = "TabError",
        /// The file is not valid text in its encoding.
        UnicodeDecodeError = "UnicodeDecodeError",
        /// The source holds a value that the parser refuses.
        ValueError = "ValueError",
        /// The source nests deeper than the limit.
        TooDeepError = "TooDeepError",
        /// The operating system failed to read the file.
        OsError = "OSError",
        /// The file does not exist.
        FileNotFoundError = "FileNotFoundError",
        /// The file is not readable.
        PermissionError = "PermissionError",
        /// The path is a directory.
        IsADirectoryError = "IsADirectoryError",
        /// A part of the path is not a directory.
        NotADirectoryError = "NotADirectoryError",
        /// The read took too long.
        TimeoutError = "TimeoutError",
        /// The read was interrupted.
        InterruptedError = "InterruptedError",
        /// A directive of the source is not valid.
        DirectiveError = "DirectiveError",
        /// The declaration is not supported.
        UnsupportedDeclaration = "UnsupportedDeclaration",
        /// The member is not supported.
        UnsupportedMember = "UnsupportedMember",
        /// The parameter is not supported.
        UnsupportedParameter = "UnsupportedParameter",
        /// The language version of the file is not supported.
        LanguageVersionError = "LanguageVersionError",
        /// The SDK constraint of the package is not valid.
        SdkConstraintError = "SdkConstraintError",
        /// The same name is declared twice.
        DuplicateDeclaration = "DuplicateDeclaration",
        /// A part file is not valid.
        PartError = "PartError",
        /// Two libraries claim one part file.
        PartOwnershipConflict = "PartOwnershipConflict",
        /// A source link of Dart is not valid.
        DartSourceLink = "DartSourceLink",
        /// The snapshot of the tree is not valid.
        SnapshotError = "SnapshotError",
        /// A Dart module is not valid.
        DartModuleError = "DartModuleError",
        /// Two Dart files name the same module.
        DartModuleCollision = "DartModuleCollision",
        /// A selected root is not valid.
        SelectedRootError = "SelectedRootError",
        /// A path leaves the root.
        ContainmentError = "ContainmentError",
        /// A tree that the scan excludes is read.
        ExcludedTreeError = "ExcludedTreeError",
        /// The package has no `pubspec.yaml`.
        PubspecMissing = "PubspecMissing",
        /// The Dart file has a syntax error.
        DartSyntaxError = "syntax_error",
        /// The file has an invalid encoding.
        InvalidEncoding = "invalid_encoding",
        /// Protocol 10.0.0 only (AD-367): the published 9.0.0 schema does not list it.
        ShadowedModule = "ShadowedModule",
    }
}

impl ExceptionName {
    /// Whether the published 9.0.0 schema lists the name.
    pub(crate) fn in_v9(self) -> bool {
        self != Self::ShadowedModule
    }
}

closed! {
    /// How far a call, a reference or a selector is resolved.
    pub enum Status {
        /// The target is proven.
        Resolved = "resolved",
        /// Some targets are proven and some are not.
        PartiallyResolved = "partially_resolved",
        /// No target is proven.
        Unresolved = "unresolved",
        /// The collector does not decide.
        Unknown = "unknown",
        /// The collector decides by its own rule.
        Decided = "decided",
    }
}

impl Status {
    /// How far a site is resolved from the targets that it names (AD-741): one target that is
    /// proven unique resolves it, no target leaves it unresolved, and every other case (several
    /// targets, or one that is not proven unique) resolves it in part. Each collector takes the
    /// status of a site, a base and a construction from here; the reason text stays its own.
    pub fn of_candidates(candidates: usize, unique: bool) -> Self {
        if candidates == 0 {
            Self::Unresolved
        } else if candidates == 1 && unique {
            Self::Resolved
        } else {
            Self::PartiallyResolved
        }
    }
}

closed! {
    /// The kind of a class.
    pub enum ClassKind {
        /// A plain class.
        Class = "class",
        /// A dataclass.
        Dataclass = "dataclass",
        /// An enum.
        Enum = "enum",
        /// A protocol.
        Protocol = "protocol",
        /// A pydantic model.
        PydanticModel = "pydantic_model",
        /// A Dart mixin (AD-796).
        Mixin = "mixin",
    }
}

closed! {
    /// The kind of a method.
    pub enum MethodKind {
        /// A method of an instance.
        Instance = "instance",
        /// A static method.
        Static = "static",
        /// A class method.
        Class = "class",
        /// A constructor.
        Constructor = "constructor",
        /// A factory.
        Factory = "factory",
    }
}

closed! {
    /// How a reference uses its target.
    pub enum Use {
        /// The target is read as a value.
        Value = "value",
        /// An attribute of the target is read.
        Attribute = "attribute",
        /// A member of the target is read.
        Member = "member",
        /// The target is read.
        Read = "read",
        /// The target is written.
        Write = "write",
        /// The target is used as a type.
        Type = "type",
        /// The target is used in a source role.
        SourceRole = "source_role",
    }
}

closed! {
    /// The category of a symbol.
    pub enum SymbolCategory {
        /// A module-level variable that is not constant (Dart, AD-796).
        Attribute = "attribute",
        /// A class.
        Class = "class",
        /// A constant.
        Constant = "constant",
        /// A binding that is set at run time.
        DynamicBinding = "dynamic_binding",
        /// A function.
        Function = "function",
        /// A macro.
        Macro = "macro",
        /// A method.
        Method = "method",
        /// A type alias.
        TypeAlias = "type_alias",
    }
}

closed! {
    /// Whether a name is public or private.
    pub enum Visibility {
        /// The name is private.
        Private = "private",
        /// The name is public.
        PublicName = "public_name",
    }
}

closed! {
    /// Why the collector withholds the publication route of an import (#2086, AD-1170).
    pub enum RouteWithheld {
        /// The package body binds the name too, so it may be the attribute or the submodule.
        AmbiguousReexport = "ambiguous_reexport",
        /// A hop is not proven: not one plain statement, two targets or a cycle.
        UncertainHop = "uncertain_hop",
        /// A module on the route has an `__all__` that is not one literal list.
        UnreadAll = "unread_all",
        /// Code outside the scan roots can write to a module on the route.
        OutsideWrite = "outside_write",
        /// A use inside the scan hands the object of a module on the route on.
        Escaped = "escaped",
        /// The import sits under `TYPE_CHECKING` and passes a re-export.
        TypeCheckingReexport = "type_checking_reexport",
    }
}

closed! {
    /// The context of a reference.
    pub enum ReferenceContext {
        /// The reference sits in an annotation.
        Annotation = "annotation",
        /// The reference sits in a value.
        Value = "value",
        /// The context is not known.
        Unknown = "unknown",
    }
}

closed! {
    /// How a class relates to a base declaration.
    pub enum RelationshipKind {
        /// The class inherits from the base.
        Inherits = "inherits",
        /// The class realizes the base.
        Realizes = "realizes",
        /// The class mixes the base in (Dart `with`, AD-796).
        MixesIn = "mixes_in",
    }
}

impl Kind {
    /// The construct named by the record kind, never by a redundant payload field.
    pub fn construct(self) -> Option<&'static str> {
        match self {
            Self::AssertStatement => Some("assert"),
            Self::PlaceholderBody => Some("placeholder_body"),
            Self::BroadExcept => Some("broad_except"),
            Self::SetattrCall => Some("setattr"),
            Self::DelattrCall => Some("delattr"),
            Self::VarsCall => Some("vars"),
            Self::DunderDict => Some("dunder_dict"),
            Self::StringLiteralCompare => Some("string_literal_compare"),
            Self::ConstructSelector => Some("selector"),
            Self::AnyAnnotation => Some("any_annotation"),
            Self::CastCall => Some("cast"),
            Self::GetattrCall => Some("getattr"),
            Self::HasattrCall => Some("hasattr"),
            Self::EvalCall => Some("eval"),
            Self::ExecCall => Some("exec"),
            Self::DynamicImport => Some("dynamic_import"),
            Self::TypeIgnore => Some("type_ignore"),
            _ => None,
        }
    }
}

closed! {
    /// The members that a member inventory lists (`facts.MemberKind`).
    pub enum MemberKind {
        /// The members are attributes.
        Attribute = "attribute",
        /// The members are methods.
        Method = "method",
    }
}

closed! {
    /// Whether a member inventory lists every member (`facts.InventoryStatus`).
    pub enum InventoryStatus {
        /// The inventory lists every member.
        Complete = "complete",
        /// The inventory may miss members.
        Partial = "partial",
    }
}

impl Signal {
    /// The contract construct observed by this signal, if it observes one.
    pub fn construct(self) -> Option<&'static str> {
        Kind::parse(self.as_str()).and_then(Kind::construct)
    }
}

#[cfg(test)]
#[path = "vocab_tests.rs"]
mod tests;
