// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The provenance documents of a scanned contract tree (AD-466).
//!
//! The core reads each repository path that a contract of the tree cites as provenance, with the
//! same reader as the inside contracts: no link, no path outside the root and no file that is not
//! regular. The frame binds the bytes of each document that it read (`contract_files`), so the
//! shell detects a change after the run as it detects a change of a contract. A path that the
//! core cannot read refuses the run by name (`hygiene`). The documents share the bounds of the
//! inside contracts: 1,024 files and 64 MiB for all nested files together.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_collect::{Over, Scanned};
use archkeel_contract::policy::provenance_paths;

use crate::contract::{ContractInput, InsideFile, Usable, MAX_INSIDE_FILES};

/// The provenance documents of a run.
#[derive(Debug, Default)]
pub(crate) struct Documents {
    /// The bytes of each document that the core read, by the path that the contract writes.
    read: BTreeMap<String, Document>,
    /// Each cited path that the core cannot read: missing, unsafe, linked or not a regular file.
    unread: BTreeSet<String>,
}

/// One document that the core read: its repository-relative path and its bytes.
#[derive(Debug)]
struct Document {
    identity: String,
    bytes: Vec<u8>,
}

impl Documents {
    /// The bytes of the document that a contract cites as `reference`, when the core read it.
    pub(crate) fn bytes(&self, reference: &str) -> Option<&[u8]> {
        self.read
            .get(reference)
            .map(|document| document.bytes.as_slice())
    }

    /// Each cited path that the core cannot read, sorted.
    pub(crate) fn unread(&self) -> &BTreeSet<String> {
        &self.unread
    }

    /// The repository-relative path and the SHA-256 of each document that the core read.
    pub(crate) fn bound(&self) -> impl Iterator<Item = (String, String)> + '_ {
        self.read.values().map(|document| {
            let digest = archkeel_facts::identity::sha256_hex(&document.bytes);
            (document.identity.clone(), digest)
        })
    }

    /// Documents from bytes that a test gives, by path; `None` names a path that is not read.
    #[cfg(test)]
    pub(crate) fn of(files: &[(&str, Option<&str>)]) -> Documents {
        let mut documents = Documents::default();
        for (path, text) in files {
            match text {
                Some(text) => {
                    let document = Document {
                        identity: (*path).to_owned(),
                        bytes: text.as_bytes().to_vec(),
                    };
                    documents.read.insert((*path).to_owned(), document);
                }
                None => {
                    documents.unread.insert((*path).to_owned());
                }
            }
        }
        documents
    }
}

/// Each repository path that a contract of the tree cites as provenance.
pub(crate) fn cited(usable: &Usable) -> BTreeSet<String> {
    let mut paths = provenance_paths(&usable.root);
    for mount in usable.tree.iter().flat_map(|tree| tree.mounts()) {
        paths.extend(provenance_paths(mount.contract()));
    }
    paths
}

/// Read the provenance documents of the scanned tree. The inside contracts already hold a part of
/// the bounds; a tree over a bound is an error (exit 2), as an inside tree over a bound is.
pub(crate) fn read(
    scanned: &Scanned,
    insides: &[InsideFile],
    max_bytes: u64,
) -> Result<Documents, String> {
    let (path, bytes) = &scanned.contract;
    let input = ContractInput {
        path: path.clone(),
        bytes: bytes.clone(),
        insides: insides.to_vec(),
    };
    let mut documents = Documents::default();
    let Some(usable) = crate::contract::answer(input).1 else {
        return Ok(documents);
    };
    let mut total = insides.iter().fold(0u64, |sum, file| {
        sum.saturating_add(file.bytes.len() as u64)
    });
    for reference in cited(&usable) {
        if insides.len().saturating_add(documents.read.len()) >= MAX_INSIDE_FILES {
            return Err(format!(
                "the contract tree cites more than {MAX_INSIDE_FILES} nested files"
            ));
        }
        match scanned.read_inside(&reference, max_bytes.saturating_sub(total)) {
            Ok(Some((identity, bytes))) => {
                total = total.saturating_add(bytes.len() as u64);
                documents
                    .read
                    .insert(reference, Document { identity, bytes });
            }
            Ok(None) => {
                documents.unread.insert(reference);
            }
            Err(Over(_)) => {
                return Err(format!(
                    "the inside contracts and provenance documents hold more than {max_bytes} bytes"
                ))
            }
        }
    }
    Ok(documents)
}
