// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed resolver answers and raw assembly records; no resolver executes here (AD-400).

use crate::declarations::types::{File, Symbol};
use crate::syntax::{Site, Span};
use archkeel_facts::envelope::{Capabilities, Dirty, Evidence, FileFact, Input as Digest, Target};
use archkeel_facts::ids::EvidenceId;
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::{ExceptionName, Status};
use archkeel_facts::Record;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Input {
    pub(crate) files: Vec<Source>,
    pub(crate) package_name: String,
    pub(crate) sdk_state: crate::pubspec::SdkState,
    pub(crate) sdk: Option<String>,
    pub(crate) roots: Vec<String>,
    pub(crate) inputs: Vec<Digest>,
    pub(crate) problems: Vec<Problem>,
    pub(crate) resolver: Answers,
    pub(crate) git_head: String,
    pub(crate) dirty: Dirty,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Source {
    pub(crate) file: File,
    pub(crate) content: String,
    pub(crate) owner: Option<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Problem {
    pub(crate) path: String,
    pub(crate) kind: ExceptionName,
    pub(crate) message: String,
    pub(crate) span: Option<Span>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Answers {
    pub(crate) directives: Vec<DirectiveAnswer>,
    pub(crate) names: Vec<NameAnswer>,
    pub(crate) sites: Vec<SitesAnswer>,
    pub(crate) constructions: Vec<ConstructionAnswer>,
    pub(crate) problems: Vec<Problem>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct DirectiveTarget {
    pub(crate) module: String,
    pub(crate) package: String,
    pub(crate) rel_path: Option<String>,
    pub(crate) uri: String,
    pub(crate) builtin: bool,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct DirectiveAnswer {
    pub(crate) rel: String,
    pub(crate) start: usize,
    pub(crate) targets: Vec<DirectiveTarget>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct NameAnswer {
    pub(crate) rel: String,
    pub(crate) name: String,
    pub(crate) targets: Vec<String>,
}

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Resolution {
    Resolved,
    Unknown,
    Unresolved,
}

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum BindingKind {
    Class,
    Interface,
    Mixin,
    Enum,
    Extension,
    ExtensionType,
    Typedef,
    Function,
    Getter,
    Setter,
    Variable,
    Field,
    Method,
    Constructor,
    Operator,
    Binding,
    EnumMember,
    ImplicitConstructor,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Binding {
    pub(crate) module: String,
    pub(crate) name: String,
    pub(crate) kind: BindingKind,
    pub(crate) via_prefix: Option<String>,
    pub(crate) declaration_id: String,
    pub(crate) rel_path: String,
    pub(crate) span: Span,
    pub(crate) visibility: crate::syntax::Visibility,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResolvedSite {
    pub(crate) site: Site,
    pub(crate) status: Resolution,
    pub(crate) bindings: Vec<Binding>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SitesAnswer {
    pub(crate) rel: String,
    pub(crate) sites: Vec<ResolvedSite>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Construction {
    pub(crate) status: Resolution,
    pub(crate) binding: Option<Binding>,
    pub(crate) reason: Option<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ConstructionAnswer {
    pub(crate) rel: String,
    pub(crate) start: usize,
    pub(crate) expression: String,
    pub(crate) resolution: Construction,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum RecordKind {
    Import,
    Call,
    Reference,
}

pub(crate) type Fact<T> = Symbol<T, RecordKind>;

#[derive(Serialize)]
pub(crate) struct ImportData {
    pub(crate) source_module: String,
    pub(crate) source_package: String,
    pub(crate) target_module: String,
    pub(crate) target_package: String,
    pub(crate) symbol: Option<String>,
    pub(crate) binding: Option<String>,
    pub(crate) symbols_known: bool,
    pub(crate) relative_level: usize,
    pub(crate) under_type_checking: bool,
    pub(crate) ordinary_module: bool,
    pub(crate) module_level_import: bool,
    pub(crate) reexport: bool,
    pub(crate) reexport_chain: Vec<String>,
    pub(crate) origin_definition: Option<String>,
    pub(crate) symbol_visibility: Option<archkeel_facts::vocab::Visibility>,
}

#[derive(Serialize)]
pub(crate) struct SiteData {
    pub(crate) source_scope: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) source_definition_id: Option<String>,
    pub(crate) source_module: String,
    pub(crate) source_file: String,
    pub(crate) expression: String,
    pub(crate) status: Status,
    pub(crate) targets: Vec<String>,
    pub(crate) candidate_count: usize,
    pub(crate) candidates_truncated: bool,
    pub(crate) reason: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) r#use: Option<crate::syntax::SiteUse>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) construction: Option<ConstructionData>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(crate) result_bindings: Vec<ResultBinding>,
}

#[derive(Serialize)]
pub(crate) struct ConstructionData {
    pub(crate) status: Status,
    pub(crate) targets: Vec<String>,
    pub(crate) candidates_truncated: bool,
    pub(crate) reason: String,
}

#[derive(Serialize)]
pub(crate) struct ResultBinding {
    pub(crate) id: String,
    pub(crate) name: String,
    pub(crate) target_kind: &'static str,
    pub(crate) annotation: Option<String>,
    pub(crate) initializer: String,
    pub(crate) evidence_ids: Vec<EvidenceId>,
    pub(crate) definition_contexts: [String; 0],
}

#[derive(Default, Serialize)]
pub(crate) struct Output {
    pub(crate) full_scope: bool,
    pub(crate) selected_files: Vec<String>,
    pub(crate) files_read: usize,
    pub(crate) files_parsed: usize,
    pub(crate) inputs: Vec<Digest>,
    pub(crate) source_digest: String,
    pub(crate) scope: Vec<String>,
    pub(crate) git_head: String,
    pub(crate) dirty: Option<Dirty>,
    pub(crate) capabilities: Option<Capabilities>,
    pub(crate) files: Vec<FileFact>,
    pub(crate) symbols: Vec<Symbol>,
    pub(crate) imports: Vec<Fact<ImportData>>,
    pub(crate) calls: Vec<Fact<SiteData>>,
    pub(crate) references: Vec<Fact<SiteData>>,
    pub(crate) bindings: [String; 0],
    pub(crate) targets: Vec<Target>,
    pub(crate) gaps: Vec<Record<GapFact>>,
    pub(crate) evidence: Vec<Evidence>,
    pub(crate) work: usize,
}
