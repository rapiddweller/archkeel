// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the reply says about its own scope beside the coverage gaps of S1 and S2 (slice S4).
//!
//! The scope proof (`proof.rs`) reads these facts. Each one is a cause that the reference engine
//! counts as a coverage failure or a diagnostic, so it can only take a PASS away:
//!
//! - a gap between two modules (`source_module` and a different `module`): the host drops it
//!   only when the contract allows the pair (`check/pair_gaps.py` `drop_allowed_pair_gaps`);
//! - a work tree whose head or state the host could not read
//!   (`check/observation.py` `_add_git_failure`);
//! - a collector runtime outside its declared requirement (`check/runtime.py`
//!   `runtime_diagnostic`, read by `check/observe.py` `observation_diagnostics`);
//! - a dynamic import that the collector could not resolve (`check/evaluation/rule_support.py`
//!   `dynamic_dependency_limits`): it holds back the rules that its source module reaches;
//! - the construct kinds that the collector examines and the resolution features that it has
//!   (`check/evaluation/rules.py` `profile_failures`).

use std::cmp::Ordering;

use archkeel_facts::envelope::{
    ConstructSupport, Dirty, Facts, RequirementState, Runtime as RuntimeFact,
};
use archkeel_facts::sections::{GapFact, Section};

use crate::coverage::data_of;

/// The resolution feature after which the reference engine reads symbol-level selectors of one
/// profile (`evaluate_source`: `dependency_symbols=True`). The core does not know the profile,
/// so a reply with it leaves such a selector undecided.
const SYMBOL_FEATURE: &str = "script-globals-v1";

/// How the collector runtime holds against its declared requirement.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Runtime {
    /// The version satisfies a `>=` requirement of numeric releases.
    Satisfied,
    /// The requirement is absent or the version is below it: a runtime diagnostic.
    Mismatch,
    /// A requirement form or state that the core does not read.
    Unread,
}

/// The scope facts of one reply.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Observed {
    /// Each gap between two modules: its source module and its module.
    pub(crate) pair_gaps: Vec<(String, String)>,
    /// The host could not read the head or the state of the work tree.
    pub(crate) git_unknown: bool,
    /// The runtime check.
    pub(crate) runtime: Runtime,
    /// The source module of each dynamic import limit, or `None` when the record names none.
    pub(crate) dynamic_imports: Vec<Option<String>>,
    /// The construct kinds that the collector examines (any status but `unsupported`).
    pub(crate) constructs: Vec<String>,
    /// The reply has the feature after which one profile reads symbol-level selectors.
    pub(crate) symbol_feature: bool,
}

/// The scope facts of the facts of a reply.
pub(crate) fn observed(facts: &Facts) -> Observed {
    let pair_gaps = facts
        .coverage
        .gaps
        .iter()
        .filter_map(|gap| {
            let data = data_of(&gap.data);
            match (&data.source_module, &data.module) {
                (Some(source), Some(module)) if source != module => {
                    Some((source.as_str().to_owned(), module.as_str().to_owned()))
                }
                _ => None,
            }
        })
        .collect();
    let dynamic_imports = facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Unknowns(records) => Some(records),
            _ => None,
        })
        .flatten()
        .filter_map(|record| match &record.data {
            GapFact::DynamicImportLimit(data) => {
                Some(data.source_module.as_ref().map(|m| m.as_str().to_owned()))
            }
            // `dynamic_dependency_limits` reads no other kind of the `unknowns` section.
            GapFact::CollectionGap(_)
            | GapFact::SourceResolutionGap(_)
            | GapFact::PrivateAttributeAccessLimit(_)
            | GapFact::ExceptionGap { .. } => None,
        })
        .collect();
    Observed {
        pair_gaps,
        git_unknown: facts.source.git_head == "unknown"
            || matches!(facts.source.dirty, Dirty::Unknown(_)),
        runtime: runtime(&facts.runtime),
        dynamic_imports,
        constructs: facts
            .capabilities
            .constructs
            .iter()
            .filter(|entry| entry.status != ConstructSupport::Unsupported)
            .map(|entry| entry.name.clone())
            .collect(),
        symbol_feature: facts
            .capabilities
            .resolution_features
            .iter()
            .any(|feature| feature == SYMBOL_FEATURE),
    }
}

/// The runtime check of `runtime_diagnostic` for the one form that the core reads: a declared
/// requirement `>=X` and a version, both numeric releases. A missing requirement is a mismatch in
/// the reference engine for every runtime; each other form is not read, so it gives no PASS.
pub(crate) fn runtime(runtime: &RuntimeFact) -> Runtime {
    if runtime.requirement_state != RequirementState::Declared {
        return Runtime::Unread;
    }
    let Some(required) = &runtime.required else {
        return Runtime::Mismatch;
    };
    let bound = required.trim().strip_prefix(">=").map(str::trim);
    match (bound.and_then(release), release(&runtime.version)) {
        (Some(bound), Some(version)) if compare(&version, &bound) == Ordering::Less => {
            Runtime::Mismatch
        }
        (Some(_), Some(_)) => Runtime::Satisfied,
        _ => Runtime::Unread,
    }
}

/// The parts of a numeric release (`1.97.0`), without leading zeros, or `None`.
fn release(text: &str) -> Option<Vec<&str>> {
    text.split('.')
        .map(|part| {
            let digits = !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit());
            digits.then(|| part.trim_start_matches('0'))
        })
        .collect()
}

/// PEP 440 release order: part by part, a missing part is zero.
fn compare(left: &[&str], right: &[&str]) -> Ordering {
    let length = left.len().max(right.len());
    for index in 0..length {
        let a = left.get(index).copied().unwrap_or("");
        let b = right.get(index).copied().unwrap_or("");
        let order = a.len().cmp(&b.len()).then_with(|| a.cmp(b));
        if order != Ordering::Equal {
            return order;
        }
    }
    Ordering::Equal
}
