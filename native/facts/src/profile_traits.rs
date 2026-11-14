// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the host and the rules read from the profile of a reply: the layout of its modules, the
//! way it drops a pair gap, the marks of an import target, and the facts of its language.

use crate::envelope::Profile;

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

    /// The language name that a UML target entity gives for a fact of this profile (AD-494).
    pub fn language_name(self) -> &'static str {
        match self {
            Profile::Python => "python",
            Profile::Dart => "dart",
            Profile::TypeScript => "typescript",
            Profile::Rust => "rust",
        }
    }

    /// True when a name of this profile can be a type and a value at the same time, so a UML
    /// target entity of a type kind never matches a value and the other way (AD-512).
    pub fn separates_type_namespace(self) -> bool {
        match self {
            Profile::TypeScript => true,
            Profile::Python | Profile::Dart | Profile::Rust => false,
        }
    }

    /// True when the collector of this profile states the symbol, call and reference facts of
    /// the modules that it reads. For any other profile the symbol part of a UML target is a
    /// named gap: the core never reads a missing section as an empty one (AD-512).
    pub fn symbol_facts(self) -> bool {
        match self {
            Profile::TypeScript => true,
            Profile::Python | Profile::Dart | Profile::Rust => false,
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
