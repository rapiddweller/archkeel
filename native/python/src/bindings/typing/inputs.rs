// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Signals whose inputs are already collected records. This module does not collect calls.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass, Signal};
use archkeel_facts::Record;
use serde_json::Value;

use super::{data, fact, Collector};
use crate::bindings::scan::{input_array as array, Result, Scan};
use crate::module::EvidenceMap;

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("invalid signal input {key}"))
}

fn strings(scan: &mut Scan, value: &Value, key: &str) -> Result<Vec<String>> {
    let mut result = Vec::new();
    value
        .get(key)
        .ok_or_else(|| format!("missing {key} array"))?;
    for value in array(value, key)? {
        scan.tick(1)?;
        let value = value.as_str().ok_or("invalid string array entry")?;
        scan.tick(value.len())?;
        result.push(value.into());
    }
    Ok(result)
}

impl Collector<'_> {
    pub(super) fn dynamic(&mut self, scan: &mut Scan, input: &Value) -> Result<()> {
        for call in array(input, "calls")? {
            scan.tick(1)?;
            let call_data = call.get("data").ok_or("call data unseen")?;
            let expression = text(call_data, "expression")?;
            let Some(signal) = dynamic_target(scan, call_data)? else {
                continue;
            };
            let owner = text(call_data, "source_scope")?;
            let id = text(call, "id")?;
            let evidence_ids = retained_evidence(scan, call, &self.evidence)?;
            scan.tick(owner.len().saturating_add(expression.len()))?;
            let mut data = data(owner, signal);
            data.expression = Some(expression.into());
            self.keep(
                scan,
                Record {
                    id: FactId::new(stable_id(
                        "TYPE",
                        &[Part::Text(id), Part::Text(signal.as_str())],
                    )),
                    evidence_class: EvidenceClass::Fact,
                    area: Area::TypeArchitecture,
                    title: format!("{owner} uses {expression}"),
                    subjects: vec![owner.into()],
                    evidence_ids,
                    fact_ids: vec![FactId::new(id)],
                    data: fact(data),
                },
            )?;
        }
        Ok(())
    }

    pub(super) fn boundaries(&mut self, scan: &mut Scan, input: &Value) -> Result<()> {
        let mut used = BTreeSet::new();
        for import in array(input, "imports")? {
            scan.tick(1)?;
            let data = import.get("data").ok_or("import data unseen")?;
            if text(data, "source_package")? == text(data, "target_package")? {
                continue;
            }
            let symbol = match data.get("symbol") {
                Some(Value::Null) => "",
                Some(Value::String(value)) => value,
                _ => return Err("invalid import symbol".into()),
            };
            if symbol.is_empty() {
                continue;
            }
            let module = text(data, "target_module")?;
            scan.tick(module.len().saturating_add(symbol.len()))?;
            used.insert(format!("{module}.{symbol}"));
        }
        let mut by_name = BTreeMap::new();
        for symbol in array(input, "symbols")? {
            scan.tick(1)?;
            let data = symbol.get("data").ok_or("symbol data unseen")?;
            by_name.insert(text(data, "qualified_name")?, symbol);
        }
        for name in used {
            scan.tick(1)?;
            let Some(symbol) = by_name.get(name.as_str()) else {
                continue;
            };
            let signature = symbol.get("data").ok_or("symbol signature unseen")?;
            if !matches!(
                signature.get("symbol_category").and_then(Value::as_str),
                Some("function" | "method")
            ) {
                continue;
            }
            let mut missing = missing_positions(scan, signature)?;
            if missing.is_empty() {
                continue;
            }
            scan.tick(missing.len())?;
            let mut parts = vec![Part::Text(&name), Part::Text("missing-boundary-annotation")];
            parts.extend(missing.iter().map(|n| Part::Text(n)));
            let id = stable_id("TYPE", &parts);
            missing.sort();
            let mut data = data(&name, Signal::MissingCrossPackageAnnotation);
            data.positions = Some(missing);
            let mut evidence_ids: Vec<_> = strings(scan, symbol, "evidence_ids")?
                .into_iter()
                .map(EvidenceId::new)
                .collect();
            evidence_ids.sort_by(|a, b| a.as_str().cmp(b.as_str()));
            evidence_ids.dedup();
            self.keep(
                scan,
                Record {
                    id: FactId::new(id),
                    evidence_class: EvidenceClass::Fact,
                    area: Area::TypeArchitecture,
                    title: format!("{name} has unannotated cross-package boundary positions"),
                    subjects: vec![name],
                    evidence_ids,
                    fact_ids: vec![FactId::new(text(symbol, "id")?)],
                    data: fact(data),
                },
            )?;
        }
        Ok(())
    }
}

fn dynamic_target(scan: &mut Scan, call: &Value) -> Result<Option<Signal>> {
    call.get("targets").ok_or("call targets unseen")?;
    for target in array(call, "targets")? {
        scan.tick(1)?;
        let signal = match target.as_str().ok_or("call target unseen")? {
            "typing.cast" | "typing_extensions.cast" => Some(Signal::CastCall),
            "builtins.getattr" => Some(Signal::GetattrCall),
            "builtins.hasattr" => Some(Signal::HasattrCall),
            "builtins.eval" => Some(Signal::EvalCall),
            "builtins.exec" => Some(Signal::ExecCall),
            "builtins.__import__" | "importlib.import_module" => Some(Signal::DynamicImport),
            _ => None,
        };
        if signal.is_some() {
            return Ok(signal);
        }
    }
    Ok(None)
}

fn retained_evidence(
    scan: &mut Scan,
    call: &Value,
    evidence: &EvidenceMap,
) -> Result<Vec<EvidenceId>> {
    let mut ids = Vec::new();
    for id in strings(scan, call, "evidence_ids")? {
        scan.tick(1)?;
        if evidence.contains_key(&id) {
            ids.push(EvidenceId::new(id));
        }
    }
    ids.sort_by(|a, b| a.as_str().cmp(b.as_str()));
    ids.dedup();
    Ok(ids)
}

fn missing_positions(scan: &mut Scan, signature: &Value) -> Result<Vec<String>> {
    let mut missing = Vec::new();
    for parameter in array(signature, "parameters")? {
        scan.tick(1)?;
        if parameter
            .get("annotation")
            .ok_or("parameter annotation unseen")?
            .is_null()
        {
            missing.push(text(parameter, "name")?.into());
        }
    }
    if signature.get("returns").is_none_or(Value::is_null) {
        missing.push("return".into());
    }
    Ok(missing)
}
