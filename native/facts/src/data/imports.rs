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
        [read required] symbol: Option<String>,
        [read required] binding: Option<String>,
        [read] symbols_known: bool,
        [wire skip] specifier: Option<String>,
        [wire skip] type_only: Option<bool>,
        [read] relative_level: i64,
        [read] under_type_checking: bool,
        [read] reexport: bool,
        [read] module_level_import: bool,
        [read skip] reexport_chain: Option<Vec<String>>,
        [read skip] declared_in_all: Option<bool>,
        [read skip] ordinary_module: Option<bool>,
        [read skip] origin_binding_unique: Option<bool>,
        [read skip] origin_definition: Nullable<String>,
        [read skip] origin_member_binding_static: Option<bool>,
        [read skip] reexport_candidate: Option<bool>,
        [read skip] script_global: Option<String>,
        [read skip] script_member: Nullable<String>,
        [read skip] source_binding_unique: Option<bool>,
        [read skip] source_member_binding_static: Option<bool>,
        [read skip] symbol_visibility: Nullable<Visibility>,
    }
}

facts_data! {
    /// An UNKNOWN gap of the coverage or of the `unknowns` section.
    pub struct GapData {
        [wire never] code: Option<ReasonCode>,
        [read skip] reason: Option<String>,
        [read skip] module: Option<ModuleName>,
        [read skip] resolution_dimension: Option<ResolutionDimension>,
        [read skip] annotation: Option<String>,
        [read skip] attribute: Option<String>,
        [read skip] file: Option<String>,
        [read skip] function: Option<String>,
        [read skip] line: Option<i64>,
        [read skip] message: Option<String>,
        [read skip] parameter: Option<String>,
        [read skip] path: Option<String>,
        [read skip] source_module: Option<ModuleName>,
        [read skip] under_type_checking: Option<bool>,
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
