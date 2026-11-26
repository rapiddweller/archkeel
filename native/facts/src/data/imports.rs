// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the imports section and of the gaps.

use crate::ids::{ModuleName, PackageName};
use crate::nullable::Nullable;
use crate::vocab::Visibility;

/// Why the collector withholds the publication route of an import (#2086, AD-1170).
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, schemars::JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum RouteWithheld {
    /// The import is one of the ambiguous re-exports: the package body binds the name too, so
    /// the name may be the attribute or the submodule.
    AmbiguousReexport,
    /// A hop is not proven: its binding is not one plain statement, it has two targets, or the
    /// route is a cycle. `hop` is the dotted name of the hop.
    UncertainHop {
        /// The dotted name of the hop.
        hop: String,
    },
    /// A module on the route has a surface that the collector cannot read.
    OpaqueSurface {
        /// The module.
        module: String,
        /// Why its surface is not read.
        form: SurfaceForm,
    },
    /// The import sits under `TYPE_CHECKING` and passes a re-export.
    TypeCheckingReexport,
}

/// Why the names that a module publishes are not read.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum SurfaceForm {
    /// `__all__` is not one literal list of strings.
    UnreadAll,
    /// Code outside the scan roots can write to the module.
    OutsideWrite,
    /// A use inside the scan hands the module object on, so a write to it is not excluded.
    Escaped,
}

facts_data! {
    /// An import: one record for each statement or bound name (TypeScript, Rust), or for each
    /// imported name (Python, Dart). `script_global` and `script_member` belong to `script_global`.
    pub struct ImportData {
        /// The module that holds the source.
        [read] source_module: ModuleName,
        /// The package that holds the source module.
        [read] source_package: PackageName,
        /// The module that the import reaches.
        [read] target_module: ModuleName,
        /// The package that the import reaches.
        [read] target_package: PackageName,
        /// The imported name.
        [read required] symbol: Option<String>,
        /// The name that the import binds.
        [read required] binding: Option<String>,
        /// True when the collector reads the imported names.
        [read] symbols_known: bool,
        /// The text of the import as written.
        [wire skip] specifier: Option<String>,
        /// True for an import that only types use.
        [wire skip] type_only: Option<bool>,
        /// The number of leading dots of a relative import.
        [read] relative_level: i64,
        /// True when the import sits under `TYPE_CHECKING`.
        [read] under_type_checking: bool,
        /// True when the import publishes the name again.
        [read] reexport: bool,
        /// True when the import sits at module level.
        [read] module_level_import: bool,
        /// The names whose route the collector records.
        [read skip] reexport_chain: Option<Vec<String>>,
        /// Why the collector withholds the publication route of this import. Absent: it states
        /// no cause, or the route is not withheld.
        [live never] route_withheld: Option<RouteWithheld>,
        /// `false` when the collector proves only the first hops of `reexport_chain`: a later
        /// hop may follow (AD-604). Absent: the route is complete, or there is none.
        [read skip] route_complete: Option<bool>,
        /// The name that a re-export publishes outside the package of its module, as a `pub use`
        /// at the root of a library crate does (`*` for a glob; AD-608).
        [read skip] published_as: Option<String>,
        /// True when the import names a module of another crate of the workspace by that crate's
        /// name, as a binary target names its library (AD-622). Absent: the same crate, or a
        /// collector without crates.
        [read skip] other_crate: Option<bool>,
        /// True when a dot call's symbol names its inferred receiver type, not a written path.
        [live never] inferred_receiver: bool,
        /// True when `__all__` lists the name.
        [read skip] declared_in_all: Option<bool>,
        /// True when the target is an ordinary module.
        [read skip] ordinary_module: Option<bool>,
        /// True when one statement binds the name in the origin.
        [read skip] origin_binding_unique: Option<bool>,
        /// The id of the definition at the origin.
        [read skip] origin_definition: Nullable<String>,
        /// True when no statement rebinds the member at the origin.
        [read skip] origin_member_binding_static: Option<bool>,
        /// True when the import can publish the name again.
        [read skip] reexport_candidate: Option<bool>,
        /// The global that a script import binds.
        [read skip] script_global: Option<String>,
        /// The member of the global that a script import reads.
        [read skip] script_member: Nullable<String>,
        /// True when one statement binds the name in the source.
        [read skip] source_binding_unique: Option<bool>,
        /// True when no statement rebinds the member.
        [read skip] source_member_binding_static: Option<bool>,
        /// The visibility of the imported symbol.
        [read skip] symbol_visibility: Nullable<Visibility>,
    }
}

impl ImportData {
    /// The source, provider, declaration and binding of a direct, unique import.
    pub fn direct_symbol_route(&self) -> Option<[&str; 4]> {
        if !self.module_level_import
            || self.under_type_checking
            || !self.symbols_known
            || self.source_binding_unique != Some(true)
        {
            return None;
        }
        Some([
            self.source_module.as_str(),
            self.target_module.as_str(),
            self.symbol.as_deref()?,
            self.binding.as_deref()?,
        ])
    }

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
            route_complete: None,
            route_withheld: None,
            published_as: None,
            other_crate: None,
            inferred_receiver: false,
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
