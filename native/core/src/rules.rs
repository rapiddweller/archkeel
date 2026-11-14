// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Rules` request: the gaps that the core names next to the model.
//!
//! The core decides no verdict and no status here: the report evaluates the model and writes
//! each rule verdict and the status of the run (`archkeel_report::rule`, AD-388). The core adds
//! only gaps: the hold of a tree whose models do not hold every mount (AD-379, AD-385) and the
//! reason of each rule of a run without models. A gap never makes a PASS.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, kind_of, Contract, RuleKind};
use archkeel_eval::Outcome;
use archkeel_model::{ModelTree, Reason, Unsupported};
use archkeel_report::Named;

use crate::contract::Usable;

/// True for a rule kind that `archkeel-eval` decides (slices S1, S2, S5 and S7). It chooses only the
/// reason of a rule in a run without a model: the reason of the missing model, or the kind.
fn decided(kind: RuleKind) -> bool {
    // Each kind has an arm: a new kind does not compile without a decision here.
    match kind {
        RuleKind::CompleteAssignment
        | RuleKind::RootLayout
        | RuleKind::ExternalDependencyScope
        | RuleKind::CompleteExternalScope
        | RuleKind::ForbiddenDependency
        | RuleKind::AllowedDependency
        | RuleKind::SiblingIsolation
        | RuleKind::LayerOrder
        | RuleKind::CompleteRequires
        | RuleKind::NoComponentCycles
        | RuleKind::ForbiddenConstruct => true,
        RuleKind::InterfaceBoundary => true,
        RuleKind::SymbolPlacement => false,
        RuleKind::SourceOwnership => false,
        RuleKind::BoundedNumericOperand => false,
        RuleKind::CallOwner => false,
        RuleKind::ForbiddenCallArgument => false,
        RuleKind::CatalogArgument => false,
        RuleKind::CatalogUse => false,
        RuleKind::ForbiddenEffectUnderCondition => false,
        RuleKind::ProtocolDeclarations => false,
        RuleKind::BoundaryTypes => false,
    }
}

/// What an inside-contract tree adds to the root rules: the scoped id and kind of each rule of
/// its mounts, and the number of mounts. Each contract of the tree has its own model (AD-385);
/// a PASS needs the scope proof of the model whose contract holds the rule.
#[derive(Debug, Default)]
pub(crate) struct Tree {
    inside: Vec<(String, RuleKind)>,
    mounts: usize,
}

impl Tree {
    /// A tree of the given inside rules and number of mounts (a test builds the second line).
    #[cfg(test)]
    pub(crate) fn new(inside: Vec<(String, RuleKind)>, mounts: usize) -> Tree {
        Tree { inside, mounts }
    }

    pub(crate) fn of(usable: &Usable) -> Tree {
        Tree {
            inside: usable.inside.clone(),
            mounts: usable.tree.as_ref().map_or(0, |tree| tree.mounts().len()),
        }
    }
}

/// The outcome of each rule of each contract of the tree, or none when the run has no model
/// (the sections read them).
pub(crate) fn outcomes(models: Result<&ModelTree, Reason>) -> Vec<Outcome> {
    match models {
        Ok(models) => archkeel_eval::evaluate_tree(models),
        Err(_) => Vec::new(),
    }
}

/// The gaps of the run: each inside rule of a tree, the hold of a mounted root, and without a
/// model the reason of each rule of the contract. Without a contract, the contract is the gap.
pub(crate) fn named(
    contract: Option<&Contract>,
    models: Result<&ModelTree, Reason>,
    tree: Option<Tree>,
) -> Named {
    let Some(contract) = contract else {
        let missing = Reason::MissingInput(archkeel_model::Input::Contract);
        return Named {
            contract: Some(missing.to_string()),
            ..Named::default()
        };
    };
    let tree = tree.unwrap_or_default();
    let mut rules: BTreeMap<String, Reason> = BTreeMap::new();
    let models = match models {
        Ok(models) => models,
        Err(reason) => {
            let root = contract.rules().iter().map(|rule| {
                let id = head_of(rule).id().as_text().to_owned();
                (id, kind_of(rule))
            });
            for (id, kind) in root.chain(tree.inside.iter().cloned()) {
                let reason = if decided(kind) {
                    reason.clone()
                } else {
                    Reason::Unsupported(Unsupported::Rule(kind))
                };
                rules.insert(id, reason);
            }
            return Named {
                rules,
                ..Named::default()
            };
        }
    };
    // The second line after the proof: a tree whose mounts the models do not all hold never
    // passes a rule (AD-379, AD-385).
    let whole = models.mounts().len() == tree.mounts;
    Named {
        rules,
        contract: None,
        hold: (!whole).then_some(Reason::Unsupported(Unsupported::TreeScope)),
        uml: None,
    }
}
