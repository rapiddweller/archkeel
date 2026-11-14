// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the walk keeps of each file for the script dependencies (`collect._script_dependencies`).

use std::collections::HashSet;

use crate::exports::Named;
use crate::parse::Parsed;
use crate::references::Form;
use crate::script_types::Script;
use crate::source::Span;

/// The facts of one file that the script analysis reads.
#[derive(Default)]
pub(crate) struct ScriptFile {
    pub script: Script,
    /// The file is a global script, and no other fact in the project reads it as a module
    /// (`collect._file` clears a script that a resolver format or a `require` makes a module).
    pub script_mode: bool,
    pub module_file: bool,
    pub declaration_file: bool,
    /// `collect._global_dependency_scope`: a file that can use a browser global.
    pub dependency_scope: bool,
    pub bindings: HashSet<String>,
    pub ambient_globals: Named,
    pub ambient_top_level: Named,
    /// The line and column of each `require` reference: a call at one of them is a loader.
    pub requires: HashSet<(i64, i64)>,
}

impl ScriptFile {
    /// Take the script facts of a parsed file. `cleared` is `collect._file`'s test: the file has a
    /// resolver format, or it uses `require` or `import x = require()`.
    pub(crate) fn take(parsed: &mut Parsed, format_known: bool, dependency_scope: bool) -> Self {
        let uses_loader = parsed
            .references
            .iter()
            .any(|item| matches!(item.form, Form::Require | Form::ImportEquals));
        let cleared = parsed.syntax.script_mode && (format_known || uses_loader);
        let mut script = std::mem::take(&mut parsed.syntax.script);
        if cleared {
            script.direct = None;
            script.globals.clear();
            script.aliases.clear();
        }
        let syntax = &mut parsed.syntax;
        let requires = parsed
            .references
            .iter()
            .filter(|item| item.form == Form::Require)
            .map(|item: &crate::references::Reference| position(&item.span))
            .collect();
        Self {
            script,
            script_mode: syntax.script_mode && !cleared,
            module_file: syntax.module_file,
            declaration_file: syntax.declaration_file,
            dependency_scope,
            bindings: syntax.script_bindings.iter().cloned().collect(),
            ambient_globals: std::mem::take(&mut syntax.ambient_globals),
            ambient_top_level: std::mem::take(&mut syntax.ambient_top_level),
            requires,
        }
    }
}

fn position(span: &Span) -> (i64, i64) {
    (span.line, span.column)
}
