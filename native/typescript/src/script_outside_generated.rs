// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A generated copy of scanned sources that states its generation (AD-788 amendment). A file
//! outside the scan roots whose last lines state, in this form,
//!
//! ```text
//! // Generated from <source>; source-sha256=<64 lower-case hex digits>
//! // Owner: <generator>. …
//! // Check: <freshness check>
//! ```
//!
//! is the code of its sources when each stated source (relative to the folder of the copy) is a
//! file inside the scan roots whose SHA-256 is the stated digest, and the generator and the check
//! are files of the repository. The writes of the copy are then the writes of its sources, which
//! the scan reads. A copy that was changed after its generation is the open part: the stated check
//! finds it, and the printed premise names it. A copy whose statement does not hold is read as any
//! other file.

use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::paths::{dirname, join, within};
use archkeel_snapshot::Snapshot;

/// The lines at the end of a copy that hold the statement.
const TAIL_LINES: usize = 8;

/// The copy states its generation from scanned sources, and the statement holds.
pub(crate) fn stated_copy(
    snapshot: &mut Snapshot,
    rel: &str,
    data: &[u8],
    roots: &[String],
) -> bool {
    let text = String::from_utf8_lossy(data);
    let tail: Vec<&str> = text.lines().rev().take(TAIL_LINES).collect();
    let field = |prefix: &str| -> Vec<String> {
        tail.iter()
            .filter_map(|line| line.trim().strip_prefix(prefix))
            .map(str::to_owned)
            .collect()
    };
    let sources = field("// Generated from ");
    let owner = field("// Owner: ");
    let check = field("// Check: ");
    let ([owner], [check]) = (owner.as_slice(), check.as_slice()) else {
        return false;
    };
    let tools_exist = snapshot.is_file(&first_word(owner)) && snapshot.is_file(&first_word(check));
    let folder = dirname(rel).trim_end_matches('/').to_owned();
    let sources_hold = !Vec::is_empty(&sources)
        && sources.iter().all(|line| {
            let Some((source, digest)) = line.split_once("; source-sha256=") else {
                return false;
            };
            let source = join(
                if str::is_empty(&folder) { "." } else { &folder },
                source.trim(),
            );
            let scanned = roots.iter().any(|root| within(root, &source));
            scanned
                && snapshot
                    .read(&source)
                    .is_some_and(|bytes| sha256_hex(&bytes) == digest.trim())
        });
    tools_exist && sources_hold
}

/// The path at the start of a statement: up to the first space, without a final full stop.
fn first_word(stated: &str) -> String {
    let word = stated.split_whitespace().next().unwrap_or_default();
    word.trim_end_matches(['.', ';']).to_owned()
}

#[cfg(test)]
#[path = "script_outside_generated_tests.rs"]
mod tests;
