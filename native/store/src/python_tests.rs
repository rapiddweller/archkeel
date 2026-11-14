// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the one validation of the store (AD-450). The planted claims of a real survey are in
// `native/collect/src/python_tests.rs`, which links the collector and the store.

use super::*;

#[test]
fn protocol_10_is_the_python_survey_and_python_has_no_other_protocol() {
    assert_eq!(version(ProtocolVersion::V10, Profile::Python), Ok(()));
    for profile in [Profile::TypeScript, Profile::Rust, Profile::Dart] {
        assert!(version(ProtocolVersion::V10, profile).is_err());
        assert_eq!(version(ProtocolVersion::V8, profile), Ok(()));
    }
    for old in [ProtocolVersion::V8, ProtocolVersion::V9] {
        assert!(version(old, Profile::Python).is_err());
    }
}

#[test]
fn the_first_part_names_the_package() {
    assert_eq!(first_part("os.path"), "os");
    assert_eq!(first_part("app"), "app");
}
