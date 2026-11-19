// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rule kinds that no slice decides yet, as one pattern (SPOT). The limits of a profile
//! (`limits.rs`) and the read sets of a gap (`gap_effects.rs`) match on it, so a kind that a slice
//! starts to decide leaves both lists at once, and each match keeps no catch-all arm.

/// A pattern of each `archkeel_contract::Rule` kind that no slice decides.
macro_rules! undecided_rule {
    () => {
        archkeel_contract::Rule::ForbiddenCallArgument(_)
            | archkeel_contract::Rule::CatalogArgument(_)
            | archkeel_contract::Rule::CatalogUse(_)
            | archkeel_contract::Rule::ForbiddenEffectUnderCondition(_)
            | archkeel_contract::Rule::SourceOwnership(_)
            | archkeel_contract::Rule::BoundedNumericOperand(_)
            | archkeel_contract::Rule::ProtocolDeclarations(_)
    };
}
