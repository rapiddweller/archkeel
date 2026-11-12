// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The semantic check of a payload: what JSON Schema cannot say (AD-361, AD-371).
//!
//! It has every rule of the oracle checker (`archkeel.report.payload.checker`): equal column
//! lengths, ids in range, the sorted string table, the offsets, the node tree, the measure
//! verdicts, the gap list, the counts, the status rule, the rows that explain a status and the
//! violation count of each rule. It adds rules that the oracle checker does not have: a code
//! beyond the lists of this crate, the row order of each table, the flags, the permissions
//! against the component edges, a PASS rule without its receipt, a `run` row with a Target, and
//! the counts that follow from the rows. As in the oracle checker, a structure problem stops the
//! check before the row rules, because the row rules read ids.

use crate::payload::Payload;
use crate::problem::Problem;

/// Every problem of the payload; empty when the payload is sound.
pub(crate) fn problems(payload: &Payload) -> Vec<Problem> {
    let mut found = Vec::new();
    if !schema_version_ok(&payload.schema_version) {
        found.push(Problem::SchemaVersion);
    }
    crate::check_structure::structure(payload, &mut found);
    if found.is_empty() {
        crate::check_rows::rows(payload, &mut found);
        crate::check_order::order(payload, &mut found);
    }
    found
}

fn schema_version_ok(version: &str) -> bool {
    let mut parts = version.split('.');
    let numeric = |part: Option<&str>| {
        part.is_some_and(|text| !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit()))
    };
    parts.next() == Some("2")
        && numeric(parts.next())
        && numeric(parts.next())
        && parts.next().is_none()
}
