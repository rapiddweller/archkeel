// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `declarations` object. Python reads it in three steps of `parse_contract`: the
//! capabilities before the components, the other records after them, and the four string lists
//! after the label checks. The functions here keep these three steps, so the first error of a
//! contract has the same kind in both parsers.

use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json, Object};
use crate::model::{ComponentLabel, ItemId, Package};
use crate::model_declarations::{
    BudgetName, Capability, Command, Compat, CouplingBudget, Declarations, FacadeBudget, FlowPath,
    MeasurementBudget, ModuleTarget, ReviewScope, SpotOwner,
};
use crate::model_uml::{GraphSchemaVersion, Target};
use crate::names::dotted_name;
use crate::paths::module_target_path;
use crate::read::{
    count, fields, listed_strings, nonempty_field, positive, present, record, repeats,
    strings_field, text,
};
use crate::uml::target;
use crate::version::{ContractVersion, Feature};
use crate::words::value_of;

const KEYS: [&str; 15] = [
    "capabilities",
    "review_scopes",
    "public_api",
    "public_api_provenance",
    "public_commands",
    "context_roots",
    "context_roots_provenance",
    "paths",
    "spot_owners",
    "compat",
    "measurement_budgets",
    "facade_budgets",
    "coupling_budgets",
    "modules",
    "uml",
];

/// The declarations object with only its known keys.
pub(crate) fn declarations_object(raw: &Json) -> Parsed<&Object> {
    fields(raw, &[], &KEYS, "contract.declarations")
}

/// `records(key)`: an absent key is empty, any value but an array is an error.
fn records<'a>(object: &'a Object, key: &str) -> Parsed<&'a [Json]> {
    match field(object, key) {
        None => Ok(&[]),
        Some(Json::Array(items)) => Ok(items),
        Some(_) => Err(invalid(format!(
            "contract.declarations.{key} must be an array"
        ))),
    }
}

fn each<T>(object: &Object, key: &str, parse: impl Fn(&Json, &str) -> Parsed<T>) -> Parsed<Vec<T>> {
    records(object, key)?
        .iter()
        .enumerate()
        .map(|(index, raw)| parse(raw, &format!("{key}[{index}]")))
        .collect()
}

/// Step 1: the capabilities.
pub(crate) fn capabilities(object: &Object) -> Parsed<Vec<Capability>> {
    each(object, "capabilities", |raw, label| {
        let (item, id, provenance) = record(raw, &["name", "label", "review_order"], &[], label)?;
        Ok(Capability {
            review_order: positive(
                present(item, "review_order", label)?,
                &format!("{label}.review_order"),
            )?,
            name: nonempty_field(item, "name", label)?,
            label: nonempty_field(item, "label", label)?,
            id,
            provenance,
        })
    })
}

/// The records of step 2.
pub(crate) struct Records {
    review_scopes: Vec<ReviewScope>,
    public_commands: Vec<Command>,
    paths: Vec<FlowPath>,
    spot_owners: Vec<SpotOwner>,
    compat: Vec<Compat>,
    measurement_budgets: Vec<MeasurementBudget>,
    facade_budgets: Option<Vec<FacadeBudget>>,
    coupling_budgets: Option<Vec<CouplingBudget>>,
    modules: Option<Vec<ModuleTarget>>,
    pub(crate) uml: Option<Target>,
}

/// The ids of step 2 that the contract ID check counts.
pub(crate) fn record_ids(records: &Records) -> Vec<&ItemId> {
    let scopes = records.review_scopes.iter().map(|item| &item.id);
    let commands = records.public_commands.iter().map(|item| &item.id);
    let paths = records.paths.iter().map(|item| &item.id);
    let owners = records.spot_owners.iter().map(|item| &item.id);
    scopes.chain(commands).chain(paths).chain(owners).collect()
}

/// The budgets of step 2, for the interface budget check.
pub(crate) fn budgets(records: &Records) -> (&[FacadeBudget], &[CouplingBudget]) {
    (
        records.facade_budgets.as_deref().unwrap_or_default(),
        records.coupling_budgets.as_deref().unwrap_or_default(),
    )
}

fn optional_records<T>(
    object: &Object,
    key: &str,
    parse: impl Fn(&Json, &str) -> Parsed<T>,
) -> Parsed<Option<Vec<T>>> {
    if has(object, key) {
        each(object, key, parse).map(Some)
    } else {
        Ok(None)
    }
}

/// Step 2: the records after the components, in the order of Python.
pub(crate) fn later_records(object: &Object, version: ContractVersion) -> Parsed<Records> {
    let review_scopes = each(object, "review_scopes", review_scope)?;
    let public_commands = each(object, "public_commands", command)?;
    let paths = each(object, "paths", flow_path)?;
    let spot_owners = each(object, "spot_owners", spot_owner)?;
    let compat = each(object, "compat", compat)?;
    let modules_of_compat: Vec<&Package> = compat.iter().map(|item| &item.module).collect();
    if repeats(&modules_of_compat) {
        return Err(invalid(
            "contract.declarations.compat modules must be unique",
        ));
    }
    let measurement_budgets = each(object, "measurement_budgets", measurement_budget)?;
    let names: Vec<BudgetName> = measurement_budgets.iter().map(|item| item.name).collect();
    if repeats(&names) {
        return Err(invalid(
            "contract.declarations.measurement_budgets repeats a name",
        ));
    }
    let facade_budgets = optional_records(object, "facade_budgets", facade_budget)?;
    let coupling_budgets = optional_records(object, "coupling_budgets", coupling_budget)?;
    let modules = optional_records(object, "modules", module_target)?;
    let paths_of_modules: Vec<&crate::model::SourcePath> =
        modules.iter().flatten().map(|item| &item.path).collect();
    if repeats(&paths_of_modules) {
        return Err(invalid("contract.declarations.modules repeats a path"));
    }
    let uml = uml(object, version)?;
    Ok(Records {
        review_scopes,
        public_commands,
        paths,
        spot_owners,
        compat,
        measurement_budgets,
        facade_budgets,
        coupling_budgets,
        modules,
        uml,
    })
}

fn uml(object: &Object, version: ContractVersion) -> Parsed<Option<Target>> {
    let Some(raw) = field(object, "uml") else {
        return Ok(None);
    };
    if !crate::version::supports(version, Feature::Uml) {
        return Err(invalid(
            "UML declarations require contract schema_version 2.2.0",
        ));
    }
    let parsed = target(raw)?;
    let planned = crate::version::supports(version, Feature::PlannedComponentOwner);
    if parsed.schema_version == GraphSchemaVersion::V1_3 && !planned {
        return Err(invalid(
            "UML schema_version 1.3.0 requires contract schema_version 2.4.0",
        ));
    }
    Ok(Some(parsed))
}

/// Step 3: the four string lists, after the label checks, and the whole declarations.
pub(crate) fn finish(
    object: &Object,
    capabilities: Vec<Capability>,
    records: Records,
) -> Parsed<Declarations> {
    let label = "contract.declarations";
    Ok(Declarations {
        capabilities,
        review_scopes: records.review_scopes,
        public_api: listed_strings(object, "public_api", label)?,
        public_api_provenance: listed_strings(object, "public_api_provenance", label)?,
        public_commands: records.public_commands,
        context_roots: listed_strings(object, "context_roots", label)?,
        context_roots_provenance: listed_strings(object, "context_roots_provenance", label)?,
        paths: records.paths,
        spot_owners: records.spot_owners,
        compat: records.compat,
        measurement_budgets: records.measurement_budgets,
        facade_budgets: records.facade_budgets,
        coupling_budgets: records.coupling_budgets,
        modules: records.modules,
        uml: records.uml,
    })
}

fn review_scope(raw: &Json, label: &str) -> Parsed<ReviewScope> {
    let (item, id, provenance) = record(raw, &["label", "parent_id", "subjects"], &[], label)?;
    Ok(ReviewScope {
        label: nonempty_field(item, "label", label)?,
        parent_id: nonempty_field(item, "parent_id", label)?,
        subjects: strings_field(item, "subjects", label, true)?,
        id,
        provenance,
    })
}

fn command(raw: &Json, label: &str) -> Parsed<Command> {
    let (item, id, provenance) = record(raw, &["command", "description"], &[], label)?;
    Ok(Command {
        command: nonempty_field(item, "command", label)?,
        description: nonempty_field(item, "description", label)?,
        id,
        provenance,
    })
}

fn flow_path(raw: &Json, label: &str) -> Parsed<FlowPath> {
    let (item, id, provenance) = record(raw, &["label", "kind", "steps"], &[], label)?;
    let kind_text = text(present(item, "kind", label)?, &format!("{label}.kind"))?;
    let kind = value_of(kind_text).ok_or_else(|| invalid(format!("{label}.kind is invalid")))?;
    Ok(FlowPath {
        label: nonempty_field(item, "label", label)?,
        steps: strings_field(item, "steps", label, true)?,
        kind,
        id,
        provenance,
    })
}

fn spot_owner(raw: &Json, label: &str) -> Parsed<SpotOwner> {
    let (item, id, provenance) = record(raw, &["label", "owner", "responsibility"], &[], label)?;
    Ok(SpotOwner {
        label: nonempty_field(item, "label", label)?,
        owner: nonempty_field(item, "owner", label)?,
        responsibility: nonempty_field(item, "responsibility", label)?,
        id,
        provenance,
    })
}

fn compat(raw: &Json, label: &str) -> Parsed<Compat> {
    let item = fields(raw, &["module", "target", "lifetime"], &[], label)?;
    let module = text(present(item, "module", label)?, &format!("{label}.module"))?;
    let target = text(present(item, "target", label)?, &format!("{label}.target"))?;
    if !dotted_name(module) || !dotted_name(target) {
        return Err(invalid(format!(
            "{label}.module and target must be dotted module names"
        )));
    }
    if module == target {
        return Err(invalid(format!("{label}.module and target must differ")));
    }
    let lifetime = match present(item, "lifetime", label)? {
        Json::Text(word) => value_of(word),
        _ => None,
    }
    .ok_or_else(|| invalid(format!("{label}.lifetime must be permanent or migration")))?;
    Ok(Compat {
        module: Package(module.to_owned()),
        target: Package(target.to_owned()),
        lifetime,
    })
}

fn measurement_budget(raw: &Json, label: &str) -> Parsed<MeasurementBudget> {
    let item = fields(raw, &["name", "provenance"], &[], label)?;
    let name_text = text(present(item, "name", label)?, &format!("{label}.name"))?;
    let name = value_of(name_text).ok_or_else(|| {
        invalid(format!(
            "{label}.name is not a supported measurement budget"
        ))
    })?;
    Ok(MeasurementBudget {
        name,
        provenance: strings_field(item, "provenance", label, true)?,
    })
}

fn facade_budget(raw: &Json, label: &str) -> Parsed<FacadeBudget> {
    let item = fields(raw, &["component", "max_names", "provenance"], &[], label)?;
    Ok(FacadeBudget {
        component: nonempty_field(item, "component", label)?,
        max_names: count(
            present(item, "max_names", label)?,
            &format!("{label}.max_names"),
        )?,
        provenance: strings_field(item, "provenance", label, true)?,
    })
}

fn coupling_budget(raw: &Json, label: &str) -> Parsed<CouplingBudget> {
    let item = fields(
        raw,
        &["source", "target", "max_names", "provenance"],
        &[],
        label,
    )?;
    Ok(CouplingBudget {
        source: nonempty_field::<ComponentLabel>(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        max_names: count(
            present(item, "max_names", label)?,
            &format!("{label}.max_names"),
        )?,
        provenance: strings_field(item, "provenance", label, true)?,
    })
}

fn module_target(raw: &Json, label: &str) -> Parsed<ModuleTarget> {
    let item = fields(raw, &["path", "responsibility"], &[], label)?;
    let path: String = nonempty_field(item, "path", label)?;
    if !module_target_path(&path) {
        return Err(invalid(format!(
            "{label}.path must be a repository-relative source path"
        )));
    }
    let responsibility: String = nonempty_field(item, "responsibility", label)?;
    if responsibility.contains(['\r', '\n']) {
        return Err(invalid(format!(
            "{label}.responsibility must be one sentence on one line"
        )));
    }
    Ok(ModuleTarget {
        path: crate::model::SourcePath(path),
        responsibility,
    })
}
