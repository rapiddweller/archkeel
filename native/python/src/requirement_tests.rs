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
