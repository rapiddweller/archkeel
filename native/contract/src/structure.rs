// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The structure rules: assignment, layout, external scope, requires, layers, cycles, interfaces
//! and sibling isolation.

use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json, Object};
use crate::model::{
    CompleteRequires, ComponentLabel, CycleLevel, InterfaceBoundary, LayerOrder, ModuleObjectGrant,
    NoComponentCycles, RootLayout, SiblingIsolation, SourceRule,
};
use crate::names::dotted_name;
use crate::read::{
    contract_strings, fields, flag, given, nonempty, nonempty_field, present, repeats, rule_record,
    strings_field, text,
};
use crate::words::value_of;

/// `complete_assignment` and `complete_external_scope`.
pub(crate) fn source_rule(raw: &Json, label: &str) -> Parsed<SourceRule> {
    let (item, head) = rule_record(raw, &["source"], &[], label)?;
    let source = nonempty_field(item, "source", label)?;
    Ok(SourceRule { head, source })
}

/// `root_layout` with `validate_layout_rule`: each child is one immediate child of the root.
pub(crate) fn root_layout(raw: &Json, label: &str) -> Parsed<RootLayout> {
    let (item, head) = rule_record(raw, &["root", "allowed_children"], &[], label)?;
    let root = nonempty_field(item, "root", label)?;
    let allowed_children = strings_field(item, "allowed_children", label, false)?;
    let outside = allowed_children.iter().position(|child| {
        let (parent, name) = child.rsplit_once('.').unwrap_or(("", child));
        parent != root || name.is_empty()
    });
    if let Some(index) = outside {
        return Err(invalid(format!(
            "{label}.allowed_children[{index}] must be exactly one immediate child of root"
        )));
    }
    Ok(RootLayout {
        head,
        root,
        allowed_children,
    })
}

pub(crate) fn complete_requires(raw: &Json, label: &str) -> Parsed<CompleteRequires> {
    let (item, head) = rule_record(raw, &[], &["include_type_checking"], label)?;
    let include_type_checking = flag(item, "include_type_checking", true, label)?;
    Ok(CompleteRequires {
        head,
        include_type_checking,
    })
}

fn labels(values: Vec<String>) -> Vec<ComponentLabel> {
    values.into_iter().map(ComponentLabel).collect()
}

pub(crate) fn layer_order(raw: &Json, label: &str) -> Parsed<LayerOrder> {
    let (item, head) = rule_record(raw, &["layers"], &["components"], label)?;
    let layers = strings_field(item, "layers", label, true)?;
    let components = if has(item, "components") {
        Some(labels(strings_field(item, "components", label, true)?))
    } else {
        None
    };
    Ok(LayerOrder {
        head,
        layers,
        components,
    })
}

pub(crate) fn no_component_cycles(raw: &Json, label: &str) -> Parsed<NoComponentCycles> {
    let (item, head) = rule_record(raw, &[], &["level", "components"], label)?;
    let level = match given(item, "level") {
        None => CycleLevel::Component,
        Some(value) => {
            let level_label = format!("{label}.level");
            let word = nonempty(value, &level_label)?;
            value_of(&word)
                .ok_or_else(|| invalid(format!("{level_label} must be component or module")))?
        }
    };
    let components = given(item, "components")
        .map(|value| contract_strings(value, &format!("{label}.components"), true))
        .transpose()?
        .map(labels);
    Ok(NoComponentCycles {
        head,
        level,
        components,
    })
}

fn grants(item: &Object, label: &str) -> Parsed<Option<Vec<ModuleObjectGrant>>> {
    let grants_label = format!("{label}.module_object_grants");
    let entries = match field(item, "module_object_grants") {
        None => return Ok(None),
        Some(Json::Array(entries)) => entries,
        Some(_) => return Err(invalid(format!("{grants_label} must be an array"))),
    };
    let mut grants: Vec<ModuleObjectGrant> = Vec::new();
    for (index, raw) in entries.iter().enumerate() {
        let entry_label = format!("{grants_label}[{index}]");
        let entry = fields(raw, &["source_module", "target_module"], &[], &entry_label)?;
        let mut modules = Vec::new();
        for key in ["source_module", "target_module"] {
            let module = text(
                present(entry, key, &entry_label)?,
                &format!("{entry_label}.{key}"),
            )?;
            modules.push(module.to_owned());
        }
        if let Some(position) = modules.iter().position(|module| !dotted_name(module)) {
            let key = if position == 0 {
                "source_module"
            } else {
                "target_module"
            };
            return Err(invalid(format!(
                "{entry_label}.{key} must be a dotted module name"
            )));
        }
        let [source_module, target_module]: [String; 2] = modules
            .try_into()
            .map_err(|_| invalid(format!("{entry_label} needs two modules")))?;
        grants.push(ModuleObjectGrant {
            source_module,
            target_module,
        });
    }
    if repeats(&grants) {
        return Err(invalid(format!(
            "{grants_label} must contain unique entries"
        )));
    }
    Ok(Some(grants))
}

pub(crate) fn interface_boundary(raw: &Json, label: &str) -> Parsed<InterfaceBoundary> {
    let (item, head) = rule_record(
        raw,
        &[],
        &["include_type_checking", "module_object_grants"],
        label,
    )?;
    let include_type_checking = flag(item, "include_type_checking", true, label)?;
    let module_object_grants = grants(item, label)?;
    Ok(InterfaceBoundary {
        head,
        include_type_checking,
        module_object_grants,
    })
}

pub(crate) fn sibling_isolation(raw: &Json, label: &str) -> Parsed<SiblingIsolation> {
    let (item, head) = rule_record(raw, &["members"], &["include_type_checking"], label)?;
    let members = strings_field(item, "members", label, true)?;
    if members.len() < 2 {
        return Err(invalid(format!(
            "{label}.members must name at least two peers"
        )));
    }
    let include_type_checking = flag(item, "include_type_checking", true, label)?;
    Ok(SiblingIsolation {
        head,
        members,
        include_type_checking,
    })
}
