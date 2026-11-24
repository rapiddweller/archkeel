// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts directory of one configuration, written from the raw files of the driver (AD-1047).

use archkeel_facts::type_reach::{Field, Unavailable};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};

use std::path::Path;

/// Replace each id of a record by its text (`ids`), or each text by an id of a new table (`!ids`); `map`
/// decides. In a record every number is an id, except `line`; see `tools/rustc-facts/src/out.rs`.
pub(super) fn recode(record: &mut Value, ids: bool, map: &mut impl FnMut(&Value) -> Value) {
    let Some(fields) = record.as_object_mut() else {
        return;
    };
    let kept = |name: &String| name != "line" && name != "k";
    let hit = |v: &Value| if ids { v.is_number() } else { v.is_string() };
    for (_, field) in fields.iter_mut().filter(|(name, _)| kept(name)) {
        match field {
            Value::Array(all) => all.iter_mut().filter(|v| hit(v)).for_each(|v| *v = map(v)),
            other if hit(other) => *other = map(other),
            _ => {}
        }
    }
}

/// The build line and the records of a file, each with its ids resolved to text. `None` when the file
/// has no `end` record, or the count of that record is wrong.
pub(super) fn load(text: &str) -> Option<(String, Vec<String>)> {
    let lines: Vec<&str> = text.lines().collect();
    let end: Value = serde_json::from_str(lines.last()?).ok()?;
    let table: Value = serde_json::from_str(lines.get(1)?).ok()?;
    if end.get("lines")?.as_u64()? + 1 != lines.len() as u64 {
        return None;
    }
    let names = table.get("v")?.as_array()?;
    let resolve = &mut |id: &Value| {
        id.as_u64()
            .and_then(|n| names.get(n as usize))
            .cloned()
            .unwrap_or(Value::Null)
    };
    let mut records = Vec::new();
    for line in lines.get(2..lines.len() - 1)? {
        let mut record: Value = serde_json::from_str(line).ok()?;
        recode(&mut record, true, resolve);
        records.push(record.to_string());
    }
    Some((lines.first()?.to_string(), records))
}

/// The union of the records of `base` and of the files of `extras`: one file with the build line of
/// `base`, one copy of each record, one string table. A fact is only ever added, so a union never
/// drops a gap that a unit alone would keep.
pub(super) fn merge(base: &str, extras: &[&str]) -> Option<String> {
    let (build, mut all) = load(base)?;
    for extra in extras {
        all.extend(load(extra)?.1);
    }
    let (mut ids, mut names): (HashMap<String, u64>, Vec<Value>) = (HashMap::new(), Vec::new());
    let mut intern = |text: &Value| {
        let (next, key) = (
            names.len() as u64,
            text.as_str().unwrap_or_default().to_string(),
        );
        let id = *ids.entry(key).or_insert(next);
        if id == next {
            names.push(text.clone());
        }
        Value::from(id)
    };
    let mut out = BTreeSet::new();
    for line in all {
        let mut record: Value = serde_json::from_str(&line).ok()?;
        recode(&mut record, false, &mut intern);
        out.insert(record.to_string());
    }
    let table = serde_json::json!({"k": "str", "v": names}).to_string();
    let count = out.len() + 2;
    let records: Vec<String> = out.into_iter().collect();
    Some(format!(
        "{build}\n{table}\n{}\n{{\"k\":\"end\",\"lines\":{count}}}\n",
        records.join("\n")
    ))
}

/// The unit that holds the library code of a test unit: the one unit of the same crate that is no
/// test build, or the one of them that is a library.
pub(super) fn base_of<'a>(test: &str, raw: &'a BTreeMap<String, String>) -> Option<&'a String> {
    let same = |name: &&String| !name.ends_with("-test") && crate_of(name) == crate_of(test);
    let mut found: Vec<&String> = raw.keys().filter(same).collect();
    if found.len() > 1 {
        found.retain(|name| {
            raw[*name]
                .lines()
                .next()
                .is_some_and(|b| b.contains("\"lib\""))
        });
    }
    (found.len() == 1).then(|| found[0])
}

/// Write the facts directory of one configuration from the raw files of the driver. The records of a
/// test unit go into the file of its base unit; the test unit keeps its build line (AD-1047).
pub(super) fn compact(
    raw_dir: &Path,
    out: &Path,
    units: &BTreeSet<String>,
) -> Result<(), Unavailable> {
    let _ = std::fs::remove_dir_all(out);
    let broken = |unit: &str| Unavailable::BindingMismatch(Field::End(unit.to_string()));
    std::fs::create_dir_all(out).map_err(|_| broken(""))?;
    let mut raw = BTreeMap::new();
    for unit in units {
        let text = std::fs::read_to_string(raw_dir.join(format!("{unit}.jsonl")));
        raw.insert(
            unit.clone(),
            text.map_err(|_| Unavailable::BindingMismatch(Field::Unit(unit.clone())))?,
        );
    }
    for (unit, text) in &raw {
        let base = if unit.ends_with("-test") {
            base_of(unit, &raw)
        } else {
            None
        };
        let content = match base {
            Some(base) => {
                let (build, _) = load(text).ok_or_else(|| broken(unit))?;
                format!("{build}\n{{\"k\":\"merged\",\"into\":\"{base}\"}}\n{{\"k\":\"end\",\"lines\":2}}\n")
            }
            None => {
                let tests: Vec<&str> = raw
                    .iter()
                    .filter(|(t, _)| base_of(t, &raw) == Some(unit))
                    .map(|(_, text)| text.as_str())
                    .collect();
                merge(text, &tests).ok_or_else(|| broken(unit))?
            }
        };
        let temporary = out.join(format!("{unit}.jsonl.tmp"));
        std::fs::write(&temporary, content).map_err(|_| broken(unit))?;
        std::fs::rename(&temporary, out.join(format!("{unit}.jsonl"))).map_err(|_| broken(unit))?;
    }
    Ok(())
}

/// The crate name of a unit: the part before its metadata hash.
fn crate_of(unit: &str) -> &str {
    let plain = unit.strip_suffix("-test").unwrap_or(unit);
    plain.rsplit_once('-').map_or(plain, |(name, _)| name)
}
