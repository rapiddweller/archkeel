// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::ids::sealed::Sealed;
use crate::ids::{ComponentId, Id, ModuleId, Table};
use crate::reason::{Input, Reason, Unsupported};
use crate::section::{Porting, Section, Slice};
use crate::verdict::{Decision, Verdict};

/// The section names of `tools/dual_run_schema.json`, in its order.
fn schema_sections() -> Vec<String> {
    let schema = include_str!("../../../tools/dual_run_schema.json");
    let start = schema.find("\"sections\": [").unwrap_or(0);
    let list = &schema[start..];
    let end = list.find(']').unwrap_or(0);
    list[..end]
        .split('"')
        .skip(3)
        .step_by(2)
        .map(str::to_owned)
        .collect()
}

#[test]
fn the_sections_are_the_sections_of_the_dual_run_schema() {
    let names: Vec<String> = Section::ALL.iter().map(|s| s.name().to_owned()).collect();
    assert_eq!(names, schema_sections());
    for section in Section::ALL {
        assert_eq!(Section::of_name(section.name()), Some(*section));
    }
    assert_eq!(Section::of_name("transitive_paths"), None);
}

#[test]
fn slice_s1_ports_modules_and_packages() {
    let s1: Vec<Section> = Section::ALL
        .iter()
        .copied()
        .filter(|section| section.porting() == Porting::Slice(Slice::S1))
        .collect();
    assert_eq!(s1, vec![Section::Packages, Section::Modules]);
}

#[test]
fn an_unported_section_names_the_slice_that_ports_it() {
    let reason = Reason::Unsupported(Unsupported::Section(Section::Modules));
    assert_eq!(
        reason.to_string(),
        "unsupported: section modules: slice S1 ports it"
    );
    let store = Reason::Unsupported(Unsupported::Section(Section::Evidence));
    assert!(store.to_string().contains("the store writes it"));
}

#[test]
fn an_unknown_carries_its_reason_and_no_pass_exists_without_the_proof() {
    let reason = Reason::Unsupported(Unsupported::ScopeProof);
    let decision = Decision::unknown(reason.clone());
    assert_eq!(decision.verdict(), Verdict::Unknown);
    assert_eq!(decision.reason(), Some(&reason));
    assert_eq!(Decision::fail().reason(), None);
    assert_eq!(Decision::fail().verdict(), Verdict::Fail);
    assert!(matches!(Decision::passed().verdict(), Verdict::Pass(_)));
}

#[test]
fn a_missing_input_has_its_own_reason() {
    let reason = Reason::MissingInput(Input::Reply);
    assert_eq!(
        reason.to_string(),
        "missing input: no valid collector reply"
    );
    assert!(!reason.to_string().contains("slice"));
}

#[test]
fn a_table_gives_ids_in_order_and_an_id_reads_its_row() {
    let table = Table::<ComponentId, &str>::of_rows(vec!["a", "b"]);
    assert!(table.is_some());
    let Some(table) = table else { return };
    let ids: Vec<usize> = table.iter().map(|(id, _)| id.index()).collect();
    assert_eq!(ids, vec![0, 1]);
    assert_eq!(table.get(ComponentId::from_index(1)), Some(&"b"));
    assert_eq!(table.get(ComponentId::from_index(2)), None);
    assert_eq!(ModuleId::from_index(1).index(), 1);
}

#[test]
fn a_contract_with_mounts_names_the_missing_tree_assembly() {
    let reason = Reason::Unsupported(Unsupported::InsideTree);
    assert_eq!(
        reason.to_string(),
        "unsupported: the contract mounts inside contracts; the tree assembly is not in the core yet"
    );
}
