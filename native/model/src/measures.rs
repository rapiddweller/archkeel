// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Check and sum the per-file counts without treating missing data as zero.

use std::collections::BTreeSet;

use archkeel_facts::envelope::{Coverage, Facts};
use archkeel_facts::vocab::Status;
use archkeel_facts::{CallFact, Section};
use serde::Serialize;

/// The counts of one complete source inventory.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Measures {
    pub calls_total: u64,
    pub calls_resolved: u64,
    pub calls_partial: u64,
    pub calls_builtin: u64,
    pub calls_external: u64,
    pub calls_unresolved: u64,
    pub unresolved_self: u64,
    pub unresolved_attribute: u64,
    pub unresolved_name: u64,
    pub unresolved_dynamic: u64,
    pub typing_positions: u64,
    pub untyped_private_accesses: u64,
}

/// Return no measurement when the inventory or any row is incomplete or inconsistent.
fn measure(coverage: &Coverage) -> Option<Measures> {
    let selected: BTreeSet<&str> = coverage.selected_files.iter().map(String::as_str).collect();
    let rows = coverage.measures.as_ref()?;
    let files: BTreeSet<&str> = rows.iter().map(|row| row.file.as_str()).collect();
    let modules: BTreeSet<&str> = rows.iter().map(|row| row.module.as_str()).collect();
    let count = u64::try_from(selected.len()).ok()?;
    if selected.is_empty()
        || selected.len() != coverage.selected_files.len()
        || rows.len() != files.len()
        || rows.len() != modules.len()
        || modules.contains("")
        || files != selected
        || coverage.files_read != count
        || coverage.files_parsed != count
    {
        return None;
    }
    let mut total = Measures::default();
    for row in rows {
        let calls = row
            .calls_resolved
            .checked_add(row.calls_partial)?
            .checked_add(row.calls_builtin)?
            .checked_add(row.calls_external)?
            .checked_add(row.calls_unresolved)?;
        let reasons = row
            .unresolved_self
            .checked_add(row.unresolved_attribute)?
            .checked_add(row.unresolved_name)?
            .checked_add(row.unresolved_dynamic)?;
        if calls != row.calls_total || reasons != row.calls_unresolved {
            return None;
        }
        macro_rules! add {
            ($($field:ident),*) => { $(total.$field = total.$field.checked_add(row.$field)?;)* };
        }
        add!(
            calls_total,
            calls_resolved,
            calls_partial,
            calls_builtin,
            calls_external,
            calls_unresolved,
            unresolved_self,
            unresolved_attribute,
            unresolved_name,
            unresolved_dynamic,
            typing_positions,
            untyped_private_accesses
        );
    }
    Some(total)
}

/// Check that the count does not omit a proven call record.
pub fn measure_facts(facts: &Facts) -> Option<Measures> {
    let total = measure(&facts.coverage)?;
    let rows = facts.coverage.measures.as_ref()?;
    if !crate::observed::inventory_complete(facts) || facts.files.len() != rows.len() {
        return None;
    }
    for row in rows {
        if !facts
            .files
            .iter()
            .any(|file| file.rel_path == row.file && file.module == row.module)
        {
            return None;
        }
    }
    let mut proven = std::collections::HashMap::<&str, u64>::new();
    for section in &facts.sections {
        if let Section::Calls(calls) = section {
            for data in calls.iter().filter_map(|call| match &call.data {
                CallFact::Calls(data)
                    if data.status == Status::Resolved && !data.targets.is_empty() =>
                {
                    Some(data)
                }
                _ => None,
            }) {
                let count = proven.entry(data.source_module.as_str()).or_default();
                *count = count.checked_add(1)?;
            }
        }
    }
    for (module, count) in proven {
        let row = rows.iter().find(|row| row.module.as_str() == module)?;
        if count > row.calls_resolved.checked_add(row.calls_partial)? {
            return None;
        }
    }
    Some(total)
}

#[cfg(test)]
mod tests {
    use super::measure;
    use archkeel_facts::envelope::Coverage;
    use archkeel_facts::measures::FileMeasures;

    #[test]
    fn rejects_missing_duplicate_and_inconsistent_rows() {
        let mut coverage = Coverage::of((1, 1), vec!["a.py".into()], vec![]);
        assert!(measure(&coverage).is_none());
        let row = FileMeasures {
            file: "a.py".into(),
            module: archkeel_facts::ids::ModuleName::new("a"),
            calls_total: 2,
            calls_unresolved: 2,
            unresolved_name: 2,
            ..FileMeasures::default()
        };
        coverage.measures = Some(vec![row.clone()]);
        assert_eq!(measure(&coverage).unwrap().calls_unresolved, 2);
        coverage.measures = Some(vec![row.clone(), row.clone()]);
        assert!(measure(&coverage).is_none());
        coverage.measures = Some(vec![FileMeasures {
            calls_total: 3,
            ..row
        }]);
        assert!(measure(&coverage).is_none());
        coverage.files_parsed = 0;
        assert!(measure(&coverage).is_none());
    }
}
