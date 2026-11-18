// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: an unread or mismatched runtime requirement holds the run (`proof.rs`), so only a
// requirement whose every clause the core reads can give a satisfied runtime (AD-472).

use super::*;
use crate::edges::tests::golden;
use crate::{Graph, Producer, Settings};
use archkeel_facts::envelope::{LimitSupport, Reply};

fn checked(required: Option<&str>, version: &str) -> Runtime {
    runtime(&RuntimeFact {
        name: "collector".to_owned(),
        required: required.map(str::to_owned),
        requirement_state: RequirementState::Declared,
        version: version.to_owned(),
        target_source: None,
        target_description: None,
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
    // A leading zero does not change a part: `3.010` is `3.10`.
    assert_eq!(
        checked(Some(">=03.09,<3.015"), "3.14.0"),
        Runtime::Satisfied
    );
    assert_eq!(checked(Some(">=3.9,<3.010"), "3.14.0"), Runtime::Mismatch);
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

#[test]
fn a_missing_requirement_needs_a_bound_producer_and_a_selected_target(
) -> Result<(), Box<dyn std::error::Error>> {
    let mut reply = golden().ok_or("the golden reply")?;
    let facts = &mut reply.facts;
    facts.runtime.requirement_state = RequirementState::RequirementMissing;
    facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: LimitSupport::Supported,
        interface_boundary: LimitSupport::Supported,
        publication_surface: LimitSupport::Unsupported,
    });
    let read = |reply: &Reply, producer: Producer| {
        let settings = Settings::new("shop".into(), reply.facts.profile.as_str().into(), vec![])
            .with_producer(producer);
        Graph::recorded(&reply.facts, settings)
            .map(|graph| graph.observed().runtime)
            .map_err(|reason| reason.to_string())
    };
    for source in [TargetSource::Config, TargetSource::Default] {
        reply.facts.runtime.target_source = Some(source);
        assert_eq!(read(&reply, Producer::Trusted)?, Runtime::Satisfied);
        assert_eq!(read(&reply, Producer::External)?, Runtime::Unread);
    }
    let mut wrong_adapter = reply.clone();
    wrong_adapter.facts.adapter.name = "other".to_owned();
    assert_eq!(read(&wrong_adapter, Producer::Trusted)?, Runtime::Unread);

    let wire: Reply = serde_json::from_slice(&serde_json::to_vec(&reply)?)?;
    assert_eq!(
        wire.facts.runtime.target_source,
        Some(TargetSource::Default)
    );
    assert_eq!(read(&wire, Producer::Trusted)?, Runtime::Unread);
    for source in [
        None,
        Some(TargetSource::Requirement),
        Some(TargetSource::Legacy),
    ] {
        reply.facts.runtime.target_source = source;
        assert_eq!(read(&reply, Producer::Trusted)?, Runtime::Unread);
    }
    reply.facts.runtime.target_source = Some(TargetSource::Config);
    reply.facts.runtime.required = Some(">=3.99".into());
    assert_eq!(read(&reply, Producer::Trusted)?, Runtime::Unread);
    reply.facts.runtime.requirement_state = RequirementState::Declared;
    assert_eq!(read(&reply, Producer::Trusted)?, Runtime::Mismatch);
    reply.facts.runtime.requirement_state = RequirementState::MetadataMissing;
    reply.facts.runtime.required = None;
    reply.facts.runtime.version = "invalid".into();
    assert_eq!(read(&reply, Producer::Trusted)?, Runtime::Unread);
    Ok(())
}
