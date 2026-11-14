// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scope rules of each source profile: how the core reads a reply of that profile.

use super::Profile;

/// How the modules of a profile lie in the scan roots (`ir/profiles.py`
/// `project_import_closure` and `source_suffix`, `ir/coverage.py` `_package_paths`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layout {
    /// The collector proves the import closure of the project, and the directory of a package
    /// is the parent directory of a file of a direct module (the parent rule).
    ProjectFiles,
    /// The reference engine maps the files of the profile by another rule, or proves no closure.
    Other,
}

/// What the host does with a gap between two modules that the contract allows
/// (`check/pair_gaps.py:66` `drop_allowed_pair_gaps`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PairGapDrop {
    /// The host drops such a gap before the evaluation.
    Allowed,
    /// The host keeps every pair gap.
    Never,
}

/// Whether the collector proves that it sees each local package (AD-496). The reference engine
/// proves a cycle scope only then (`_cycle_scan_coverage`: project import closure, or Python).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CycleScope {
    /// No cycle can close through a package that the reply does not see.
    Proved,
    /// The reply can miss a local package, so a cycle rule has no receipt.
    Unproved,
}

/// How the rules read the target of an import (`evaluate.py` `evaluate_source`, AD-372, AD-450).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TargetMarks {
    /// An external package target matches a dependency by its package, and a builtin target is
    /// no dependency.
    Typed,
    /// Each resolved target matches a dependency by the scope of its target module, as the
    /// reference engine reads a Python import.
    ByModule,
}

impl Profile {
    /// How the rules read the import targets of this profile.
    pub fn target_marks(self) -> TargetMarks {
        match self {
            Profile::TypeScript | Profile::Rust => TargetMarks::Typed,
            Profile::Python | Profile::Dart => TargetMarks::ByModule,
        }
    }

    /// What the host does with an allowed pair gap of this profile.
    pub fn pair_gap_drop(self) -> PairGapDrop {
        match self {
            Profile::Rust => PairGapDrop::Allowed,
            Profile::TypeScript | Profile::Python | Profile::Dart => PairGapDrop::Never,
        }
    }

    /// Whether a cycle rule of this profile can have its receipt. The Dart survey names the package
    /// files and keys that it sees, but it does not prove that it sees each local package.
    pub fn cycle_scope(self) -> CycleScope {
        match self {
            Profile::TypeScript | Profile::Rust | Profile::Python => CycleScope::Proved,
            Profile::Dart => CycleScope::Unproved,
        }
    }

    /// How the modules of this profile lie in the scan roots. A Python module that is not its
    /// path below a scan root is a gap of the survey, so the parent rule holds (AD-450). A Dart
    /// module is the namespace and the path below its scan root (AD-468).
    pub fn layout(self) -> Layout {
        match self {
            Profile::TypeScript | Profile::Rust | Profile::Python | Profile::Dart => {
                Layout::ProjectFiles
            }
        }
    }
}

impl Profile {
    /// Whether the collector of this profile emits nominal construct selectors.
    pub fn construct_selectors(self) -> bool {
        matches!(self, Self::Python)
    }
}
