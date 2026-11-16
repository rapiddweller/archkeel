// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Reading the selected files of a scan: decode, parse and name each module, and a record for each
//! file that does not read, is shadowed or is unseen.

use std::collections::HashSet;

use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::{GapFact, Record};
use archkeel_snapshot::Snapshot;

use super::failures::{self, early, NOT_FOUND};
use crate::discover::{self, Unseen};
use crate::module::Module;
use crate::names;
use crate::parse::{parse, ParseFailure as Failure};
use crate::source::{decode, newlines};

pub(super) struct Parsed {
    pub(super) modules: Vec<Module>,
    /// The failures in the order of the selection, the shadowed modules and the unseen files.
    pub(super) gaps: Vec<Record<GapFact>>,
    pub(super) files_read: u64,
}

/// `parse_unshadowed`: the modules of the selected files that the import system can reach and
/// that read, decode, parse and have a module name; a record for each other file.
pub(super) fn parse_unshadowed(
    snapshot: &mut Snapshot,
    scope: &discover::Scope,
    namespace: &str,
    minor: PyMinor,
) -> Parsed {
    let shadowed = names::shadowed(&scope.selected, namespace, minor);
    let skipped: HashSet<&str> = shadowed.iter().map(|item| item.file.as_str()).collect();
    let mut parsed = Parsed {
        modules: Vec::new(),
        gaps: Vec::new(),
        files_read: 0,
    };
    let mut unseen: Vec<Unseen> = scope
        .unseen
        .iter()
        .filter(|item| !matches!(item, Unseen::Missing(_)))
        .cloned()
        .collect();
    for rel in scope
        .selected
        .iter()
        .filter(|rel| !skipped.contains(rel.as_str()))
    {
        let Some(raw) = snapshot.read(rel) else {
            match unread(snapshot, rel) {
                Ok(failure) => parsed.gaps.push(failures::failure(rel, &failure)),
                Err(item) => unseen.push(item),
            }
            continue;
        };
        parsed.files_read += 1;
        match parsed_module(rel, &raw, namespace, minor) {
            Ok(module) => parsed.modules.push(module),
            Err(failure) => parsed.gaps.push(failures::failure(rel, &failure)),
        }
    }
    parsed.gaps.extend(shadowed.iter().map(failures::shadowed));
    for item in &unseen {
        let (Unseen::NotUtf8(rel)
        | Unseen::Oversized(rel)
        | Unseen::Missing(rel)
        | Unseen::Special(rel)) = item;
        let reason = item
            .reason(snapshot)
            .unwrap_or_else(|| format!("Source unseen: {rel}"));
        parsed.gaps.push(failures::unseen(rel, &reason));
    }
    parsed
}

/// Why a selected file did not read: the failure of Python, or a file that the native
/// collector does not see (over the size limit, AD-367 point 4).
fn unread(snapshot: &mut Snapshot, rel: &str) -> Result<Failure, Unseen> {
    if snapshot.size_gap(rel).is_some() {
        return Err(Unseen::Oversized(rel.to_owned()));
    }
    if snapshot.is_dir(rel) {
        return Ok(early(ExceptionName::IsADirectoryError, "Is a directory"));
    }
    if snapshot.real(rel).is_none() {
        return Ok(early(ExceptionName::FileNotFoundError, NOT_FOUND));
    }
    Ok(early(
        ExceptionName::OsError,
        "the native collector cannot read the file",
    ))
}

/// Decode, parse and name one file, in the order of `parse_sources`.
fn parsed_module(
    rel: &str,
    raw: &[u8],
    namespace: &str,
    minor: PyMinor,
) -> Result<Module, Failure> {
    crate::source::declared_encoding(raw).map_err(|name| {
        let message = format!("source_encoding: the file declares the encoding {name}");
        early(ExceptionName::SyntaxError, &message)
    })?;
    let decode_error = || early(ExceptionName::UnicodeDecodeError, "UnicodeDecodeError");
    let text = newlines(decode(raw).ok_or_else(decode_error)?);
    let tree = parse(&text, minor)?;
    let name = names::module_for(rel, namespace, minor)
        .ok_or_else(|| early(ExceptionName::ValueError, "ValueError"))?;
    Ok(Module::new(rel.to_owned(), name, text.into_owned(), tree))
}
