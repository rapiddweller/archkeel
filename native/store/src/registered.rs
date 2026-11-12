// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The registered capability sets of each profile that the store checks (AD-378, lead decision
//! L-35a). A reply whose sections, resolution features or construct capabilities are not one
//! registered set is refused by name, as `evaluate_source` refuses it
//! (`check/evaluation/evaluate.py:1006-1056`): never a PASS, never a silent subset.
//!
//! - TypeScript (`evaluate.py:1031-1054`): the features without `bundler-mode-v1` are the legacy
//!   set (`static-imports`, or the four native import features) with the sections `imports` and
//!   `unknowns` and no construct capability; or the inner UML set (the native import features
//!   and `inner-uml-v1`, optionally `script-globals-v1`) with the six inner UML sections, and
//!   either no construct capability or the `constructs` section with exactly
//!   `string_literal_compare` `partial`.
//! - Rust (`evaluate.py:1055-1056`, `ir/profiles.py:227-252`): the sections without the
//!   optional `symbols` are exactly `imports` and `unknowns`.

use std::collections::BTreeSet;

use archkeel_facts::envelope::{ConstructSupport, Facts, Profile};

const NATIVE_IMPORTS: [&str; 4] = [
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
];

/// The message of `evaluate_source` for a set that is not registered.
const NOT_REGISTERED: &str = "source sections or resolution features are not registered";

fn names<'a>(items: impl IntoIterator<Item = &'a str>) -> BTreeSet<&'a str> {
    items.into_iter().collect()
}

/// The reply refused by name unless its capability sets are a registered set of its profile.
pub(crate) fn registered(facts: &Facts) -> Result<(), String> {
    let sections = names(facts.capabilities.sections.iter().map(|name| name.as_str()));
    match facts.profile {
        Profile::TypeScript => typescript(facts, &sections),
        Profile::Rust => {
            let mut required = sections;
            required.remove("symbols");
            if required == names(["imports", "unknowns"]) {
                Ok(())
            } else {
                Err("source sections do not match the registered profile".to_owned())
            }
        }
        Profile::Python | Profile::Dart => Err(format!(
            "the store does not check {} replies yet",
            facts.profile.as_str()
        )),
    }
}

fn typescript(facts: &Facts, sections: &BTreeSet<&str>) -> Result<(), String> {
    let mut features = names(
        facts
            .capabilities
            .resolution_features
            .iter()
            .map(String::as_str),
    );
    features.remove("bundler-mode-v1");
    let constructs = &facts.capabilities.constructs;
    let native = names(NATIVE_IMPORTS);
    let legacy = *sections == names(["imports", "unknowns"])
        && (features == names(["static-imports"]) || features == native)
        && constructs.is_empty();
    let mut inner_features = native.clone();
    inner_features.insert("inner-uml-v1");
    let mut script_globals = inner_features.clone();
    script_globals.insert("script-globals-v1");
    let inner_sections = names([
        "imports",
        "unknowns",
        "symbols",
        "calls",
        "references",
        "bindings",
    ]);
    let mut with_constructs = inner_sections.clone();
    with_constructs.insert("constructs");
    let partial_compare = matches!(
        constructs.as_slice(),
        [only] if only.name == "string_literal_compare" && only.status == ConstructSupport::Partial
    );
    let inner = (features == inner_features || features == script_globals)
        && ((*sections == inner_sections && constructs.is_empty())
            || (*sections == with_constructs && partial_compare));
    if legacy || inner {
        Ok(())
    } else {
        Err(NOT_REGISTERED.to_owned())
    }
}
