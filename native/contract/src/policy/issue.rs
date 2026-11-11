// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed errors of the tree. An issue is one Python `InsideContractIssue`; the kinds of a
//! source error are the two cases where Rust is stricter than Python (AD-366).

use std::fmt;

use crate::error::ErrorKind;
use crate::policy::reference::identity;

/// Why one declared inside cannot be mounted.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IssueKind {
    /// The reference is not a safe repository path (`unsafe repository path`).
    UnsafePath,
    /// The scope key of the parent is a root label or the key of another mount.
    ParentIdCollision,
    /// The shell sent no bytes for the path. The shell reads the file and asks again.
    Missing,
    /// The path is the root or a mount above it (`reference cycle`).
    Cycle,
    /// An earlier mount reads the same path (`duplicate mount`).
    DuplicateMount,
    /// The bytes are not a valid contract; the kind of the parse error.
    Contract(ErrorKind),
    /// The inside holds declarations that only a root can hold. The mount stays.
    UnsupportedDeclarations,
    /// A scoped ID of the inside is an ID of the tree already.
    DeclarationIdCollision,
    /// Two contracts of the tree declare one module target path.
    DuplicateModuleTarget,
    /// The mount is deeper than `MAX_DEPTH` (stricter than Python, which stops without a verdict).
    TooDeep,
    /// The shell resolved the path to another file: a symbolic link (stricter than Python).
    Linked,
}

impl IssueKind {
    /// The stable name of the kind, as it is serialized.
    pub fn word(&self) -> &'static str {
        match self {
            IssueKind::UnsafePath => "unsafe_path",
            IssueKind::ParentIdCollision => "parent_id_collision",
            IssueKind::Missing => "missing",
            IssueKind::Cycle => "cycle",
            IssueKind::DuplicateMount => "duplicate_mount",
            IssueKind::Contract(ErrorKind::Invalid) => "contract_invalid",
            IssueKind::Contract(ErrorKind::Version) => "contract_version",
            IssueKind::Contract(ErrorKind::Input) => "contract_input",
            IssueKind::Contract(ErrorKind::DuplicateKey) => "contract_duplicate_key",
            IssueKind::UnsupportedDeclarations => "unsupported_declarations",
            IssueKind::DeclarationIdCollision => "declaration_id_collision",
            IssueKind::DuplicateModuleTarget => "duplicate_module_target",
            IssueKind::TooDeep => "too_deep",
            IssueKind::Linked => "linked",
        }
    }
}

impl serde::Serialize for IssueKind {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(self.word())
    }
}

record!(
    pub(crate),
    /// One declared inside that cannot be mounted, at the JSON pointer of its `inside` field.
    TreeIssue {
        kind: IssueKind,
        pointer: String,
        parent_id: String,
        path: String,
        reason: String,
    }
);

impl TreeIssue {
    pub(crate) fn new(kind: IssueKind, at: &Place, reason: impl Into<String>) -> TreeIssue {
        TreeIssue {
            kind,
            pointer: at.pointer.clone(),
            parent_id: at.parent_id.clone(),
            path: at.path.clone(),
            reason: reason.into(),
        }
    }
}

/// The place of one `inside` field: its pointer, the scope key of its component and its text.
pub(crate) struct Place {
    pub(crate) pointer: String,
    pub(crate) parent_id: String,
    pub(crate) path: String,
}

/// Which input of the shell is wrong.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceProblem {
    /// A path is not a safe repository path.
    Unsafe,
    /// Two inputs name one path.
    Duplicate,
    /// No mount reads the bytes of the path. Python never reads such bytes (stricter).
    Unmounted,
}

/// Why no tree exists. A partly assembled tree is never returned.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TreeError {
    /// The root path is not a repository path.
    UnsafeRootPath,
    /// The inputs of the shell, with the sorted paths.
    Source(SourceProblem, Vec<String>),
    /// Each declared inside that cannot be mounted, in the order of Python.
    Issues(Vec<TreeIssue>),
}

impl TreeError {
    /// The repository paths that the shell must still send, when each issue is a missing path.
    /// The shell reads them and calls `assemble_tree` again; any other error gives `None`.
    pub fn missing_paths(&self) -> Option<Vec<String>> {
        let TreeError::Issues(issues) = self else {
            return None;
        };
        let paths: Option<std::collections::BTreeSet<String>> = issues
            .iter()
            .map(|item| {
                (item.kind == IssueKind::Missing)
                    .then(|| identity(&item.path))
                    .flatten()
            })
            .collect();
        paths.map(|found| found.into_iter().collect())
    }
}

impl fmt::Display for TreeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            TreeError::UnsafeRootPath => formatter.write_str("unsafe root contract path"),
            TreeError::Source(problem, paths) => {
                write!(formatter, "{problem:?} inputs: {}", paths.join(", "))
            }
            TreeError::Issues(issues) => {
                let lines: Vec<String> = issues
                    .iter()
                    .map(|item| {
                        format!(
                            "inside {:?} at {}: {}",
                            item.path, item.pointer, item.reason
                        )
                    })
                    .collect();
                formatter.write_str(&lines.join("; "))
            }
        }
    }
}

impl std::error::Error for TreeError {}
