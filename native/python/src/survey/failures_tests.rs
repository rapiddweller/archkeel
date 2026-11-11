// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_failure_has_the_id_and_the_title_of_parse_sources() {
    let found = failure(
        "src/a.py",
        &Failure {
            exception: ExceptionName::SyntaxError,
            line: 3,
            message: "bad".to_owned(),
        },
    );
    assert_eq!(found.id.as_str(), "COVERAGE-1c5381d86d27013d");
    assert_eq!(found.title, "src/a.py:3 could not be analyzed");
    assert_eq!(found.subjects, ["src/a.py"]);
    assert_eq!(found.evidence_class, EvidenceClass::Unknown);
}

#[test]
fn an_unseen_file_is_a_collection_gap_that_names_it() {
    let found = unseen("src/big.py", "Source file over the size limit: src/big.py");
    assert!(matches!(&found.data, GapFact::CollectionGap(data)
        if data.file.as_deref() == Some("src/big.py")));
    assert_eq!(found.subjects, ["src/big.py"]);
}
