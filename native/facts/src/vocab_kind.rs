// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabulary `Kind`, written as a plain enum (its `impl` blocks are plain items).

/// The kind of a record. The section of the record decides its data type (`sections`).
/// `ExceptionGap` replaces the open kind of protocol 9: there, the kind of an analyzer failure
/// is the name of the exception class (`SyntaxError`). The name is a field of the record.
#[derive(
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Hash,
    serde::Serialize,
    serde::Deserialize,
    schemars::JsonSchema,
)]
pub enum Kind {
    #[serde(rename = "import")]
    Import,
    #[serde(rename = "reexport")]
    Reexport,
    #[serde(rename = "import_type")]
    ImportType,
    #[serde(rename = "import_equals")]
    ImportEquals,
    #[serde(rename = "require")]
    Require,
    #[serde(rename = "dynamic_import")]
    DynamicImport,
    #[serde(rename = "script_global")]
    ScriptGlobal,
    #[serde(rename = "macro_body")]
    MacroBody,
    #[serde(rename = "class")]
    Class,
    #[serde(rename = "function")]
    Function,
    #[serde(rename = "method")]
    Method,
    #[serde(rename = "constant")]
    Constant,
    #[serde(rename = "type_alias")]
    TypeAlias,
    #[serde(rename = "binding")]
    Binding,
    #[serde(rename = "alias")]
    Alias,
    #[serde(rename = "dynamic_binding")]
    DynamicBinding,
    #[serde(rename = "static_constant")]
    StaticConstant,
    #[serde(rename = "macro")]
    Macro,
    #[serde(rename = "calls")]
    Calls,
    #[serde(rename = "call")]
    Call,
    #[serde(rename = "resolved_call")]
    ResolvedCall,
    #[serde(rename = "partially_resolved_call")]
    PartiallyResolvedCall,
    #[serde(rename = "unresolved_call")]
    UnresolvedCall,
    #[serde(rename = "references")]
    References,
    #[serde(rename = "reference")]
    Reference,
    #[serde(rename = "script_namespace_effect")]
    ScriptNamespaceEffect,
    #[serde(rename = "value_reference")]
    ValueReference,
    #[serde(rename = "attribute_reference")]
    AttributeReference,
    #[serde(rename = "source_role")]
    SourceRole,
    #[serde(rename = "bindings")]
    Bindings,
    #[serde(rename = "unused_parameter")]
    UnusedParameter,
    #[serde(rename = "unused_local")]
    UnusedLocal,
    #[serde(rename = "string_literal_compare")]
    StringLiteralCompare,
    #[serde(rename = "broad_except")]
    BroadExcept,
    #[serde(rename = "getattr_call")]
    GetattrCall,
    #[serde(rename = "hasattr_call")]
    HasattrCall,
    #[serde(rename = "setattr_call")]
    SetattrCall,
    #[serde(rename = "delattr_call")]
    DelattrCall,
    #[serde(rename = "vars_call")]
    VarsCall,
    #[serde(rename = "construct_selector")]
    ConstructSelector,
    #[serde(rename = "numeric_operand")]
    NumericOperand,
    #[serde(rename = "any_annotation")]
    AnyAnnotation,
    #[serde(rename = "dict_any_annotation")]
    DictAnyAnnotation,
    #[serde(rename = "callable_any_annotation")]
    CallableAnyAnnotation,
    #[serde(rename = "object_annotation")]
    ObjectAnnotation,
    #[serde(rename = "cast_call")]
    CastCall,
    #[serde(rename = "eval_call")]
    EvalCall,
    #[serde(rename = "exec_call")]
    ExecCall,
    #[serde(rename = "type_ignore")]
    TypeIgnore,
    #[serde(rename = "missing_cross_package_annotation")]
    MissingCrossPackageAnnotation,
    #[serde(rename = "collection_gap")]
    CollectionGap,
    #[serde(rename = "source_resolution_gap")]
    SourceResolutionGap,
    #[serde(rename = "dynamic_import_limit")]
    DynamicImportLimit,
    #[serde(rename = "private_attribute_access_limit")]
    PrivateAttributeAccessLimit,
    #[serde(rename = "exception_gap")]
    ExceptionGap,
    #[serde(rename = "assert_statement")]
    AssertStatement,
    #[serde(rename = "placeholder_body")]
    PlaceholderBody,
    #[serde(rename = "dunder_dict")]
    DunderDict,
}

impl Kind {
    /// Each value, in the order of the declaration.
    pub const ALL: &'static [Self] = &[
        Self::Import,
        Self::Reexport,
        Self::ImportType,
        Self::ImportEquals,
        Self::Require,
        Self::DynamicImport,
        Self::ScriptGlobal,
        Self::MacroBody,
        Self::Class,
        Self::Function,
        Self::Method,
        Self::Constant,
        Self::TypeAlias,
        Self::Binding,
        Self::Alias,
        Self::DynamicBinding,
        Self::StaticConstant,
        Self::Macro,
        Self::Calls,
        Self::Call,
        Self::ResolvedCall,
        Self::PartiallyResolvedCall,
        Self::UnresolvedCall,
        Self::References,
        Self::Reference,
        Self::ScriptNamespaceEffect,
        Self::ValueReference,
        Self::AttributeReference,
        Self::SourceRole,
        Self::Bindings,
        Self::UnusedParameter,
        Self::UnusedLocal,
        Self::StringLiteralCompare,
        Self::BroadExcept,
        Self::GetattrCall,
        Self::HasattrCall,
        Self::SetattrCall,
        Self::DelattrCall,
        Self::VarsCall,
        Self::ConstructSelector,
        Self::NumericOperand,
        Self::AnyAnnotation,
        Self::DictAnyAnnotation,
        Self::CallableAnyAnnotation,
        Self::ObjectAnnotation,
        Self::CastCall,
        Self::EvalCall,
        Self::ExecCall,
        Self::TypeIgnore,
        Self::MissingCrossPackageAnnotation,
        Self::CollectionGap,
        Self::SourceResolutionGap,
        Self::DynamicImportLimit,
        Self::PrivateAttributeAccessLimit,
        Self::ExceptionGap,
        Self::AssertStatement,
        Self::PlaceholderBody,
        Self::DunderDict,
    ];

    /// The JSON text of the value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Import => "import",
            Self::Reexport => "reexport",
            Self::ImportType => "import_type",
            Self::ImportEquals => "import_equals",
            Self::Require => "require",
            Self::DynamicImport => "dynamic_import",
            Self::ScriptGlobal => "script_global",
            Self::MacroBody => "macro_body",
            Self::Class => "class",
            Self::Function => "function",
            Self::Method => "method",
            Self::Constant => "constant",
            Self::TypeAlias => "type_alias",
            Self::Binding => "binding",
            Self::Alias => "alias",
            Self::DynamicBinding => "dynamic_binding",
            Self::StaticConstant => "static_constant",
            Self::Macro => "macro",
            Self::Calls => "calls",
            Self::Call => "call",
            Self::ResolvedCall => "resolved_call",
            Self::PartiallyResolvedCall => "partially_resolved_call",
            Self::UnresolvedCall => "unresolved_call",
            Self::References => "references",
            Self::Reference => "reference",
            Self::ScriptNamespaceEffect => "script_namespace_effect",
            Self::ValueReference => "value_reference",
            Self::AttributeReference => "attribute_reference",
            Self::SourceRole => "source_role",
            Self::Bindings => "bindings",
            Self::UnusedParameter => "unused_parameter",
            Self::UnusedLocal => "unused_local",
            Self::StringLiteralCompare => "string_literal_compare",
            Self::BroadExcept => "broad_except",
            Self::GetattrCall => "getattr_call",
            Self::HasattrCall => "hasattr_call",
            Self::SetattrCall => "setattr_call",
            Self::DelattrCall => "delattr_call",
            Self::VarsCall => "vars_call",
            Self::ConstructSelector => "construct_selector",
            Self::NumericOperand => "numeric_operand",
            Self::AnyAnnotation => "any_annotation",
            Self::DictAnyAnnotation => "dict_any_annotation",
            Self::CallableAnyAnnotation => "callable_any_annotation",
            Self::ObjectAnnotation => "object_annotation",
            Self::CastCall => "cast_call",
            Self::EvalCall => "eval_call",
            Self::ExecCall => "exec_call",
            Self::TypeIgnore => "type_ignore",
            Self::MissingCrossPackageAnnotation => "missing_cross_package_annotation",
            Self::CollectionGap => "collection_gap",
            Self::SourceResolutionGap => "source_resolution_gap",
            Self::DynamicImportLimit => "dynamic_import_limit",
            Self::PrivateAttributeAccessLimit => "private_attribute_access_limit",
            Self::ExceptionGap => "exception_gap",
            Self::AssertStatement => "assert_statement",
            Self::PlaceholderBody => "placeholder_body",
            Self::DunderDict => "dunder_dict",
        }
    }

    /// The value of a JSON text, or `None` when the vocabulary does not hold it.
    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "import" => Some(Self::Import),
            "reexport" => Some(Self::Reexport),
            "import_type" => Some(Self::ImportType),
            "import_equals" => Some(Self::ImportEquals),
            "require" => Some(Self::Require),
            "dynamic_import" => Some(Self::DynamicImport),
            "script_global" => Some(Self::ScriptGlobal),
            "macro_body" => Some(Self::MacroBody),
            "class" => Some(Self::Class),
            "function" => Some(Self::Function),
            "method" => Some(Self::Method),
            "constant" => Some(Self::Constant),
            "type_alias" => Some(Self::TypeAlias),
            "binding" => Some(Self::Binding),
            "alias" => Some(Self::Alias),
            "dynamic_binding" => Some(Self::DynamicBinding),
            "static_constant" => Some(Self::StaticConstant),
            "macro" => Some(Self::Macro),
            "calls" => Some(Self::Calls),
            "call" => Some(Self::Call),
            "resolved_call" => Some(Self::ResolvedCall),
            "partially_resolved_call" => Some(Self::PartiallyResolvedCall),
            "unresolved_call" => Some(Self::UnresolvedCall),
            "references" => Some(Self::References),
            "reference" => Some(Self::Reference),
            "script_namespace_effect" => Some(Self::ScriptNamespaceEffect),
            "value_reference" => Some(Self::ValueReference),
            "attribute_reference" => Some(Self::AttributeReference),
            "source_role" => Some(Self::SourceRole),
            "bindings" => Some(Self::Bindings),
            "unused_parameter" => Some(Self::UnusedParameter),
            "unused_local" => Some(Self::UnusedLocal),
            "string_literal_compare" => Some(Self::StringLiteralCompare),
            "broad_except" => Some(Self::BroadExcept),
            "getattr_call" => Some(Self::GetattrCall),
            "hasattr_call" => Some(Self::HasattrCall),
            "setattr_call" => Some(Self::SetattrCall),
            "delattr_call" => Some(Self::DelattrCall),
            "vars_call" => Some(Self::VarsCall),
            "construct_selector" => Some(Self::ConstructSelector),
            "numeric_operand" => Some(Self::NumericOperand),
            "any_annotation" => Some(Self::AnyAnnotation),
            "dict_any_annotation" => Some(Self::DictAnyAnnotation),
            "callable_any_annotation" => Some(Self::CallableAnyAnnotation),
            "object_annotation" => Some(Self::ObjectAnnotation),
            "cast_call" => Some(Self::CastCall),
            "eval_call" => Some(Self::EvalCall),
            "exec_call" => Some(Self::ExecCall),
            "type_ignore" => Some(Self::TypeIgnore),
            "missing_cross_package_annotation" => Some(Self::MissingCrossPackageAnnotation),
            "collection_gap" => Some(Self::CollectionGap),
            "source_resolution_gap" => Some(Self::SourceResolutionGap),
            "dynamic_import_limit" => Some(Self::DynamicImportLimit),
            "private_attribute_access_limit" => Some(Self::PrivateAttributeAccessLimit),
            "exception_gap" => Some(Self::ExceptionGap),
            "assert_statement" => Some(Self::AssertStatement),
            "placeholder_body" => Some(Self::PlaceholderBody),
            "dunder_dict" => Some(Self::DunderDict),
            _ => None,
        }
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
