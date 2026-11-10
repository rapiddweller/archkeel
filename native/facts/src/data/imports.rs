// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the imports section and of the gaps.

use crate::ids::{ModuleName, PackageName};
use crate::nullable::Nullable;
use crate::reason::ReasonCode;
use crate::vocab::{ResolutionDimension, Visibility};

facts_data! {
    /// An import: one record for each statement or bound name (TypeScript, Rust), or for each
    /// imported name (Python, Dart). `script_global` and `script_member` belong to `script_global`.
    pub struct ImportData {
        [read] source_module: ModuleName,
        [read] source_package: PackageName,
        [read] target_module: ModuleName,
        [read] target_package: PackageName,
        [read] symbol: Option<String>,
        [read] binding: Option<String>,
        [wire] symbols_known: bool,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] specifier: Option<String>,
        [wire] #[serde(default, skip_serializing_if = "Option::is_none")] type_only: Option<bool>,
        [read] relative_level: i64,
        [read] under_type_checking: bool,
        [read] reexport: bool,
        [read] module_level_import: bool,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] reexport_chain: Option<Vec<String>>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] declared_in_all: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] ordinary_module: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] origin_binding_unique: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] origin_definition: Nullable<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] origin_member_binding_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] reexport_candidate: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] script_global: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] script_member: Nullable<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_binding_unique: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_member_binding_static: Option<bool>,
        [optional] #[serde(default, skip_serializing_if = "Nullable::is_absent")] symbol_visibility: Nullable<Visibility>,
    }
}

facts_data! {
    /// An UNKNOWN gap of the coverage or of the `unknowns` section.
    pub struct GapData {
        [optional] #[serde(skip)] code: Option<ReasonCode>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] reason: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] module: Option<ModuleName>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] resolution_dimension: Option<ResolutionDimension>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] annotation: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] attribute: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] file: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] function: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] line: Option<i64>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] message: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] parameter: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] path: Option<String>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] source_module: Option<ModuleName>,
        [optional] #[serde(default, skip_serializing_if = "Option::is_none")] under_type_checking: Option<bool>,
    }
}

impl ImportData {
    /// An import with the fields of a statement import (TypeScript, Rust) and empty values. The
    /// fields that only Python and Dart write are absent. A producer sets each statement field.
    pub fn statement() -> Self {
        ImportData {
            source_module: ModuleName::default(),
            source_package: PackageName::default(),
            target_module: ModuleName::default(),
            target_package: PackageName::default(),
            symbol: None,
            binding: None,
            symbols_known: false,
            specifier: Some(String::new()),
            type_only: Some(false),
            relative_level: 0,
            under_type_checking: false,
            reexport: false,
            module_level_import: false,
            reexport_chain: None,
            declared_in_all: None,
            ordinary_module: None,
            origin_binding_unique: None,
            origin_definition: Nullable::Absent,
            origin_member_binding_static: None,
            reexport_candidate: None,
            script_global: None,
            script_member: Nullable::Absent,
            source_binding_unique: None,
            source_member_binding_static: None,
            symbol_visibility: Nullable::Absent,
        }
    }
}
