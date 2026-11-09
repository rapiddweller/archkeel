// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: both collectors. The records must have the shape of the Python `_gap` records.

use super::*;

#[test]
fn a_collection_gap_is_an_unknown_record_of_its_module() {
    let record = gap_record("Bad thing", Some("EVD-1"), "app.core", GapKind::Collection);
    assert_eq!(
        (record.evidence_class, record.kind),
        ("UNKNOWN", "collection_gap")
    );
    assert_eq!(record.subjects, ["app.core"]);
    assert_eq!(record.evidence_ids, ["EVD-1"]);
    assert_eq!(record.data["reason"], "Bad thing");
    assert!(!record.data.contains_key("resolution_dimension"));
    assert!(record.id.starts_with("UNKNOWN-"));
}

#[test]
fn a_resolution_gap_names_its_dimension_and_a_gap_without_a_module_has_no_subject() {
    let record = gap_record("Cannot resolve", None, "", GapKind::Resolution);
    assert_eq!(record.kind, "source_resolution_gap");
    assert_eq!(record.data["resolution_dimension"], "imports");
    assert!(record.subjects.is_empty() && record.evidence_ids.is_empty());
}

#[test]
fn the_identity_follows_the_reason_the_evidence_and_the_module() {
    let base = gap_record("Reason", Some("EVD-1"), "m", GapKind::Collection).id;
    assert_eq!(
        base,
        gap_record("Reason", Some("EVD-1"), "m", GapKind::Resolution).id
    );
    for other in [
        gap_record("Other", Some("EVD-1"), "m", GapKind::Collection),
        gap_record("Reason", Some("EVD-2"), "m", GapKind::Collection),
        gap_record("Reason", Some("EVD-1"), "n", GapKind::Collection),
        gap_record("Reason", None, "m", GapKind::Collection),
    ] {
        assert_ne!(base, other.id);
    }
}

#[test]
fn evidence_has_the_identity_of_its_location() {
    let evidence = evidence_at("a.rs", 3, 4, 5, "let x = 1;");
    assert_eq!(evidence.id, evidence_id("a.rs", 3, 4, 5));
    assert_eq!(
        (evidence.line, evidence.end_line, evidence.column),
        (3, 4, 5)
    );
    assert_eq!(evidence.excerpt, "let x = 1;");
}
