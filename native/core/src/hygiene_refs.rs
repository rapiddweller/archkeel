// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract references that need no reply (AD-458).
//!
//! Reference engine: `check/validation/references.py` (`reference.namespace`,
//! `reference.public_owner`, `reference.public_underscore`), `ir/model.py` `module_references`,
//! `check/validation/rationale.py` and `_responsibility_diagnostics`. The namespace walk reads the
//! canonical form of the typed contract, whose field names are the names of the reference engine.

use archkeel_contract::{canonical_bytes, Component, Contract, DecidedBy};
use archkeel_model::{claims, in_scope};
use serde_json::Value;

use crate::hygiene_graph::space;

/// One reference finding: the code, the pointer, the subject and the claim.
pub(crate) type Finding = (&'static str, String, String, String);

/// The rule kinds whose `source` names a module, and the kinds whose other fields do.
const SOURCE_KINDS: [&str; 7] = [
    "forbidden_dependency",
    "allowed_dependency",
    "forbidden_construct",
    "complete_assignment",
    "complete_external_scope",
    "symbol_placement",
    "boundary_types",
];
const ALLOWED_SOURCE_KINDS: [&str; 4] = [
    "forbidden_dependency",
    "external_dependency_scope",
    "symbol_placement",
    "boundary_types",
];
const EXACT_SOURCE_KINDS: [&str; 3] = ["external_dependency_scope", "symbol_placement", "boundary_types"];

fn texts(value: &Value) -> Vec<&str> {
    match value {
        Value::String(text) => vec![text.as_str()],
        Value::Array(items) => items.iter().filter_map(Value::as_str).collect(),
        _ => Vec::new(),
    }
}

/// Each held module reference of the contract: its pointer and its value (`module_references`
/// with `held`). A `forbidden_dependency` target of another target kind is not held.
fn held(contract: &Contract) -> Vec<(String, String)> {
    let Ok(root) = serde_json::from_slice::<Value>(&canonical_bytes(contract)) else {
        return Vec::new();
    };
    let mut found: Vec<(String, String)> = Vec::new();
    let mut add = |pointer: String, value: &Value, scalar: bool| {
        for (item, text) in texts(value).into_iter().enumerate() {
            let place = if scalar { pointer.clone() } else { format!("{pointer}/{item}") };
            found.push((place, text.to_owned()));
        }
    };
    let list = |value: &Value| value.as_array().cloned().unwrap_or_default();
    for (index, component) in list(&root["components"]).iter().enumerate() {
        for field in ["packages", "exact_modules", "public", "planned"] {
            add(format!("/components/{index}/{field}"), &component[field], false);
        }
        for (position, entry) in list(&component["requires"]).iter().enumerate() {
            let pointer = format!("/components/{index}/requires/{position}/through");
            add(pointer, &entry["through"], false);
        }
    }
    for (index, rule) in list(&root["rules"]).iter().enumerate() {
        let kind = rule["kind"].as_str().unwrap_or_default();
        let at = |field: &str| format!("/rules/{index}/{field}");
        if SOURCE_KINDS.contains(&kind) {
            add(at("source"), &rule["source"], true);
        }
        let module_target = rule.get("target_kind").is_none_or(|kind| kind == "module");
        if kind == "allowed_dependency" || (kind == "forbidden_dependency" && module_target) {
            add(at("target"), &rule["target"], true);
        }
        if ALLOWED_SOURCE_KINDS.contains(&kind) {
            add(at("allowed_sources"), &rule["allowed_sources"], false);
        }
        if EXACT_SOURCE_KINDS.contains(&kind) {
            add(at("exact_sources"), &rule["exact_sources"], false);
        }
        if kind == "sibling_isolation" {
            add(at("members"), &rule["members"], false);
        }
        for (item, grant) in list(&rule["module_object_grants"]).iter().enumerate() {
            for field in ["source_module", "target_module"] {
                let pointer = format!("/rules/{index}/module_object_grants/{item}/{field}");
                add(pointer, &grant[field], true);
            }
        }
    }
    let declarations = &root["declarations"];
    add("/declarations/public_api".to_owned(), &declarations["public_api"], false);
    add("/declarations/context_roots".to_owned(), &declarations["context_roots"], false);
    for (index, scope) in list(&declarations["review_scopes"]).iter().enumerate() {
        let pointer = format!("/declarations/review_scopes/{index}/subjects");
        add(pointer, &scope["subjects"], false);
    }
    for (index, owner) in list(&declarations["spot_owners"]).iter().enumerate() {
        add(format!("/declarations/spot_owners/{index}/owner"), &owner["owner"], true);
    }
    for (index, entity) in list(&declarations["uml"]["entities"]).iter().enumerate() {
        if entity["presence"] != "referenced" {
            let pointer = format!("/declarations/uml/entities/{index}/qualified_name");
            add(pointer, &entity["qualified_name"], true);
        }
    }
    found
}

/// The held references outside the namespace of the configuration (`reference.namespace`).
pub(crate) fn namespace(contract: &Contract, namespace: &str) -> Vec<Finding> {
    held(contract)
        .into_iter()
        .filter(|(_, value)| !in_scope(value.split(':').next().unwrap_or_default(), namespace))
        .map(|(pointer, value)| {
            let claim = format!("The reference is outside namespace {namespace}.");
            ("reference.namespace", pointer, value, claim)
        })
        .collect()
}

/// The `public` and `planned` entries that another component owns or that name an underscore
/// name (`reference.public_owner`, `reference.public_underscore`).
pub(crate) fn public(contract: &Contract) -> Vec<Finding> {
    let components = contract.components();
    let mut found = Vec::new();
    for (index, component) in components.iter().enumerate() {
        let lists = [("public", component.public()), ("planned", component.planned())];
        for (field, entries) in lists {
            for (item, entry) in entries.iter().flatten().enumerate() {
                let entry = entry.as_text();
                let pointer = format!("/components/{index}/{field}/{item}");
                let (module, name) = entry.split_once(':').unwrap_or((entry, ""));
                let mut owners = components.iter().enumerate().filter(|(_, c)| claims(c, module));
                let sole = matches!((owners.next(), owners.next()), (Some((at, _)), None) if at == index);
                if !sole {
                    let claim = "The public entry's module is not owned by this component.";
                    found.push(("reference.public_owner", pointer.clone(), entry.to_owned(), claim.to_owned()));
                }
                if name.starts_with('_') {
                    let claim = "Underscore names are never public.";
                    found.push(("reference.public_underscore", pointer, entry.to_owned(), claim.to_owned()));
                }
            }
        }
    }
    found
}

/// `(?:todo|tbd|placeholder)(?:\b|:)`, case-insensitive, at the start of `text`.
fn placeholder(text: &str) -> Option<usize> {
    ["placeholder", "todo", "tbd"].iter().find_map(|word| {
        let head = text.get(..word.len())?;
        let next = text.get(word.len()..)?.chars().next();
        (head.eq_ignore_ascii_case(word) && next.is_none_or(|c| !(c.is_alphanumeric() || c == '_')))
            .then_some(word.len())
    })
}

/// `(?:The )?\S+ <phrase> \S+\.` as a full, case-insensitive match.
fn repeats(text: &str, phrases: &[&str]) -> bool {
    let plain = |body: &str| {
        let Some(gap) = body.find(space) else {
            return false;
        };
        let (Some(rest), true) = (body.get(gap..).and_then(|r| r.strip_prefix(' ')), gap > 0) else {
            return false;
        };
        phrases.iter().any(|phrase| {
            let tail = rest
                .get(..phrase.len())
                .filter(|head| head.eq_ignore_ascii_case(phrase))
                .and_then(|_| rest.get(phrase.len()..))
                .and_then(|tail| tail.strip_prefix(' '));
            tail.is_some_and(|word| word.len() > 1 && word.ends_with('.') && !word.contains(space))
        })
    };
    let prefixed = text
        .get(..4)
        .filter(|head| head.eq_ignore_ascii_case("the "))
        .and_then(|_| text.get(4..));
    plain(text) || prefixed.is_some_and(plain)
}

/// The placeholder and repeated rationales of the rules and the `requires` entries
/// (`rationale_diagnostics`).
pub(crate) fn rationale(contract: &Contract) -> Vec<Finding> {
    let mut found = Vec::new();
    let mut judge = |text: &str, phrases: &[&str], pointer: String, subject: String| {
        let text = text.trim_matches(space);
        if repeats(text, phrases) {
            let claim = "The rationale repeats the rule without explaining why.".to_owned();
            found.push(("rationale.repeated", pointer, subject, claim));
        } else if placeholder(text).is_some() {
            let claim = "The rationale is a placeholder.".to_owned();
            found.push(("rationale.placeholder", pointer, subject, claim));
        }
    };
    for (index, rule) in contract.rules().iter().enumerate() {
        let head = archkeel_contract::head_of(rule);
        let pointer = format!("/rules/{index}/rationale");
        judge(head.rationale(), &["does not depend on"], pointer, head.id().as_text().to_owned());
    }
    for (index, component) in contract.components().iter().enumerate() {
        for (position, entry) in component.requires().iter().flatten().enumerate() {
            let pointer = format!("/components/{index}/requires/{position}/rationale");
            let subject = format!("{} -> {}", component.label().as_text(), entry.component().as_text());
            judge(entry.rationale(), &["depends on", "requires", "uses", "needs"], pointer, subject);
        }
    }
    found
}

/// The components that the architect decided without a responsibility that is not a placeholder
/// (`responsibility.missing`).
pub(crate) fn responsibility(contract: &Contract) -> Vec<Finding> {
    // A placeholder value is the whole text: the word, then nothing or one colon.
    let only_placeholder = |value: &str| {
        placeholder(value).is_some_and(|end| matches!(value.get(end..), Some("" | ":")))
    };
    let substantive = |component: &Component| {
        component.responsibilities().iter().any(|value| {
            let value = value.trim_matches(space);
            !value.is_empty() && !only_placeholder(value)
        })
    };
    contract
        .components()
        .iter()
        .enumerate()
        .filter(|(_, c)| *c.decided_by() == Some(DecidedBy::Architect) && !substantive(c))
        .map(|(index, component)| {
            let claim = "The architect-decided component has no substantive responsibility.";
            let pointer = format!("/components/{index}/responsibilities");
            ("responsibility.missing", pointer, component.label().as_text().to_owned(), claim.to_owned())
        })
        .collect()
}

#[cfg(test)]
#[path = "hygiene_refs_tests.rs"]
mod tests;
