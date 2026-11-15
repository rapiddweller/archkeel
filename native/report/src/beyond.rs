// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text of a PASS that the core decides beyond the reference engine (AD-384, AD-564).

/// Why a PASS of `model` is a PASS beyond the reference engine, if it is one: the reference
/// engine gives each rule UNKNOWN for a kept pair gap (AD-384) and for a gap that states its
/// effect (AD-564), and the core passes a rule that no such gap can change.
pub(crate) fn reason(model: &archkeel_model::Model) -> Option<String> {
    let (kept, stated) = (model.kept_pair_gaps(), model.effect_gaps());
    let pairs = format!("no one of the {kept} kept pair gaps can change the rule");
    let effects = format!("no one of the {stated} gaps with a stated effect can change the rule");
    match (kept > 0, stated > 0) {
        (false, false) => None,
        (true, false) => Some(pairs),
        (false, true) => Some(effects),
        (true, true) => Some(format!("{pairs}; {effects}")),
    }
}
