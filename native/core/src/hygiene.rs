// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Contract hygiene of a scanned run (AD-466).
//!
//! Release 4.0.1 rejects a run (exit 2) when a contract cites a provenance file that does not
//! exist, when the marked graph of the provenance documents is missing, repeated or stale, when a
//! contract reference is outside the namespace or owned by another component, and for more
//! conditions of the same family. The core checks each condition that it ports and names each
//! other condition that applies to the contract, so no such run can PASS:
//!
//! - A cited path that the core cannot read refuses the whole contract (exit 2).
//! - Each defect that a check finds is a named row with `Reason::Hygiene`.
//! - Each family that applies and that no check ports is a named row with
//!   `Unsupported::Hygiene`.
//!
//! A row only holds back a PASS: it never makes a verdict. Only the scan request reads the
//! repository, so only a scan run has the documents.

use std::collections::BTreeMap;
use std::iter;

use archkeel_contract::{Contract, Rule};
use archkeel_model::{in_scope, Graph, Hygiene, ModelTree, Reason, Unsupported};

use crate::contract::Usable;
use crate::hygiene_graph::{self, Pair};
use crate::hygiene_pairs;
use crate::hygiene_refs;
use crate::provenance::Documents;

/// The interface lifecycle checks: they apply to a contract with an `interface_boundary` rule.
const INTERFACE: &str = "interface.undeclared, interface.unused, interface.usage_unknown, \
                         interface.missing, interface.planned_built";
/// The checks of `declarations.compat`.
const COMPATIBILITY: &str = "compatibility.invalid";
/// The check of an `allowed_dependency` rule of a mounted contract against its parent.
const INSIDE: &str = "inside.forbidden_import";
/// The measurement budgets: release 4.0.1 needs a baseline for them, and `main` reads none.
const BUDGET: &str = "baseline.invalid, budget.exceeded, budget.unknown";

/// What the hygiene of a run adds to the gaps of the core.
#[derive(Debug, Default)]
pub(crate) struct Found {
    /// A reason that refuses the whole contract.
    pub(crate) refusal: Option<String>,
    /// The reason of each hygiene row.
    pub(crate) rules: BTreeMap<String, Reason>,
}

impl Found {
    fn defect(&mut self, place: &str, (code, pointer, subject, claim): hygiene_refs::Finding) {
        let id = format!("hygiene:{code}:{place}{pointer}:{subject}");
        let detail = format!("{place}{pointer} {subject}: {claim}");
        self.rules
            .insert(id, Reason::Hygiene(Hygiene::new(code, detail)));
    }

    fn gap(&mut self, place: &str, family: &'static str, codes: &'static str) {
        let id = format!("hygiene:{family}:{place}");
        let reason = Reason::Unsupported(Unsupported::Hygiene(codes));
        self.rules.insert(id, reason);
    }

    fn refuse(&mut self, code: &'static str, detail: String) {
        self.refusal = Some(Reason::Hygiene(Hygiene::new(code, detail)).to_string());
    }
}

/// The hygiene of a request without provenance documents (a dual-run or a check request): one
/// named row for a usable contract, so such a request cannot give PASS without hygiene.
pub(crate) fn unread(usable: Option<&Usable>) -> Found {
    let mut found = Found::default();
    if usable.is_some() {
        let reason = Reason::Unsupported(Unsupported::HygieneInput);
        found.rules.insert("hygiene:request".to_owned(), reason);
    }
    found
}

/// The hygiene of a run over the usable contract at `path`, the provenance documents and the
/// models. A run without a usable contract has no hygiene: its contract already names a gap.
pub(crate) fn check(
    documents: &Documents,
    usable: Option<&Usable>,
    models: Result<&ModelTree, Reason>,
    namespace: &str,
    path: &str,
) -> Found {
    let mut found = Found::default();
    let Some(usable) = usable else {
        return found;
    };
    if !documents.unread().is_empty() {
        let list: Vec<&str> = documents.unread().iter().map(String::as_str).collect();
        let detail = format!(
            "the core cannot read the provenance files {}: each must be a regular file inside \
             the repository, not a link",
            list.join(", ")
        );
        found.refuse("reference.provenance", detail);
        return found;
    }
    let mounts = usable.tree.iter().flat_map(|tree| tree.mounts());
    let contracts = iter::once((path, &usable.root))
        .chain(mounts.map(|mount| (mount.path().as_str(), mount.contract())));
    for (place, contract) in contracts {
        let findings = [
            hygiene_refs::namespace(contract, namespace),
            hygiene_refs::public(contract),
            hygiene_refs::responsibility(contract),
        ];
        for finding in findings.into_iter().flatten() {
            found.defect(place, finding);
        }
        let has = |test: fn(&Rule) -> bool| contract.rules().iter().any(test);
        if has(|rule| matches!(rule, Rule::InterfaceBoundary(_))) {
            found.gap(place, "interface", INTERFACE);
        }
        if place != path && has(|rule| matches!(rule, Rule::AllowedDependency(_))) {
            found.gap(place, "inside", INSIDE);
        }
    }
    root(&mut found, documents, &usable.root, models, path);
    found
}

/// The checks of the root contract alone, as the reference engine runs them.
fn root(
    found: &mut Found,
    documents: &Documents,
    contract: &Contract,
    models: Result<&ModelTree, Reason>,
    path: &str,
) {
    for finding in hygiene_refs::rationale(contract) {
        found.defect(path, finding);
    }
    if let Some(declarations) = contract.declarations() {
        if !declarations.compat().is_empty() {
            found.gap(path, "compatibility", COMPATIBILITY);
        }
        if !declarations.measurement_budgets().is_empty() {
            found.gap(path, "budget", BUDGET);
        }
    }
    // The checks below read the code: a run without models has no PASS to hold back.
    let Ok(models) = models else {
        return;
    };
    let graph = models.root().graph();
    for finding in unscanned(contract, graph)
        .into_iter()
        .chain(api_surface(contract, graph))
    {
        found.defect(path, finding);
    }
    let observed = hygiene_pairs::observed(contract, graph);
    for (code, subject, claim) in hygiene_pairs::closed_world(contract, &observed) {
        found.defect(path, (code, "/rules".to_owned(), subject, claim));
    }
    let mut texts = Vec::new();
    for reference in archkeel_contract::policy::provenance_paths(contract) {
        let text = documents.bytes(&reference).and_then(hygiene_graph::text);
        let Some(text) = text else {
            let detail = format!("the provenance document {reference} is not UTF-8 text");
            found.refuse("reference.provenance", detail);
            return;
        };
        texts.push((reference, text));
    }
    let permitted: std::collections::BTreeSet<Pair> = hygiene_pairs::permitted(contract);
    for (code, subject, claim) in hygiene_graph::findings(&texts, &observed, &permitted) {
        found.defect(path, (code, "/components".to_owned(), subject, claim));
    }
}

/// The component packages and exact modules without a scanned module
/// (`reference.package_unscanned`).
fn unscanned(contract: &Contract, graph: &Graph) -> Vec<hygiene_refs::Finding> {
    let modules: Vec<&str> = graph.modules().iter().map(|(_, m)| m.name()).collect();
    let mut found = Vec::new();
    for (index, component) in contract.components().iter().enumerate() {
        for (item, package) in component.packages().iter().enumerate() {
            let package = package.as_text();
            if !modules.iter().any(|module| in_scope(module, package)) {
                let pointer = format!("/components/{index}/packages/{item}");
                let claim = "The component package has no scanned module.".to_owned();
                found.push((
                    "reference.package_unscanned",
                    pointer,
                    package.to_owned(),
                    claim,
                ));
            }
        }
        for (item, exact) in component.exact_modules().iter().enumerate() {
            let exact = exact.as_text();
            if !modules.contains(&exact) {
                let pointer = format!("/components/{index}/exact_modules/{item}");
                let claim = "The exact module has no scanned source file.".to_owned();
                found.push((
                    "reference.package_unscanned",
                    pointer,
                    exact.to_owned(),
                    claim,
                ));
            }
        }
    }
    found
}

/// The `declarations.public_api` entries whose module has no scanned file, or whose name the
/// stated exports of the module do not hold (`api_surface.missing`). The exposed-type part of the
/// reference engine reads type facts that no collector of the core writes, so it has no input.
fn api_surface(contract: &Contract, graph: &Graph) -> Vec<hygiene_refs::Finding> {
    let Some(declarations) = contract.declarations() else {
        return Vec::new();
    };
    let mut found = Vec::new();
    for (index, entry) in declarations.public_api().iter().enumerate() {
        let entry = entry.as_text();
        let (module, name) = entry.split_once(':').unwrap_or((entry, ""));
        let scanned = graph.modules().iter().find(|(_, m)| m.name() == module);
        let claim = match scanned {
            None => "The declared public API entry's module has not been scanned.",
            Some((_, m))
                if !name.is_empty()
                    && !m.exports().is_empty()
                    && !m.exports().iter().any(|export| export == name) =>
            {
                "The module states its exports and the promised name is not in them."
            }
            Some(_) => continue,
        };
        let pointer = format!("/declarations/public_api/{index}");
        found.push((
            "api_surface.missing",
            pointer,
            entry.to_owned(),
            claim.to_owned(),
        ));
    }
    found
}

#[cfg(test)]
#[path = "hygiene_tests.rs"]
mod tests;
