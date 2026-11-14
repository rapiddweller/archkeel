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

/// The typed facts of a frozen reply, as a Python survey with its two sections.
fn survey_facts() -> Facts {
    let value = crate::validate::tests::golden("f-typescript-story");
    let mut facts = serde_json::from_value::<archkeel_facts::envelope::Reply>(value)
        .expect("the frozen reply")
        .facts;
    facts.profile = Profile::Python;
    facts.capabilities.resolution_features.clear();
    facts.capabilities.constructs.clear();
    facts.capabilities.sections = ["imports", "unknowns"]
        .into_iter()
        .map(|name| archkeel_facts::envelope::SectionName::parse(name).expect("a section"))
        .collect();
    facts.profile_limits = None;
    facts
}

#[test]
fn the_survey_has_exactly_two_sections_and_no_construct() {
    assert_eq!(registered(&survey_facts()), Ok(()));
    let mut more = survey_facts();
    let symbols = archkeel_facts::envelope::SectionName::parse("symbols").expect("a section");
    more.capabilities.sections.push(symbols);
    assert!(registered(&more)
        .unwrap_err()
        .contains("exactly the import survey"));
    let mut fewer = survey_facts();
    fewer.capabilities.sections.pop();
    assert!(registered(&fewer)
        .unwrap_err()
        .contains("exactly the import survey"));
    let mut construct = survey_facts();
    let golden = crate::validate::tests::golden("f-typescript-story");
    let entry = golden["facts"]["capabilities"]["constructs"].clone();
    construct.capabilities.constructs =
        serde_json::from_value(entry).expect("the construct capabilities of the frozen reply");
    if construct.capabilities.constructs.is_empty() {
        construct.capabilities.constructs = serde_json::from_value(serde_json::json!([
            {"name": "string_literal_compare", "status": "partial"}
        ]))
        .expect("one construct capability");
    }
    assert!(registered(&construct)
        .unwrap_err()
        .contains("exactly the import survey"));
}

#[test]
fn an_interface_statement_is_refused() {
    let mut facts = survey_facts();
    facts.profile_limits = Some(archkeel_facts::envelope::ProfileLimits {
        dependency_symbols: LimitSupport::Unsupported,
        interface_boundary: LimitSupport::Supported,
    });
    assert!(registered(&facts)
        .unwrap_err()
        .contains("no interface rule"));
}
