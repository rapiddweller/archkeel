// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trait impl runs in code that never names its module (#1515, #1516, AD-806).
//!
//! `impl Tr for Y` in `b` runs where a value of `Y` meets a use of `Tr`: a method call on a value
//! that another module gives (`c::make().m()`), an operator, `?`, `for`, a format macro, a drop, a
//! `dyn Tr` value, a generic function of another module with the bound `T: Tr` or a supertrait of
//! it, and a re-export of `Tr`. None of these writes a name of `b`. A caller can hold such a value,
//! or reach such a function, only over a chain of dependencies that ends in `b`. So each module
//! that reaches `b` over the edges and the pair gaps of the reply gets the pair gap to `b`
//! (`impl_flow::settle`), when `b` holds a trait impl that runs code: a block with an item other
//! than an associated type, or a derive other than `Copy`. The host drops a gap that the contract
//! allows (AD-357).

use crate::attrs::model::Proof;
use crate::crates::Workspace;
use crate::impl_globs::depends;
use crate::site::Site;
use crate::tree::Module;

use super::flow::Pending;

/// The pending gap from each module that may run a trait impl of another module to that module:
/// the modules of its crate and of each crate that depends on it, before the value flow.
pub(super) fn trait_impl_candidates(workspace: &Workspace, modules: &[Module]) -> Vec<Pending> {
    let mut pending = Vec::new();
    for home in modules {
        let Some(site) = runs_code(home) else {
            continue;
        };
        let target = home.module.as_str();
        let reason = format!(
            "A trait impl in {target} may run in code that reaches {target} without naming it: a method or an operator on a value of its type, a drop, a format, a generic or dyn call"
        );
        let callers = modules.iter().filter(|caller| {
            caller.module != home.module
                && (caller.crate_index == home.crate_index || depends(workspace, caller, home))
        });
        for caller in callers {
            pending.push(Pending {
                source: caller.module.clone(),
                rel: home.rel.clone(),
                site: site.clone(),
                target: target.to_owned(),
                reason: reason.clone(),
            });
        }
    }
    pending
}

/// The place of a trait impl of the file that runs code: a written impl block with an item other
/// than an associated type, or a derive other than `Copy`, which writes an impl in the module of its
/// item. `None` when the file has neither.
fn runs_code(home: &Module) -> Option<&Site> {
    let written = home.scan.orphans.impls.iter().find(|found| found.runs);
    let derived = home.scan.concerns.iter().find(|concern| {
        matches!(&concern.proof, Some(Proof::Derive(usage))
            if usage.path.last().map(String::as_str) != Some("Copy"))
    });
    written
        .map(|found| &found.site)
        .or(derived.map(|concern| &concern.site))
}
