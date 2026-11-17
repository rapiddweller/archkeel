// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What kind of file a source file is for the script analysis: one value in place of the three
//! booleans (`module_file`, `declaration_file`, `script_mode`) and the override of `collect._file`.

use crate::source_input::{SourceKind, Suffix};

/// The mode of one file. `module_syntax` (an `import` or an `export`) stays a separate fact: a
/// declaration file can have it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum FileMode {
    /// A declaration file (`.d.ts`): its names belong to the global scope.
    Declaration,
    /// A module: it has module syntax, or its suffix says that the resolver reads a module.
    Module,
    /// A JavaScript global script: its script facts are collected.
    Script,
    /// A global script whose script facts are not collected: a file of a suffix that is no
    /// JavaScript script (a TypeScript file without module syntax, or a file that failed to
    /// parse), or a JavaScript script that a resolver format or a `require` makes a module
    /// (`collect._file`). It is no module for the project scan.
    #[default]
    ClearedScript,
}

impl FileMode {
    /// The mode of a parsed file from its suffix and whether it has module syntax.
    pub(crate) fn of(suffix: Option<Suffix>, module_syntax: bool) -> Self {
        let kind = suffix.and_then(Suffix::source_kind);
        let hinted = suffix.is_some_and(|s| s.format_hint().is_some());
        if kind == Some(SourceKind::Declaration) {
            FileMode::Declaration
        } else if module_syntax || hinted {
            FileMode::Module
        } else if kind == Some(SourceKind::JavaScript) {
            FileMode::Script
        } else {
            FileMode::ClearedScript
        }
    }

    /// The mode of a script file whose script facts the project clears.
    pub(crate) fn cleared(self, cleared: bool) -> Self {
        match self {
            FileMode::Script if cleared => FileMode::ClearedScript,
            other => other,
        }
    }

    /// The file is a declaration file.
    pub(crate) fn is_declaration(self) -> bool {
        self == FileMode::Declaration
    }

    /// The file is a JavaScript global script with collected script facts.
    pub(crate) fn is_script(self) -> bool {
        self == FileMode::Script
    }

    /// The file is a module for the resolver. A declaration file with module syntax is a module
    /// too: the caller adds its `module_syntax`.
    pub(crate) fn is_module(self, module_syntax: bool) -> bool {
        match self {
            FileMode::Module => true,
            FileMode::Declaration => module_syntax,
            FileMode::Script | FileMode::ClearedScript => false,
        }
    }
}

#[cfg(test)]
#[path = "file_mode_tests.rs"]
mod tests;
