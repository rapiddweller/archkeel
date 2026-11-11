// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `parse_contract`: the checks run in the order of the Python parser, so that the first error
//! has the same kind in both parsers.

use sha2::{Digest, Sha256};

use crate::budgets::check_interface_budgets;
use crate::component::parse_component;
use crate::declarations::{
    budgets, capabilities, declarations_object, finish, later_records, record_ids, Records,
};
use crate::document::{classify, Contract, ParsedContract};
use crate::error::{invalid, ErrorKind, ParseError, Parsed};
use crate::graph::check_declared_graph;
use crate::json::{read, Json};
use crate::model::{Component, ComponentLabel, ContractDigest, ItemId};
use crate::model_declarations::Capability;
use crate::read::{fields, given, nonempty, present, repeats};
use crate::rule::{head_of, Rule};
use crate::rules::{check_boundary_features, check_rule_features, parse_rule, rule_kind};
use crate::version::{version_of, ContractVersion};

/// Parse contract bytes. The bytes are the whole file; this crate reads no file. A contract whose
/// components mount inside contracts comes back as `ParsedContract::NeedsTree`: it is complete
/// only after the tree assembly of the inside contracts has checked the mounted contracts.
pub fn parse(bytes: &[u8]) -> Result<ParsedContract, ParseError> {
    parse_file(bytes).map(classify)
}

/// Parse the bytes of one contract file, without its inside tree. The digest of the contract is
/// the SHA-256 of these bytes. The tree assembly reads each file of the tree with this function.
pub(crate) fn parse_file(bytes: &[u8]) -> Result<Contract, ParseError> {
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
    let declared = given(root, "declarations")
        .map(declarations_object)
        .transpose()?;
    let capabilities = declared.map(capabilities).transpose()?.unwrap_or_default();
    let components = components_raw
        .iter()
        .enumerate()
        .map(|(index, value)| parse_component(value, &format!("components[{index}]"), version))
        .collect::<Parsed<Vec<_>>>()?;
    check_namespaces(&components)?;
    let records = declared
        .map(|object| later_records(object, version))
        .transpose()?;
    let rules = parse_rules(version, rules_raw)?;
    check_labels(&components)?;
    check_rule_components(&components, &rules)?;
    let (facades, pairs) = records.as_ref().map(budgets).unwrap_or_default();
    check_interface_budgets(&components, &rules, facades, pairs)?;
    check_unique_ids(&capabilities, &components, records.as_ref(), &rules)?;
    let schema = given(root, "$schema")
        .map(|value| nonempty(value, "contract.$schema"))
        .transpose()?;
    let declarations = match (declared, records) {
        (Some(object), Some(records)) => Some(finish(object, capabilities, records)?),
        _ => None,
    };
    if let Some(declarations) = &declarations {
        if let Some(target) = &declarations.uml {
            check_declared_graph(&components, &rules, declarations, target)?;
        }
    }
    Ok(Contract {
        version,
        schema,
        components,
        rules,
        declarations,
        digest: digest_of(bytes),
    })
}

/// The rule kinds, the feature gates, each rule and the gates of the boundary positions.
fn parse_rules(version: ContractVersion, rules_raw: &[Json]) -> Parsed<Vec<Rule>> {
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
    check_boundary_features(version, &rules)?;
    Ok(rules)
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

/// Each id of the contract is unique: capabilities, components, the records of the declarations,
/// rules, and the entities and relationships of the UML Target.
fn check_unique_ids(
    capabilities: &[Capability],
    components: &[Component],
    records: Option<&Records>,
    rules: &[Rule],
) -> Parsed<()> {
    let mut ids: Vec<&ItemId> = capabilities.iter().map(|item| &item.id).collect();
    ids.extend(components.iter().map(|component| &component.id));
    if let Some(records) = records {
        ids.extend(record_ids(records));
    }
    ids.extend(rules.iter().map(|rule| &head_of(rule).id));
    if let Some(target) = records.and_then(|records| records.uml.as_ref()) {
        ids.extend(target.entities.iter().map(|entity| &entity.id));
        ids.extend(target.relationships.iter().map(|edge| &edge.id));
    }
    if repeats(&ids) {
        return Err(invalid("duplicate contract ID"));
    }
    Ok(())
}

#[cfg(test)]
#[path = "contract_tests.rs"]
mod tests;
