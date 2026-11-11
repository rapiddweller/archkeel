// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `parse_contract`: the checks run in the order of the Python parser, so that the first error
//! has the same kind in both parsers.

use sha2::{Digest, Sha256};

use crate::component::parse_component;
use crate::error::{invalid, unsupported, ErrorKind, ParseError, Parsed, Unported};
use crate::json::{read, Json};
use crate::model::{Component, ComponentLabel, Contract, ContractDigest, ItemId, Rule};
use crate::read::{fields, given, nonempty, present, repeats};
use crate::rules::{check_rule_features, head_of, parse_rule, rule_kind};
use crate::version::{version_of, ContractVersion};

/// Parse contract bytes into a typed contract. The bytes are the whole file; this crate reads no
/// file. The digest of the contract is the SHA-256 of these bytes.
pub fn parse(bytes: &[u8]) -> Result<Contract, ParseError> {
    let raw = read(bytes)?;
    let root = fields(
        &raw,
        &["schema_version", "components", "rules"],
        &["$schema", "declarations"],
        "contract",
    )?;
    let version = schema_version(present(root, "schema_version", "contract")?)?;
    let (Json::Array(components_raw), Json::Array(rules_raw)) = (
        present(root, "components", "contract")?,
        present(root, "rules", "contract")?,
    ) else {
        return Err(invalid("contract components and rules must be arrays"));
    };
    if given(root, "declarations").is_some() {
        return Err(unsupported(
            Unported::Declarations,
            "contract.declarations is not parsed in Rust yet (slice 0c-2)",
        ));
    }
    let components = components_raw
        .iter()
        .enumerate()
        .map(|(index, value)| parse_component(value, &format!("components[{index}]"), version))
        .collect::<Parsed<Vec<_>>>()?;
    check_namespaces(&components)?;
    let kinds = rules_raw
        .iter()
        .enumerate()
        .map(|(index, value)| rule_kind(value, &format!("rules[{index}]")))
        .collect::<Parsed<Vec<_>>>()?;
    check_rule_features(version, rules_raw, &kinds)?;
    let rules = rules_raw
        .iter()
        .zip(&kinds)
        .enumerate()
        .map(|(index, (value, kind))| parse_rule(value, &format!("rules[{index}]"), *kind))
        .collect::<Parsed<Vec<_>>>()?;
    check_labels(&components)?;
    check_rule_components(&components, &rules)?;
    check_unique_ids(&components, &rules)?;
    let schema = given(root, "$schema")
        .map(|value| nonempty(value, "contract.$schema"))
        .transpose()?;
    Ok(Contract {
        version,
        schema,
        components,
        rules,
        digest: digest_of(bytes),
    })
}

/// The SHA-256 of bytes in lower-case hex.
pub(crate) fn digest_of(bytes: &[u8]) -> ContractDigest {
    let digest = Sha256::digest(bytes);
    ContractDigest(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

/// Any failure to read the version is a version error, as in Python.
fn schema_version(raw: &Json) -> Parsed<ContractVersion> {
    let text = match raw {
        Json::Text(text) => Some(text.as_str()),
        _ => None,
    };
    text.and_then(version_of).ok_or_else(|| ParseError {
        kind: ErrorKind::Version,
        message: format!("contract.schema_version {raw:?} is not a known version"),
    })
}

/// A namespace must be a package of exactly one component.
fn check_namespaces(components: &[Component]) -> Parsed<()> {
    for component in components {
        let Some(namespace) = &component.namespace else {
            continue;
        };
        let owners = components
            .iter()
            .filter(|other| other.packages.contains(namespace))
            .count();
        if owners != 1 {
            return Err(invalid(format!(
                "component {:?}.namespace must identify one component package",
                component.label.0
            )));
        }
    }
    Ok(())
}

fn input(pointer: String, message: String) -> ParseError {
    ParseError {
        kind: ErrorKind::Input,
        message: format!("{pointer}: {message}"),
    }
}

/// A label is unique, and each `requires` entry names a label of this contract.
fn check_labels(components: &[Component]) -> Parsed<()> {
    let labels: Vec<&ComponentLabel> = components
        .iter()
        .map(|component| &component.label)
        .collect();
    for (index, component) in components.iter().enumerate() {
        if labels
            .iter()
            .take(index)
            .any(|seen| **seen == component.label)
        {
            return Err(input(
                format!("/components/{index}/label"),
                format!(
                    "component label {:?} is not unique in this contract",
                    component.label.0
                ),
            ));
        }
        let entries = component.requires.iter().flatten().enumerate();
        for (position, entry) in entries {
            if !labels.contains(&&entry.component) {
                return Err(input(
                    format!("/components/{index}/requires/{position}/component"),
                    format!(
                        "{:?} is not a component label in this contract",
                        entry.component.0
                    ),
                ));
            }
        }
    }
    Ok(())
}

/// The `components` of a cycle rule or a layer rule name declared components.
fn check_rule_components(components: &[Component], rules: &[Rule]) -> Parsed<()> {
    for (index, rule) in rules.iter().enumerate() {
        let named = match rule {
            Rule::NoComponentCycles(rule) => rule.components.as_ref(),
            Rule::LayerOrder(rule) => rule.components.as_ref(),
            _ => None,
        };
        let unknown = named.into_iter().flatten().find(|label| {
            !components
                .iter()
                .any(|component| component.label == **label)
        });
        if let Some(label) = unknown {
            return Err(invalid(format!(
                "rules[{index}].components names no declared component: {:?}",
                label.0
            )));
        }
    }
    Ok(())
}

/// Each id of a component and of a rule is unique in the contract.
fn check_unique_ids(components: &[Component], rules: &[Rule]) -> Parsed<()> {
    let ids: Vec<&ItemId> = components
        .iter()
        .map(|component| &component.id)
        .chain(rules.iter().map(|rule| &head_of(rule).id))
        .collect();
    if repeats(&ids) {
        return Err(invalid("duplicate contract ID"));
    }
    Ok(())
}

#[cfg(test)]
#[path = "contract_tests.rs"]
mod tests;
