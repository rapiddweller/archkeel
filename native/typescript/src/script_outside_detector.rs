// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The repository guard reads a file outside the scan roots with the write detector of the scan
//! (#1712, AD-788): the same facts that keep a scanned file from a global proof. A direct form (an
//! alias of a window name that leaves, a window name passed on, `eval`, `Function`, a reflective
//! call on a window), an amplifier form in a file with a host entry, and a write with no path
//! withhold every global. A path that the file writes on the global object (also through an
//! alias, a pattern or a `for` target) withholds its first name.

use crate::file_mode::FileMode;
use crate::parse::parse_for;
use crate::script_outside_forms::Found;
use crate::script_types::Script;
use crate::source::Span;
use crate::source_input::Reach;
use crate::syntax::Parsers;

/// The writes that the scan's detector finds in one program of a file outside the scan roots.
/// `rel` names the program for the grammar (a page program is read as JavaScript).
pub(crate) fn detected(parsers: &mut Parsers, rel: &str, program: &[u8]) -> Vec<Found> {
    let parsed = parse_for(parsers, rel, program, Reach::default(), None);
    let script: &Script = &parsed.syntax.script;
    // A top-level binding is a global only in a classic script.
    let top: &[Vec<String>] = if FileMode::is_script(parsed.syntax.mode) {
        &script.top_level_write_paths
    } else {
        &[]
    };
    let first_line = || Span {
        line: 1,
        end_line: 1,
        column: 0,
        excerpt: String::new(),
    };
    let mut found = Vec::new();
    let unknown_path = script.write_paths.iter().chain(top).any(Vec::is_empty);
    let direct = script.blockers.first().map(|(span, _)| span.clone());
    let amplified = script
        .amp_blockers
        .first()
        .filter(|_| script.amplified && script.host_entry)
        .map(|(span, _)| span.clone());
    if let Some(span) = direct.or(amplified) {
        Vec::push(&mut found, Found::global(None, span));
    } else if unknown_path || script.unlabelled_empty {
        Vec::push(&mut found, Found::global(None, first_line()));
    }
    let named = script
        .write_paths
        .iter()
        .chain(top)
        .filter_map(|path| path.first());
    for name in named {
        let span = script
            .writes
            .iter()
            .find(|(written, _)| written.as_deref() == Some(String::as_str(name)))
            .map_or_else(first_line, |(_, span)| span.clone());
        Vec::push(&mut found, Found::global(Some(name.clone()), span));
    }
    for global in &script.globals {
        Vec::push(
            &mut found,
            Found::global(Some(global.name.clone()), global.span.clone()),
        );
    }
    found
}
