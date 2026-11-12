// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed inputs and records at the declaration seam. This is not the reply protocol (AD-390).

use crate::syntax::{DefinitionKind, Modifier, Span, Syntax, Visibility};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use serde::Serialize;

macro_rules! words {
    ($vis:vis $name:ident { $($variant:ident => $word:literal),+ $(,)? }) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
        $vis enum $name { $(#[serde(rename = $word)] $variant),+ }
    };
}

words!(pub(crate) Kind { Class => "class", Function => "function", Method => "method",
    Alias => "alias", Attribute => "attribute", Constant => "constant" });
words!(pub(crate) ClassKind { Class => "class", Protocol => "protocol", Mixin => "mixin", Enum => "enum" });
words!(pub(crate) ParameterKind { Positional => "positional", KeywordOnly => "keyword_only" });
words!(pub(crate) InventoryKind { Attribute => "attribute", Method => "method" });
words!(pub(crate) Category { Class => "class", Function => "function", Method => "method",
    TypeAlias => "type_alias", Attribute => "attribute", Constant => "constant" });

impl Kind {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Class => "class",
            Self::Function => "function",
            Self::Method => "method",
            Self::Alias => "alias",
            Self::Attribute => "attribute",
            Self::Constant => "constant",
        }
    }
}

#[derive(Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Input {
    pub(crate) files: Vec<File>,
}

#[derive(Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct File {
    pub(crate) rel: String,
    pub(crate) module: String,
    pub(crate) source_len: usize,
    pub(crate) first_line: Option<String>,
    pub(crate) syntax: Syntax,
    pub(crate) constructors: Vec<Constructor>,
}

#[derive(Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Constructor {
    pub(crate) start: usize,
    pub(crate) parameters: Vec<ResolvedParameter>,
    pub(crate) problems: Vec<Problem>,
}

#[derive(Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResolvedParameter {
    pub(crate) name: String,
    pub(crate) annotation: Option<String>,
    pub(crate) kind: crate::syntax::ParameterKind,
    pub(crate) default: Option<String>,
    pub(crate) default_known: bool,
    pub(crate) span: Span,
    pub(crate) field_formal: bool,
}

#[derive(Clone, Copy, PartialEq, Eq, Serialize, serde::Deserialize)]
pub(crate) enum ProblemKind {
    #[serde(rename = "UnsupportedParameter")]
    UnsupportedParameter,
    #[serde(rename = "source_resolution_gap")]
    SourceResolutionGap,
}

#[derive(Serialize, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Problem {
    pub(crate) path: String,
    pub(crate) kind: ProblemKind,
    pub(crate) message: String,
    pub(crate) span: Option<Span>,
}

#[derive(Serialize)]
pub(crate) struct Symbol {
    pub(crate) id: FactId,
    pub(crate) evidence_class: archkeel_facts::vocab::EvidenceClass,
    pub(crate) area: archkeel_facts::vocab::Area,
    pub(crate) kind: Kind,
    pub(crate) title: String,
    pub(crate) subjects: Vec<String>,
    pub(crate) evidence_ids: Vec<EvidenceId>,
    pub(crate) fact_ids: [FactId; 0],
    pub(crate) rule_ids: [String; 0],
    pub(crate) provenance: [String; 0],
    pub(crate) data: Data,
}

#[derive(Serialize)]
pub(crate) struct VisibilityDetail {
    pub(crate) kind: Visibility,
    pub(crate) basis: &'static str,
    pub(crate) spelling: String,
}

#[derive(Serialize)]
pub(crate) struct Data {
    pub(crate) qualified_name: String,
    #[serde(flatten)]
    pub(crate) location: Location,
    pub(crate) name: String,
    pub(crate) parent: Option<String>,
    pub(crate) lexical_parent_id: Option<FactId>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) modifiers: Option<Vec<Modifier>>,
    pub(crate) visibility_detail: VisibilityDetail,
    pub(crate) symbol_category: Category,
    pub(crate) source_binding_unique: bool,
    pub(crate) source_member_binding_static: bool,
    pub(crate) class_header_static: bool,
    pub(crate) decorators: Vec<String>,
    pub(crate) signature_complete: bool,
    pub(crate) overload_signature: bool,
    #[serde(flatten)]
    pub(crate) detail: Detail,
}

#[derive(Serialize)]
pub(crate) struct Location {
    pub(crate) module: ModuleName,
    pub(crate) source_file: String,
    pub(crate) package: PackageName,
}

#[derive(Serialize)]
#[serde(untagged)]
pub(crate) enum Detail {
    Class {
        class_kind: ClassKind,
        enum_members: Vec<String>,
        attribute_declarations: Vec<Attribute>,
        member_inventories: Vec<Inventory>,
        #[serde(skip_serializing_if = "Option::is_none")]
        mixin_capable: Option<bool>,
    },
    Callable {
        annotation: Option<String>,
        returns: Option<String>,
        parameters: Vec<Parameter>,
        method_kind: archkeel_facts::vocab::MethodKind,
        signature_decorators_proven: bool,
        #[serde(skip_serializing_if = "Option::is_none")]
        accessor_kind: Option<DefinitionKind>,
    },
    Value {
        annotation: Option<String>,
        constant: Option<String>,
    },
}

#[derive(Serialize)]
pub(crate) struct Parameter {
    pub(crate) name: String,
    pub(crate) annotation: Option<String>,
    pub(crate) kind: ParameterKind,
    pub(crate) default: Option<String>,
    pub(crate) default_known: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) super_formal: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) evidence_ids: Option<Vec<EvidenceId>>,
}

#[derive(Serialize)]
pub(crate) struct Attribute {
    pub(crate) name: String,
    pub(crate) annotation: Option<String>,
    pub(crate) visibility: VisibilityDetail,
    pub(crate) definition_id: FactId,
    pub(crate) evidence_ids: Vec<EvidenceId>,
    pub(crate) r#static: bool,
    pub(crate) constant: Option<String>,
}

#[derive(Serialize)]
pub(crate) struct Inventory {
    pub(crate) schema_version: &'static str,
    pub(crate) kind: InventoryKind,
    pub(crate) status: &'static str,
    pub(crate) definition_ids: Vec<FactId>,
    pub(crate) reason: Option<String>,
}

impl Inventory {
    pub(crate) fn new(kind: InventoryKind, definition_ids: Vec<FactId>) -> Self {
        Self {
            schema_version: "1.0.0",
            kind,
            status: "complete",
            definition_ids,
            reason: None,
        }
    }
}

pub(crate) type Scope = (String, String, String, String, Span, usize, usize);
