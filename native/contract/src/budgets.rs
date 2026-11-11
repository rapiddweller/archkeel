// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_check_interface_budgets` (AD-99): a budget counts a declared facade, so an unknown component
//! is an error and not a PASS.

use crate::error::{invalid, Parsed};
use crate::model::{Component, ComponentLabel};
use crate::model_declarations::{CouplingBudget, FacadeBudget};
use crate::read::repeats;
use crate::rule::Rule;

/// Whether the component exists and declares a public facade: `None` when it does not exist.
fn facade(components: &[Component], label: &ComponentLabel) -> Option<bool> {
    components
        .iter()
        .find(|component| component.label == *label)
        .map(|component| component.public.is_some())
}

fn budget_component(
    components: &[Component],
    key: &str,
    label: &ComponentLabel,
    needs_facade: bool,
) -> Parsed<()> {
    match facade(components, label) {
        None => Err(invalid(format!(
            "contract.declarations.{key} names no component: {:?}",
            label.0
        ))),
        Some(false) if needs_facade => Err(invalid(format!(
            "contract.declarations.{key} {:?} declares no public facade",
            label.0
        ))),
        Some(_) => Ok(()),
    }
}

pub(crate) fn check_interface_budgets(
    components: &[Component],
    rules: &[Rule],
    facades: &[FacadeBudget],
    pairs: &[CouplingBudget],
) -> Parsed<()> {
    let counted = rules.iter().any(
        |rule| matches!(rule, Rule::InterfaceBoundary(boundary) if boundary.include_type_checking),
    );
    if !pairs.is_empty() && !counted {
        return Err(invalid(
            "contract.declarations.coupling_budgets need an interface_boundary rule that includes \
             TYPE_CHECKING imports",
        ));
    }
    for (index, budget) in facades.iter().enumerate() {
        let key = format!("facade_budgets[{index}].component");
        budget_component(components, &key, &budget.component, true)?;
    }
    for (index, pair) in pairs.iter().enumerate() {
        budget_component(
            components,
            &format!("coupling_budgets[{index}].source"),
            &pair.source,
            false,
        )?;
        budget_component(
            components,
            &format!("coupling_budgets[{index}].target"),
            &pair.target,
            true,
        )?;
        if pair.source == pair.target {
            return Err(invalid(format!(
                "contract.declarations.coupling_budgets[{index}] names one component twice"
            )));
        }
    }
    let facade_subjects: Vec<&ComponentLabel> =
        facades.iter().map(|item| &item.component).collect();
    let pair_subjects: Vec<String> = pairs
        .iter()
        .map(|item| format!("{} -> {}", item.source.0, item.target.0))
        .collect();
    if repeats(&facade_subjects) || repeats(&pair_subjects) {
        return Err(invalid("contract.declarations budgets repeat a subject"));
    }
    Ok(())
}
