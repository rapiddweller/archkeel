// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of the validation block of a protocol 11 reply (AD-688).
//!
//! The collector states its own table in the block: its registered capability sets, what an
//! interface statement needs and the owner key of its standard library. The block can only add
//! checks: the store first checks its language-free minimum, which no block can lower. A feature
//! that a registered set names must be one whose claims the store checks; a standard library key
//! with a version must name the minor version of the runtime. The core trusts a reply only when
//! its key names the list of its adapter (`scan.rs`, `check.rs` of the core).
//! A symbol statement needs a feature that writes the symbol of each import. Then the
//! capabilities of the reply must be exactly one registered set, and an interface statement must
//! agree with the need of the block. Each reply is a protocol 11 reply: the decode refuses an
//! older one, which had no block. The store reads no language here.

use std::collections::BTreeSet;

use archkeel_facts::envelope::validation::{
    library_family, versioned_owner, InterfaceNeed, Registered,
};
use archkeel_facts::envelope::{Facts, LimitSupport, Validation};

use crate::features::{known_feature, SYMBOL_FEATURES};

/// The message of `evaluate_source` for a set that is not registered.
pub(crate) const NOT_REGISTERED: &str = "source sections or resolution features are not registered";

/// The block keeps the minimum and admits the reply (`evaluate_source` checks the registered
/// sets after the generic checks, L-35a).
pub(crate) fn check(facts: &Facts) -> Result<(), String> {
    let block = &facts.validation;
    minimum(facts, block)?;
    symbols(facts)?;
    registered(facts, block)?;
    interface(facts, block)
}

/// A symbol statement of the linked collector holds exactly when the reply states a feature that
/// writes the symbol of each import (AD-504 Python, AD-604 Rust, `script-globals-v1` TypeScript).
fn symbols(facts: &Facts) -> Result<(), String> {
    let Some(limits) = facts.profile_limits else {
        return Ok(());
    };
    let stated = facts
        .capabilities
        .resolution_features
        .iter()
        .any(|feature| SYMBOL_FEATURES.contains(&feature.as_str()));
    if (limits.dependency_symbols == LimitSupport::Supported) == stated {
        Ok(())
    } else {
        Err("profile symbol statement does not match its capability".to_owned())
    }
}

/// The language-free minimum that no block lowers.
fn minimum(facts: &Facts, block: &Validation) -> Result<(), String> {
    let named = block.registered.iter().flat_map(Registered::named_features);
    if let Some(feature) = named.into_iter().find(|feature| !known_feature(feature)) {
        return Err(format!(
            "the store does not check the resolution feature {feature} yet"
        ));
    }
    let key = block.standard_library.as_str();
    let family = library_family(key);
    if key != family && key != versioned_owner(family, &facts.runtime.version) {
        return Err(format!(
            "the standard library {key} is not the list of the runtime {}",
            facts.runtime.version
        ));
    }
    if let InterfaceNeed::Feature(feature) = &block.interface {
        if !known_feature(feature) {
            return Err(format!(
                "the store does not check the resolution feature {feature} yet"
            ));
        }
    }
    Ok(())
}

/// The capabilities of the reply are exactly one registered set of the block.
fn registered(facts: &Facts, block: &Validation) -> Result<(), String> {
    let capabilities = &facts.capabilities;
    let sections: BTreeSet<&str> = capabilities
        .sections
        .iter()
        .map(|name| name.as_str())
        .collect();
    let features: BTreeSet<&str> = capabilities
        .resolution_features
        .iter()
        .map(String::as_str)
        .collect();
    let admits = |set: &Registered| {
        let must: BTreeSet<&str> = set.sections.iter().map(|name| name.as_str()).collect();
        let may = set.optional_sections.iter().map(|name| name.as_str());
        let must_features: BTreeSet<&str> = set.features.iter().map(String::as_str).collect();
        let constructs = capabilities.constructs.len() == set.constructs.len()
            && capabilities
                .constructs
                .iter()
                .zip(&set.constructs)
                .all(|(have, want)| have.name == want.name && want.statuses.contains(&have.status));
        within(&sections, &must, may)
            && within(
                &features,
                &must_features,
                set.optional_features.iter().map(String::as_str),
            )
            && constructs
    };
    if block.registered.iter().any(admits) {
        Ok(())
    } else {
        Err(NOT_REGISTERED.to_owned())
    }
}

/// `must` is a part of `have`, and `have` holds nothing beyond `must` and `may`.
fn within<'a>(
    have: &BTreeSet<&'a str>,
    must: &BTreeSet<&'a str>,
    may: impl Iterator<Item = &'a str>,
) -> bool {
    let mut allowed = must.clone();
    allowed.extend(may);
    must.is_subset(have) && have.is_subset(&allowed)
}

/// An interface statement of the linked collector agrees with the need of the block.
fn interface(facts: &Facts, block: &Validation) -> Result<(), String> {
    let Some(limits) = facts.profile_limits else {
        return Ok(());
    };
    let supported = limits.interface_boundary == LimitSupport::Supported;
    // AD-749: the publication surface serves the interface rule only.
    if limits.publication_surface == LimitSupport::Supported && !supported {
        return Err("a publication surface statement needs an interface statement".to_owned());
    }
    match &block.interface {
        InterfaceNeed::Unsupported if supported => {
            Err("the collector makes no interface statement".to_owned())
        }
        InterfaceNeed::Feature(feature) => {
            let stated = facts
                .capabilities
                .resolution_features
                .iter()
                .any(|name| name == feature);
            if supported == stated {
                Ok(())
            } else {
                Err(format!(
                    "an interface statement holds exactly with the feature {feature}"
                ))
            }
        }
        InterfaceNeed::Nothing | InterfaceNeed::Unsupported => Ok(()),
    }
}

#[cfg(test)]
#[path = "validation_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "registered_tests.rs"]
mod registered_tests;
