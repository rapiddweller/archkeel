// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed resolver answers and raw assembly records; no resolver executes here (AD-400).

use crate::declarations::types::{File, Symbol};
use crate::syntax::{Site, Span};
pub(crate) use archkeel_facts::data::ImportData;
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

crate::syntax::value! { pub(crate) Problem {
    path: String, kind: ExceptionName, message: String, span: Option<Span>,
}
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

crate::syntax::value! { pub(crate) DirectiveTarget {
    module: String, package: String, rel_path: Option<String>, uri: String, builtin: bool,
}
}

crate::syntax::value! { pub(crate) DirectiveAnswer {
    rel: String, start: usize, targets: Vec<DirectiveTarget>,
}
}

crate::syntax::value! { pub(crate) NameAnswer {
    rel: String, name: String, targets: Vec<String>,
}
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Resolution {
    Resolved,
    Unknown,
    Unresolved,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
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

crate::syntax::value! { pub(crate) Binding {
    module: String, name: String, kind: BindingKind, via_prefix: Option<String>,
    declaration_id: String, rel_path: String, span: Span, visibility: crate::syntax::Visibility,
}
}

crate::syntax::value! { pub(crate) ResolvedSite {
    site: Site, status: Resolution, bindings: Vec<Binding>,
}
}

crate::syntax::value! { pub(crate) SitesAnswer {
    rel: String, sites: Vec<ResolvedSite>,
}
}

crate::syntax::value! { pub(crate) Construction {
    status: Resolution, binding: Option<Binding>, reason: Option<String>,
}
}

crate::syntax::value! { pub(crate) ConstructionAnswer {
    rel: String, start: usize, expression: String, resolution: Construction,
}
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
