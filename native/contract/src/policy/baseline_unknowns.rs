// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The accepted UNKNOWN list of schema 1.4.0 (AD-546).
//!
//! The list is sorted by (kind, subject, reason) and has no repeated identity. A file that breaks
//! either rule is refused with the entry that breaks it: a silent "nothing accepted" would turn a
//! damaged file into a gate that fails open or closed without a reason.

use crate::json::{has, Json};
use crate::policy::baseline_entries::text;
use crate::policy::baseline_value::{
    count, exact, object, required, AcceptedUnknown, BaselineError,
};

fn entry(raw: &Json, label: &str) -> Result<AcceptedUnknown, BaselineError> {
    let value = object(raw, label)?;
    let mut fields = vec!["kind", "subject", "reason"];
    let counted = has(value, "count");
    if counted {
        fields.push("count");
    }
    exact(value, &fields, label)?;
    // A count of 1 is the default: the reader takes it, and the writer does not write it.
    let occurrences = if counted {
        count(required(value, "count"), &format!("{label}.count"))?
    } else {
        1
    };
    AcceptedUnknown::new(
        text(required(value, "kind"), &format!("{label}.kind"))?,
        text(required(value, "subject"), &format!("{label}.subject"))?,
        text(required(value, "reason"), &format!("{label}.reason"))?,
        occurrences,
    )
    .map_err(|_| BaselineError::ZeroCount(format!("{label}.count")))
}

/// Read and check the list: each entry, then the order and the identity of all.
pub(super) fn unknowns(raw: &Json) -> Result<Vec<AcceptedUnknown>, BaselineError> {
    let Json::Array(values) = raw else {
        return Err(BaselineError::NotArray("baseline.unknowns".into()));
    };
    let found = values
        .iter()
        .enumerate()
        .map(|(index, raw)| entry(raw, &format!("baseline.unknowns[{index}]")))
        .collect::<Result<Vec<_>, _>>()?;
    for (index, pair) in found.windows(2).enumerate() {
        let (before, after) = (pair[0].identity(), pair[1].identity());
        if before >= after {
            return Err(BaselineError::UnorderedUnknown {
                index: index + 1,
                repeated: before == after,
                name: format!("{} | {} | {}", after.0, after.1, after.2),
            });
        }
    }
    Ok(found)
}

#[cfg(test)]
#[path = "baseline_unknowns_tests.rs"]
mod tests;
