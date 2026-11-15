// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed vocabulary `Signal`, written as a plain enum (its `impl` blocks are plain items).

use super::kind::Kind;

/// The typing signal of a record of `typing_signals`; the text equals the kind of the record.
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
pub enum Signal {
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
    #[serde(rename = "getattr_call")]
    GetattrCall,
    #[serde(rename = "hasattr_call")]
    HasattrCall,
    #[serde(rename = "eval_call")]
    EvalCall,
    #[serde(rename = "exec_call")]
    ExecCall,
    #[serde(rename = "dynamic_import")]
    DynamicImport,
    #[serde(rename = "type_ignore")]
    TypeIgnore,
    #[serde(rename = "missing_cross_package_annotation")]
    MissingCrossPackageAnnotation,
}

impl Signal {
    /// Each value, in the order of the declaration.
    pub const ALL: &'static [Self] = &[
        Self::AnyAnnotation,
        Self::DictAnyAnnotation,
        Self::CallableAnyAnnotation,
        Self::ObjectAnnotation,
        Self::CastCall,
        Self::GetattrCall,
        Self::HasattrCall,
        Self::EvalCall,
        Self::ExecCall,
        Self::DynamicImport,
        Self::TypeIgnore,
        Self::MissingCrossPackageAnnotation,
    ];

    /// The JSON text of the value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::AnyAnnotation => "any_annotation",
            Self::DictAnyAnnotation => "dict_any_annotation",
            Self::CallableAnyAnnotation => "callable_any_annotation",
            Self::ObjectAnnotation => "object_annotation",
            Self::CastCall => "cast_call",
            Self::GetattrCall => "getattr_call",
            Self::HasattrCall => "hasattr_call",
            Self::EvalCall => "eval_call",
            Self::ExecCall => "exec_call",
            Self::DynamicImport => "dynamic_import",
            Self::TypeIgnore => "type_ignore",
            Self::MissingCrossPackageAnnotation => "missing_cross_package_annotation",
        }
    }

    /// The value of a JSON text, or `None` when the vocabulary does not hold it.
    pub fn parse(text: &str) -> Option<Self> {
        match text {
            "any_annotation" => Some(Self::AnyAnnotation),
            "dict_any_annotation" => Some(Self::DictAnyAnnotation),
            "callable_any_annotation" => Some(Self::CallableAnyAnnotation),
            "object_annotation" => Some(Self::ObjectAnnotation),
            "cast_call" => Some(Self::CastCall),
            "getattr_call" => Some(Self::GetattrCall),
            "hasattr_call" => Some(Self::HasattrCall),
            "eval_call" => Some(Self::EvalCall),
            "exec_call" => Some(Self::ExecCall),
            "dynamic_import" => Some(Self::DynamicImport),
            "type_ignore" => Some(Self::TypeIgnore),
            "missing_cross_package_annotation" => Some(Self::MissingCrossPackageAnnotation),
            _ => None,
        }
    }
}

impl Signal {
    /// The contract construct observed by this signal, if it observes one.
    pub fn construct(self) -> Option<&'static str> {
        Kind::parse(self.as_str()).and_then(Kind::construct)
    }
}
