// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The entry points that a manifest declares or the file layout shows (#2040, AD-1140). A
//! projection for the Explorer: it is no section of the reply and never changes a verdict.

use schemars::JsonSchema;
use serde::Serialize;

/// Whether the project states the entry point or the file layout shows it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum EntryBasis {
    /// A manifest key names it.
    Declared,
    /// A file at a fixed path that the language tooling runs.
    Observed,
}

/// The form of an entry point.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum EntryKind {
    /// `[project.scripts]` of `pyproject.toml`.
    PythonScript,
    /// `[project.gui-scripts]` of `pyproject.toml`.
    PythonGuiScript,
    /// A `__main__.py` file: `python -m <package>` runs it.
    PythonMainModule,
    /// A Cargo binary target.
    CargoBin,
    /// The `bin` key of `package.json`.
    PackageBin,
    /// The `main` key of `package.json`.
    PackageMain,
}

/// Where the proof is: a file, and the manifest key when a manifest states it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub struct EntryEvidence {
    /// The path of the manifest or the file, relative to the scan root.
    pub path: String,
    /// The key path in the manifest, for example `project.scripts.tool`; none for a file.
    pub key: Option<String>,
}

/// One entry point with its proof.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub struct EntryPoint {
    /// The form of the entry point.
    pub kind: EntryKind,
    /// Declared or observed.
    pub basis: EntryBasis,
    /// The script, binary or module name.
    pub name: String,
    /// What it runs: `module:function`, a file path, or none when the manifest names none.
    pub target: Option<String>,
    /// The manifest key or the file that proves it.
    pub evidence: EntryEvidence,
}

/// What the scan could read. A language that the scan does not read has no `EntryPoints` at all
/// (unknown). An empty `entries` with an empty `unread` means only: none of the forms above.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, JsonSchema)]
pub struct EntryPoints {
    /// The entry points that the scan proved.
    pub entries: Vec<EntryPoint>,
    /// What the scan could not read, each with its path. A part of the list is then unknown.
    pub unread: Vec<String>,
}
