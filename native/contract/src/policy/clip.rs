// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The claims of an inside contract, clipped to the physical packages of its parent component.
//!
//! Python `_inside_source_domain` (`check/evaluation/evaluate.py`), the part over the
//! components: each package of a child component that lies below a package of the parent stays;
//! each exact module that the parent names, or that lies below a package of the parent, stays.
//! Each claim outside the parent is cut, and the component that held it is named: the reference
//! engine writes a coverage failure for it (`inside_source_domain_incomplete`). The part over the
//! modules of the reply (the source domain of the mount) belongs to the model.

use crate::document::Contract;
use crate::model::{ItemId, Package};

record!(
    pub(crate),
    /// An inside contract with the claims of its components clipped to its parent, and the id of
    /// each component that claimed a package or an exact module outside the parent.
    Clipped {
        contract: Contract,
        outside: Vec<ItemId>,
    }
);

/// True when `name` is `scope` or a dotted name below it (`in_scope`).
fn in_scope(name: &str, scope: &str) -> bool {
    name.strip_prefix(scope)
        .is_some_and(|rest| rest.is_empty() || rest.starts_with('.'))
}

/// Clip the components of `declared` (an inside contract with scoped ids) to the packages and the
/// exact modules of its parent component. The rules, the declarations and the digest stay.
pub fn clip_inside(packages: &[Package], exact: &[Package], declared: &Contract) -> Clipped {
    let roots: Vec<&str> = packages.iter().map(|p| p.0.as_str()).collect();
    let below = |name: &str| roots.iter().any(|root| in_scope(name, root));
    let mut contract = declared.clone();
    let mut outside = Vec::new();
    for component in &mut contract.components {
        let before = (component.packages.len(), component.exact_modules.len());
        component.packages.retain(|package| below(&package.0));
        component
            .exact_modules
            .retain(|module| exact.iter().any(|item| item == module) || below(&module.0));
        if before != (component.packages.len(), component.exact_modules.len()) {
            outside.push(component.id.clone());
        }
    }
    Clipped { contract, outside }
}

#[cfg(test)]
#[path = "clip_tests.rs"]
mod tests;
