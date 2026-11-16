// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python requirement of the scanned project, as `runtime.python_requirement` reads it:
//! `project.requires-python`, else the `python` dependency of Poetry with its caret written out.

use archkeel_facts::envelope::{RequirementState, TargetSource};
use archkeel_facts::request::{Interpreter, PythonSettings};
use archkeel_snapshot::Snapshot;
use toml::value::{Datetime, Offset};
use toml::{Table, Value};

use crate::inputs::PYPROJECT;

/// Select the grammar and standard library from the snapshot and the configured target.
pub(crate) fn target(
    snapshot: &mut Snapshot,
    settings: &PythonSettings,
) -> Result<(Interpreter, TargetSource), String> {
    if let Some(interpreter) = &settings.interpreter {
        return Ok((interpreter.clone(), TargetSource::Legacy));
    }
    let (required, state) = requirement(snapshot);
    let (selected, source) = if let Some(value) = &settings.python {
        (
            (value.split('.').count() == 2)
                .then(|| version(value))
                .flatten(),
            TargetSource::Config,
        )
    } else if let Some(required) = required {
        (lower_bound(&required), TargetSource::Requirement)
    } else if matches!(
        state,
        RequirementState::MetadataMissing | RequirementState::RequirementMissing
    ) {
        (Some([3, 14, 0]), TargetSource::Default)
    } else {
        return Err(
            "cannot read the Python requirement; set python = \"3.13\" in [scan]".to_owned(),
        );
    };
    let Some([3, minor @ 11..=14, patch]) = selected else {
        let wanted = selected.map_or_else(
            || {
                settings
                    .python
                    .as_deref()
                    .unwrap_or("an unknown version")
                    .to_owned()
            },
            |[major, minor, patch]| format!("{major}.{minor}.{patch}"),
        );
        return Err(format!("Python target {wanted} is unsupported or unread; the collector supports Python 3.11–3.14; set python = \"3.13\" in [scan]"));
    };
    let owner = format!("archkeel-python-analyzer@3.{minor}");
    let stdlib_module_names = archkeel_facts::STANDARD_LIBRARY
        .lines()
        .filter_map(|line| line.split_once(' '))
        .filter_map(|(key, name)| (key == owner).then_some(name.to_owned()))
        .collect::<Vec<_>>();
    if stdlib_module_names.is_empty() {
        return Err(format!("Python 3.{minor} has no standard-library table"));
    }
    Ok((
        Interpreter {
            version: format!("3.{minor}.{patch}").try_into()?,
            stdlib_module_names,
            builtin_module_names: Vec::new(),
        },
        source,
    ))
}

/// Read numeric `>=` and `<` clauses only.
fn lower_bound(required: &str) -> Option<[u32; 3]> {
    let mut lower = None;
    for clause in required.split(',').map(str::trim) {
        if let Some(value) = clause.strip_prefix(">=") {
            let found = version(value)?;
            lower = Some(lower.map_or(found, |old: [u32; 3]| old.max(found)));
        } else {
            version(clause.strip_prefix('<')?)?;
        }
    }
    lower
}

fn version(text: &str) -> Option<[u32; 3]> {
    let mut parts = text.trim().split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next().map(str::parse).transpose().ok()?.unwrap_or(0);
    if parts.next().is_some() {
        return None;
    }
    Some([major, minor, patch])
}

/// The requirement and its state.
pub(crate) fn requirement(snapshot: &mut Snapshot) -> (Option<String>, RequirementState) {
    if !snapshot.is_file(PYPROJECT) {
        // A link out of the snapshot or a directory is not valid metadata; nothing is missing.
        let invalid = Snapshot::is_link(snapshot, PYPROJECT) || snapshot.is_dir(PYPROJECT);
        let state = if invalid {
            RequirementState::MetadataInvalid
        } else {
            RequirementState::MetadataMissing
        };
        return (None, state);
    }
    let Some(table) = snapshot
        .read(PYPROJECT)
        .and_then(|raw| String::from_utf8(raw).ok())
        // `read_text` keeps a byte order mark, and `tomllib` refuses it.
        .filter(|text| !text.starts_with('\u{feff}'))
        .and_then(|text| text.parse::<Table>().ok())
        .filter(|table| table.values().all(python_values))
    else {
        return (None, RequirementState::MetadataInvalid);
    };
    let declared = table
        .get("project")
        .and_then(Value::as_table)
        .and_then(|project| project.get("requires-python"));
    let required = match declared {
        Some(value) => value.as_str().map(str::to_owned),
        None => match poetry_python(&table) {
            Err(state) => return (None, state),
            Ok(text) => Some(normalize_caret(text)),
        },
    };
    match required {
        Some(text) if !py_strip(&text).is_empty() => (Some(text), RequirementState::Declared),
        _ => (None, RequirementState::RequirementInvalid),
    }
}

/// `tool.poetry.dependencies.python`: missing, not a nonblank string, or its text.
/// Whether `tomllib` can build each value: it turns a datetime into a Python `datetime`, `date`
/// or `time`, which refuses what TOML allows, for example the leap second `23:59:60`.
fn python_values(value: &Value) -> bool {
    match value {
        Value::Datetime(datetime) => python_datetime(datetime),
        Value::Array(items) => items.iter().all(python_values),
        Value::Table(table) => table.values().all(python_values),
        _ => true,
    }
}

fn python_datetime(datetime: &Datetime) -> bool {
    let date = datetime.date.is_none_or(|date| {
        let leap = date.year % 4 == 0 && (date.year % 100 != 0 || date.year % 400 == 0);
        let days = match date.month {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 if leap => 29,
            2 => 28,
            _ => 0,
        };
        (1..=9999).contains(&date.year) && (1..=days).contains(&date.day)
    });
    let time = datetime
        .time
        .is_none_or(|time| time.hour <= 23 && time.minute <= 59 && time.second <= 59);
    // `timezone` takes an offset strictly between -24 and 24 hours.
    let offset = match datetime.offset {
        Some(Offset::Custom { minutes }) => minutes.unsigned_abs() < 24 * 60,
        _ => true,
    };
    date && time && offset
}

fn poetry_python(table: &Table) -> Result<&str, RequirementState> {
    let dependencies = table
        .get("tool")
        .and_then(Value::as_table)
        .and_then(|tool| tool.get("poetry"))
        .and_then(Value::as_table)
        .and_then(|poetry| poetry.get("dependencies"))
        .and_then(Value::as_table);
    let Some(python) = dependencies.and_then(|found| found.get("python")) else {
        return Err(RequirementState::RequirementMissing);
    };
    match python.as_str() {
        Some(text) if !py_strip(text).is_empty() => Ok(text),
        _ => Err(RequirementState::RequirementInvalid),
    }
}

/// `_normalize_poetry_caret`: `^X.Y.Z` (X without a leading zero) is `>=X.Y.Z,<X+1.0`.
fn normalize_caret(required: &str) -> String {
    let Some(version) = py_strip(required).strip_prefix('^') else {
        return required.to_owned();
    };
    let parts: Vec<&str> = version.split('.').collect();
    let digits = |part: &&str| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit());
    let first = parts[0];
    if parts.len() > 3 || !parts.iter().all(digits) || first.starts_with('0') {
        return required.to_owned();
    }
    match first
        .parse::<u64>()
        .ok()
        .and_then(|major| major.checked_add(1))
    {
        Some(next) => format!(">={version},<{next}.0"),
        None => required.to_owned(),
    }
}

/// `str.strip()`: Python also strips the separators U+001C to U+001F.
fn py_strip(text: &str) -> &str {
    text.trim_matches(|character: char| {
        character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
    })
}

#[cfg(test)]
#[path = "requirement_tests.rs"]
mod tests;
