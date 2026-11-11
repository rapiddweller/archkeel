// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_snapshot::test_tree::Tree;

use super::*;

fn state(text: &str) -> (Option<String>, RequirementState) {
    let tree = Tree::new(&[("pyproject.toml", text)]);
    requirement(&mut Snapshot::new(&tree.path()))
}

#[test]
fn the_requirement_follows_project_then_poetry() {
    let declared = state("[project]\nrequires-python = \">=3.11\"\n");
    assert_eq!(
        declared,
        (Some(">=3.11".to_owned()), RequirementState::Declared)
    );
    let caret = state("[tool.poetry.dependencies]\npython = \"^3.11\"\n");
    assert_eq!(caret.0.as_deref(), Some(">=3.11,<4.0"));
    assert_eq!(
        state("[tool.poetry]\nname = \"x\"\n").1,
        RequirementState::RequirementMissing
    );
    assert_eq!(
        state("[project]\nrequires-python = 3\n").1,
        RequirementState::RequirementInvalid
    );
    assert_eq!(state("[project\n").1, RequirementState::MetadataInvalid);
    let missing = requirement(&mut Snapshot::new(&Tree::new(&[("a.py", "")]).path()));
    assert_eq!(missing.1, RequirementState::MetadataMissing);
}

#[test]
fn only_a_plain_caret_is_written_out() {
    assert_eq!(normalize_caret(" ^3.11.2 "), ">=3.11.2,<4.0");
    assert_eq!(normalize_caret("^03.1"), "^03.1");
    assert_eq!(normalize_caret("^3.1.2.4"), "^3.1.2.4");
    assert_eq!(normalize_caret(">=3.11"), ">=3.11");
}

/// `tomllib` of CPython 3.11 to 3.14 refuses each of these datetimes.
#[test]
fn a_datetime_that_tomllib_refuses_is_invalid() {
    for text in [
        "d = 1990-12-31T23:59:60Z",
        "d = 1990-12-31T23:59:60",
        "d = 23:59:60",
        "d = 2023-02-29",
        "d = 2024-02-30",
        "d = 2024-04-31",
        "d = 1990-12-31T24:00:00Z",
        "d = 1990-12-31T23:60:00Z",
        "d = 2024-13-01",
        "d = 2024-01-00",
        "d = 0000-01-01",
        "d = 1990-12-31T23:59:59+24:00",
        "d = 1990-12-31T23:59:59+01:60",
        "d = 1990-12-31T23:59Z",
        "d = 23:59",
        "d = 10000-01-01",
        "d = 23:59:59Z",
        "[x]\nd = [{e = 1990-12-31T23:59:60Z}]",
    ] {
        assert_eq!(state(text).1, RequirementState::MetadataInvalid, "{text}");
    }
    for text in [
        "d = 2024-02-29",
        "d = 2000-02-29",
        "d = 1990-12-31T23:59:59+23:59",
        "d = 1990-12-31T23:59:59.999999999Z",
        "d = 23:59:59.1234567",
        "d = 1990-12-31 23:59:59Z",
        "d = 1990-12-31t23:59:59z",
        "d = 1990-12-31T23:59:59-00:00",
    ] {
        assert_eq!(
            state(text).1,
            RequirementState::RequirementMissing,
            "{text}"
        );
    }
}
