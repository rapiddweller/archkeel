// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reason codes of an UNKNOWN gap.
//!
//! In protocol 9 the reason of a gap is prose (`data.reason`, the title). The wire cannot carry a
//! code, so `GapData::code` is not on the wire; the read-set writes it. A collector sets the code
//! where it makes the gap. The prose stays as the message of the gap.

closed! {
    /// Why a fact is UNKNOWN. One code covers one cause; the message names the file or the value.
    pub enum ReasonCode {
        /// The parser cannot read a construct of the file.
        SyntaxError = "syntax_error",
        /// The analyzer stopped on the file with an exception (`ExceptionGap`).
        AnalyzerException = "analyzer_exception",
        /// The file cannot be read, or it is over the size limit.
        UnreadableSource = "unreadable_source",
        /// The path of the file gives no module identity.
        NoModuleIdentity = "no_module_identity",
        /// The specifier resolves to no file and no package.
        UnresolvedModule = "unresolved_module",
        /// The specifier is computed, so it cannot be resolved.
        ComputedSpecifier = "computed_specifier",
        /// A setting that decides resolution is not observed.
        UnobservedSetting = "unobserved_setting",
        /// Package metadata that decides resolution is not observed.
        UnobservedPackageMetadata = "unobserved_package_metadata",
        /// The file that the runtime loads is not proven.
        UnprovenRuntimeTarget = "unproven_runtime_target",
        /// A `require` call is shadowed or not proven.
        UnprovenRequire = "unproven_require",
        /// The target is outside the selected source scope, or it is an excluded test source.
        OutsideScope = "outside_scope",
        /// The collector does not examine this kind of dependency, for example script globals.
        NotExamined = "not_examined",
    }
}
