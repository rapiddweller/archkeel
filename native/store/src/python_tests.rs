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

/// The typed facts of a frozen reply, as a Python survey with its three sections (AD-518).
fn survey_facts() -> Facts {
    survey_of(
        Profile::Python,
        &["calls", "imports", "references", "symbols", "unknowns"],
    )
}

fn survey_of(profile: Profile, sections: &[&str]) -> Facts {
    let value = crate::validate::tests::golden("f-typescript-story");
    let mut facts = serde_json::from_value::<archkeel_facts::envelope::Reply>(value)
        .expect("the frozen reply")
        .facts;
    facts.profile = profile;
    facts.capabilities.resolution_features.clear();
    facts.capabilities.constructs.clear();
    facts.capabilities.sections = sections
        .iter()
        .map(|name| archkeel_facts::envelope::SectionName::parse(name).expect("a section"))
        .collect();
    facts.profile_limits = None;
    facts
}

#[test]
fn the_survey_has_exactly_its_sections_and_no_construct() {
    assert_eq!(registered(&survey_facts()), Ok(()));
    // Dart states no symbols; Python states no site section (AD-518).
    let dart = survey_of(Profile::Dart, &["imports", "unknowns"]);
    assert_eq!(registered(&dart), Ok(()));
    let with_symbols = survey_of(Profile::Dart, &["imports", "symbols", "unknowns"]);
    assert!(registered(&with_symbols).is_err());
    let mut more = survey_facts();
    let calls = archkeel_facts::envelope::SectionName::parse("bindings").expect("a section");
    more.capabilities.sections.push(calls);
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
fn python_accepts_only_the_registered_assert_capability_with_its_section() {
    let mut facts = survey_facts();
    facts
        .capabilities
        .sections
        .push(archkeel_facts::envelope::SectionName::parse("constructs").expect("a section"));
    facts.capabilities.constructs = vec![archkeel_facts::envelope::ConstructCapability {
        name: "assert".to_owned(),
        status: ConstructSupport::Supported,
    }];
    assert_eq!(registered(&facts), Ok(()));
    facts.capabilities.constructs[0].name = "broad_except".to_owned();
    assert!(registered(&facts).is_err());
    facts.capabilities.constructs[0].name = "assert".to_owned();
    facts.capabilities.constructs[0].status = ConstructSupport::Partial;
    assert!(registered(&facts).is_err());
    facts.capabilities.constructs[0].status = ConstructSupport::Supported;
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "broad_except".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert_eq!(registered(&facts), Ok(()));
    facts.capabilities.constructs[1].status = ConstructSupport::Supported;
    assert_eq!(registered(&facts), Ok(()));
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "dunder_dict".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert_eq!(registered(&facts), Ok(()));
    facts.capabilities.constructs[2].status = ConstructSupport::Supported;
    assert_eq!(registered(&facts), Ok(()));
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "vars".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert_eq!(registered(&facts), Ok(()));
    facts.capabilities.constructs[3].status = ConstructSupport::Supported;
    assert_eq!(registered(&facts), Ok(()));
    check_comparison_capability(&mut facts);
    facts.capabilities.constructs[3].name = "setattr".to_owned();
    assert!(registered(&facts).is_err());
    facts.capabilities.constructs.pop();
    facts.capabilities.constructs[2].name = "vars".to_owned();
    assert!(registered(&facts).is_err());
    facts.capabilities.constructs.pop();
    facts.capabilities.constructs[1].name = "getattr".to_owned();
    assert!(registered(&facts).is_err());
    facts.capabilities.constructs.clear();
    assert!(registered(&facts).is_err());
}

fn check_comparison_capability(facts: &mut Facts) {
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "string_literal_compare".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert_eq!(registered(facts), Ok(()));
    facts.capabilities.constructs[4].status = ConstructSupport::Supported;
    assert_eq!(registered(facts), Ok(()));
    check_getattr_capability(facts);
    facts.capabilities.constructs[4].name = "setattr".to_owned();
    assert!(registered(facts).is_err());
    facts.capabilities.constructs.pop();
}

fn check_getattr_capability(facts: &mut Facts) {
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "getattr".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert!(registered(facts).is_err());
    facts
        .capabilities
        .sections
        .push(archkeel_facts::envelope::SectionName::parse("typing_signals").expect("a section"));
    assert_eq!(registered(facts), Ok(()));
    facts.capabilities.constructs[5].status = ConstructSupport::Supported;
    assert_eq!(registered(facts), Ok(()));
    facts
        .capabilities
        .constructs
        .push(archkeel_facts::envelope::ConstructCapability {
            name: "any_annotation".to_owned(),
            status: ConstructSupport::Partial,
        });
    assert_eq!(registered(facts), Ok(()));
    facts.capabilities.constructs[6].status = ConstructSupport::Supported;
    assert!(registered(facts).is_err());
    facts.capabilities.constructs.pop();
    facts.capabilities.constructs[5].name = "hasattr".to_owned();
    assert!(registered(facts).is_err());
    facts.capabilities.constructs.pop();
    facts.capabilities.sections.pop();
}

#[test]
fn only_the_python_survey_with_its_routes_may_state_an_interface() {
    use archkeel_facts::envelope::ProfileLimits;
    let routes = crate::features::ROUTES_FEATURE.to_owned();
    let stated = |profile: Profile, features: Vec<String>, symbols: LimitSupport| {
        let sections: &[&str] = match profile {
            Profile::Python => &["calls", "imports", "references", "symbols", "unknowns"],
            _ => &["imports", "unknowns"],
        };
        let mut facts = survey_of(profile, sections);
        facts.capabilities.resolution_features = features;
        facts.profile_limits = Some(ProfileLimits {
            dependency_symbols: symbols,
            interface_boundary: LimitSupport::Supported,
        });
        registered(&facts)
    };
    // AD-504: the Python survey states an interface only with the feature of its routes.
    assert_eq!(
        stated(
            Profile::Python,
            vec![routes.clone()],
            LimitSupport::Supported
        ),
        Ok(())
    );
    for (profile, features, symbols, reason) in [
        (
            Profile::Python,
            vec![],
            LimitSupport::Unsupported,
            "needs the feature",
        ),
        (
            Profile::Python,
            vec![],
            LimitSupport::Supported,
            "needs the feature",
        ),
        (
            Profile::Dart,
            vec![routes],
            LimitSupport::Supported,
            "no interface rule",
        ),
    ] {
        let refused = stated(profile, features, symbols).unwrap_err();
        assert!(refused.contains(reason), "{profile:?}: {refused}");
    }
}
