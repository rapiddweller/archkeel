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

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::envelope::{
    ConstructSupport, Dirty, Facts, ProfileLimits, RequirementState, Role, Runtime as RuntimeFact,
    TargetSource,
};
use archkeel_facts::profile_traits::AnalysisCapabilities;
use archkeel_facts::vocab::{Kind, ResolutionDimension};
use archkeel_facts::{GapFact, Section};

use crate::coverage::data_of;
use crate::gap_class::{self, Class, EffectGap};

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
    /// The linked collector's typed profile statements, absent for a wire reply.
    pub(crate) profile_limits: Option<ProfileLimits>,
    /// The linked collector's stated assumption (AD-540), absent for a wire reply.
    pub(crate) scope_premise: Option<String>,
    /// The provenance of the type-reach facts that the scan used, checked by `admitted` (AD-1116).
    pub(crate) type_reach: Option<archkeel_facts::envelope::TypeReach>,
    pub(crate) excluded_sources: Vec<String>,
    /// Each pair's source, target, dispatch flag and the two scope proofs.
    pub(crate) pair_gaps: Vec<(String, String, bool, bool, bool)>,
    /// Whether every separate site for a pair leaves no written route open.
    pub(crate) named_sites: BTreeMap<(String, String), bool>,
    /// Each gap that states its effect (AD-564).
    pub(crate) effect_gaps: Vec<EffectGap>,
    /// The host could not read the head or the state of the work tree.
    pub(crate) git_unknown: bool,
    /// The runtime check.
    pub(crate) runtime: Runtime,
    /// Each dynamic import limit: its source module (`None` when the record names none) and its
    /// `under_type_checking` flag (`None` when the record has none).
    pub(crate) dynamic_imports: Vec<Dynamic>,
    /// The construct kinds that the collector examines (any status but `unsupported`).
    pub(crate) constructs: Vec<String>,
    /// The collector explicitly supports a complete inventory of nominal construct selectors.
    pub(crate) construct_selectors: bool,
    /// The reply has the feature after which one profile reads symbol-level selectors.
    pub(crate) symbol_feature: bool,
    /// The collector read and parsed each selected file, and the selected inputs are the
    /// selected files (`evaluate.py` `_source_inventory_complete`; slice S7).
    pub(crate) inventory_complete: bool,
    /// Fixed capabilities supplied with the checked facts.
    pub(crate) analysis: AnalysisCapabilities,
    /// The host can accept a dependency scope proof from the runtime of the reply (AD-418).
    pub(crate) scope_receipt: bool,
    /// Each file without a module of its own: its path, the module of its path and its owner.
    pub(crate) owned_files: Vec<(String, String, String)>,
}

/// One dynamic import limit of the `unknowns` section (`dynamic_dependency_limits`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Dynamic {
    pub(crate) source: Option<String>,
    pub(crate) type_checking: Option<bool>,
}

impl Dynamic {
    /// True when a rule that leaves out type-only imports does not see this limit. The
    /// reference engine reads the flag of the record; a record without it stops that engine,
    /// so the limit reaches every rule (fail closed).
    pub(crate) fn type_only(&self) -> bool {
        self.type_checking == Some(true)
    }
}

/// The scope facts of the facts of a reply.
pub(crate) fn observed(
    facts: &Facts,
    analysis: AnalysisCapabilities,
    classes: &[Class],
    live_target: Option<TargetSource>,
) -> Observed {
    // A gap between two modules that states an effect is not a pair gap (`gap_class::Class`).
    let pair_gaps = facts
        .coverage
        .gaps
        .iter()
        .zip(classes)
        .filter(|(_, class)| **class == Class::Pair)
        .filter_map(|(gap, _)| {
            let data = data_of(&gap.data);
            Some((
                data.source_module.as_ref()?.as_str().to_owned(),
                data.module.as_ref()?.as_str().to_owned(),
                data.dispatch,
                execution_only(&gap.data),
                data.no_name_route,
            ))
        })
        .collect();
    let unknowns = || {
        facts
            .sections
            .iter()
            .filter_map(|section| match section {
                Section::Unknowns(records) => Some(records),
                _ => None,
            })
            .flatten()
    };
    let dynamic_imports = unknowns()
        .filter_map(|record| match &record.data {
            GapFact::DynamicImportLimit(data) => Some(Dynamic {
                source: data.source_module.as_ref().map(|m| m.as_str().to_owned()),
                type_checking: data.under_type_checking,
            }),
            // `dynamic_dependency_limits` reads no other kind of the `unknowns` section.
            GapFact::CollectionGap(_)
            | GapFact::SourceResolutionGap(_)
            | GapFact::PrivateAttributeAccessLimit(_)
            | GapFact::ExceptionGap { .. } => None,
        })
        .collect();
    Observed {
        profile_limits: facts.profile_limits,
        named_sites: named_sites(unknowns().map(|gap| &gap.data)),
        scope_premise: facts.scope_premise.clone(),
        type_reach: facts.type_reach.clone(),
        excluded_sources: facts.excluded_sources.clone(),
        pair_gaps,
        effect_gaps: gap_class::effect_gaps(&facts.coverage, classes),
        git_unknown: facts.source.git_head == "unknown"
            || matches!(facts.source.dirty, Dirty::Unknown(_)),
        runtime: reply_runtime(&facts.runtime, live_target),
        dynamic_imports,
        constructs: facts
            .capabilities
            .constructs
            .iter()
            .filter(|entry| entry.status != ConstructSupport::Unsupported)
            .map(|entry| entry.name.clone())
            .collect(),
        construct_selectors: construct_selectors(facts),
        symbol_feature: facts
            .capabilities
            .resolution_features
            .iter()
            .any(|feature| feature == SYMBOL_FEATURE),
        inventory_complete: inventory_complete(facts),
        analysis,
        scope_receipt: facts.runtime.carries_scope_proof(),
        owned_files: facts
            .owned_files
            .iter()
            .map(|file| {
                let module = file.module.as_str().to_owned();
                (
                    file.rel_path.clone(),
                    module,
                    file.owner.as_str().to_owned(),
                )
            })
            .collect(),
    }
}

fn named_sites<'a>(gaps: impl Iterator<Item = &'a GapFact>) -> BTreeMap<(String, String), bool> {
    gaps.filter_map(|gap| {
        let GapFact::SourceResolutionGap(data) = gap else {
            return None;
        };
        if data.resolution_dimension != Some(ResolutionDimension::Imports) {
            return None;
        }
        let (source, target) = (data.source_module.as_ref()?, data.module.as_ref()?);
        (source != target).then(|| {
            (
                (source.as_str().to_owned(), target.as_str().to_owned()),
                data.no_name_route,
            )
        })
    })
    .fold(BTreeMap::new(), |mut pairs, (pair, name_free)| {
        pairs
            .entry(pair)
            .and_modify(|all| *all &= name_free)
            .or_insert(name_free);
        pairs
    })
}

fn construct_selectors(facts: &Facts) -> bool {
    Kind::ConstructSelector.construct().is_some_and(|name| {
        facts
            .capabilities
            .constructs
            .iter()
            .any(|entry| entry.name == name && entry.status == ConstructSupport::Supported)
    })
}

// A wire marker alone cannot prove that the live collector made this claim.
fn execution_only(gap: &GapFact) -> bool {
    matches!(gap, GapFact::CollectionGap(data)
        if data.dispatch && data.resolution_dimension == Some(ResolutionDimension::RuntimeEffects))
}

/// A verified live target from configuration or defaults needs no comparison against an absent
/// project requirement. The target source in a saved reply cannot grant this exception.
fn reply_runtime(reported: &RuntimeFact, live_target: Option<TargetSource>) -> Runtime {
    match (reported, live_target) {
        (
            RuntimeFact {
                required: None,
                requirement_state:
                    RequirementState::MetadataMissing | RequirementState::RequirementMissing,
                ..
            },
            Some(TargetSource::Config | TargetSource::Default),
        ) if release(&reported.version).is_some() => Runtime::Satisfied,
        _ => runtime(reported),
    }
}

/// `_source_inventory_complete`: the selected files are not empty, they are the paths of the
/// selected inputs, and the collector read and parsed each of them.
pub(crate) fn inventory_complete(facts: &Facts) -> bool {
    let coverage = &facts.coverage;
    let selected: BTreeSet<&str> = coverage.selected_files.iter().map(String::as_str).collect();
    let inputs: BTreeSet<&str> = facts
        .inputs
        .iter()
        .filter(|input| input.role == Role::Selected)
        .map(|input| input.path.as_str())
        .collect();
    let count = selected.len() as u64;
    !selected.is_empty()
        && selected == inputs
        && coverage.files_read == count
        && coverage.files_parsed == count
}

/// The runtime check of `runtime_diagnostic` for the forms that the core reads: a declared
/// requirement of clauses `>=X` and `<X`, joined by commas, and a version, all numeric releases
/// (AD-472: a caret requirement `^3.9` is written as `>=3.9,<4.0`). A missing requirement is a
/// mismatch in the reference engine for every runtime; each other form is not read, so it gives
/// no PASS.
pub(crate) fn runtime(runtime: &RuntimeFact) -> Runtime {
    if runtime.requirement_state != RequirementState::Declared {
        return Runtime::Unread;
    }
    let Some(required) = &runtime.required else {
        return Runtime::Mismatch;
    };
    let Some(version) = release(&runtime.version) else {
        return Runtime::Unread;
    };
    let mut found = Runtime::Satisfied;
    for clause in required.split(',').map(str::trim) {
        let (bound, wanted) = match clause.strip_prefix(">=") {
            Some(bound) => (bound, [Ordering::Greater, Ordering::Equal]),
            // `<=X` leaves `=X`, which is no release: the clause stays unread.
            None => match clause.strip_prefix('<') {
                Some(bound) => (bound, [Ordering::Less, Ordering::Less]),
                None => return Runtime::Unread,
            },
        };
        let Some(bound) = release(bound.trim()) else {
            return Runtime::Unread;
        };
        if !wanted.contains(&compare(&version, &bound)) {
            found = Runtime::Mismatch;
        }
    }
    found
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

#[cfg(test)]
#[path = "observed_tests.rs"]
mod tests;
