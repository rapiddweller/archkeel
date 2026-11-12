// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read the four Python baseline schemas without applying debt to a verdict (AD-386).

use crate::json::{self, field, Json};
use crate::policy::amendment::schema_repr;
use crate::policy::baseline_entries::{budgets, violation};
use crate::policy::baseline_value::{
    exact, object, required, BaselineError, BaselineViolation, ValidationBaseline,
    MAX_BASELINE_BYTES,
};

/// Read a baseline with the validation order of Python `parse_validation_baseline`.
///
/// An unchecked baseline cannot be built outside the crate:
/// ```compile_fail,E0451
/// use archkeel_contract::policy::ValidationBaseline;
/// let baseline = ValidationBaseline { violations: vec![], budgets: vec![] };
/// ```
pub fn parse_baseline(bytes: &[u8]) -> Result<ValidationBaseline, BaselineError> {
    if bytes.len() > MAX_BASELINE_BYTES {
        return Err(BaselineError::TooLarge);
    }
    let value = json::read(&integer_zeros(bytes)).map_err(|error| match error.kind {
        crate::ErrorKind::DuplicateKey => BaselineError::DuplicateKey(error.message),
        _ => BaselineError::Json(error.message),
    })?;
    let document = object(&value, "baseline")?;
    let version = match field(document, "schema_version") {
        Some(Json::Text(text)) if ["1.0.0", "1.1.0", "1.2.0", "1.3.0"].contains(&text.as_str()) => {
            text.as_str()
        }
        other => return Err(BaselineError::UnsupportedSchema(schema_repr(other))),
    };
    let fields = if version >= "1.2.0" {
        vec!["schema_version", "violations", "budgets"]
    } else {
        vec!["schema_version", "violations"]
    };
    exact(document, &fields, "baseline")?;
    let Json::Array(entries) = required(document, "violations") else {
        return Err(BaselineError::NotArray("baseline.violations".into()));
    };
    let mut violations = entries
        .iter()
        .enumerate()
        .map(|(index, raw)| {
            violation(
                raw,
                &format!("baseline.violations[{index}]"),
                version != "1.0.0",
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    reject_repeated(&violations)?;
    violations.sort_by(|a, b| {
        (&a.fingerprint.rules, &a.fingerprint.subjects)
            .cmp(&(&b.fingerprint.rules, &b.fingerprint.subjects))
    });
    let budgets = match field(document, "budgets") {
        Some(raw) => budgets(raw, version == "1.3.0")?,
        None => Vec::new(),
    };
    Ok(ValidationBaseline {
        violations,
        budgets,
    })
}

/// Python reads the integer token `-0` as zero; serde reads it as a float (AD-386).
fn integer_zeros(bytes: &[u8]) -> std::borrow::Cow<'_, [u8]> {
    let mut normalized = std::borrow::Cow::Borrowed(bytes);
    let mut quoted = false;
    let mut escaped = false;
    for (position, byte) in bytes.iter().enumerate() {
        if quoted {
            if escaped {
                escaped = false;
            } else if *byte == b'\\' {
                escaped = true;
            } else if *byte == b'"' {
                quoted = false;
            }
        } else if *byte == b'"' {
            quoted = true;
        } else if *byte == b'-'
            && bytes.get(position + 1) == Some(&b'0')
            && bytes.get(position.wrapping_sub(1)).is_none_or(|previous| {
                matches!(previous, b'[' | b',' | b':' | b' ' | b'\t' | b'\r' | b'\n')
            })
            && bytes.get(position + 2).is_none_or(|next| {
                matches!(next, b',' | b']' | b'}' | b' ' | b'\t' | b'\r' | b'\n')
            })
        {
            if let Some(sign) = normalized.to_mut().get_mut(position) {
                *sign = b' ';
            }
        }
    }
    normalized
}

fn reject_repeated(violations: &[BaselineViolation]) -> Result<(), BaselineError> {
    let mut first = std::collections::BTreeMap::new();
    for (index, item) in violations.iter().enumerate() {
        let fingerprint = &item.fingerprint;
        let key = (&fingerprint.rules, &fingerprint.subjects);
        if let Some(first) = first.get(&key) {
            let name = format!(
                "{} | {}",
                fingerprint.rules.join(" "),
                fingerprint.subjects.join(" ")
            );
            return Err(BaselineError::RepeatedFingerprint {
                index,
                first: *first,
                name,
            });
        }
        first.insert(key, index);
    }
    Ok(())
}
