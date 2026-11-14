// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: an unread or mismatched runtime requirement holds the run (`proof.rs`), so only a
// requirement whose every clause the core reads can give a satisfied runtime (AD-472).

use super::*;

fn checked(required: Option<&str>, version: &str) -> Runtime {
    runtime(&RuntimeFact {
        name: "collector".to_owned(),
        required: required.map(str::to_owned),
        requirement_state: RequirementState::Declared,
        version: version.to_owned(),
    })
}

#[test]
fn each_clause_of_a_read_requirement_must_hold() {
    assert_eq!(checked(Some(">=3.11"), "3.14.0"), Runtime::Satisfied);
    assert_eq!(checked(Some(">=3.9,<4.0"), "3.14.0"), Runtime::Satisfied);
    assert_eq!(
        checked(Some(" >=3.9 , <4.0 "), "3.14.0"),
        Runtime::Satisfied
    );
    assert_eq!(checked(Some(">=3.15"), "3.14.0"), Runtime::Mismatch);
    assert_eq!(checked(Some(">=3.9,<3.14"), "3.14.0"), Runtime::Mismatch);
    assert_eq!(checked(None, "3.14.0"), Runtime::Mismatch);
}

#[test]
fn a_clause_that_the_core_does_not_read_gives_an_unread_runtime() {
    for required in [
        "<=4.0",
        ">=3.9,!=3.10",
        "~=3.9",
        "==3.14",
        ">3.9",
        ">=3.9,<4.0a1",
    ] {
        assert_eq!(
            checked(Some(required), "3.14.0"),
            Runtime::Unread,
            "{required}"
        );
    }
    assert_eq!(checked(Some(">=3.9"), "3.14.0rc1"), Runtime::Unread);
}
