// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_contract::{Component, ParsedContract};
use archkeel_facts::data::GapData;
use archkeel_facts::envelope::{Coverage, FileFact};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::sections::GapFact;
use archkeel_facts::Record;

use crate::coverage::{incomplete, Incomplete};
use crate::ids::sealed::Sealed;
use crate::ids::{ComponentId, Id, ModuleId, Table};
use crate::modules::Module;
use crate::ownership::{in_scope, owner_of, source_modules};
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
fn the_rows_of_modules_and_packages_wait_for_the_ranks_of_s3() {
    let s3: Vec<Section> = Section::ALL
        .iter()
        .copied()
        .filter(|section| section.porting() == Porting::Slice(Slice::S3))
        .collect();
    assert_eq!(
        s3,
        vec![Section::Packages, Section::Modules, Section::Cycles]
    );
}

#[test]
fn an_unported_section_names_the_slice_that_ports_it() {
    let reason = Reason::Unsupported(Unsupported::Section(Section::Modules));
    assert_eq!(
        reason.to_string(),
        "unsupported: section modules: slice S3 ports it"
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

#[test]
fn a_scope_matches_whole_segments_only() {
    assert!(in_scope("shop.src", "shop.src"));
    assert!(in_scope("shop.src.data", "shop.src"));
    assert!(!in_scope("shop.srcx", "shop.src"));
    assert!(!in_scope("shop", "shop.src"));
}

fn file(module: &str, package: &str, path: &str) -> FileFact {
    FileFact {
        id: FactId::new(format!("MOD-{module}")),
        rel_path: path.to_owned(),
        module: ModuleName::new(module),
        package: PackageName::new(package),
        all_exports: Vec::new(),
        all_literal: false,
        compatibility_logic_free: false,
        stable_bindings: Vec::new(),
        blank: false,
        evidence_id: EvidenceId::new(format!("EVD-{path}")),
    }
}

#[test]
fn modules_keep_the_reply_order_and_packages_sort_by_name() {
    let files = [
        file("b.z", "b", "b/z.ts"),
        file("a.y", "a", "a/y.ts"),
        file("b.x", "b", "b/x.ts"),
    ];
    let Ok((modules, packages)) = crate::modules::tables(&files) else {
        fail("three files make a model");
        return;
    };
    let names: Vec<&str> = modules.iter().map(|(_, module)| module.name()).collect();
    assert_eq!(names, ["b.z", "a.y", "b.x"]);
    let packages: Vec<(&str, Vec<usize>)> = packages
        .iter()
        .map(|(_, p)| (p.name(), p.modules().iter().map(|m| m.index()).collect()))
        .collect();
    assert_eq!(packages, [("a", vec![1]), ("b", vec![0, 2])]);
    let first = modules.get(ModuleId::from_index(0));
    // `stable_id("MOD", "b.z")` of `ir/facts.py`.
    assert_eq!(first.map(Module::fact_id), Some("MOD-d55b1134d40767ff"));
}

fn components(json: &str) -> Option<Table<ComponentId, Component>> {
    let text = format!(r#"{{"schema_version": "2.2.0", "components": {json}, "rules": []}}"#);
    let parsed = archkeel_contract::parse(text.as_bytes());
    let Ok(ParsedContract::Complete(contract)) = parsed else {
        fail(&format!("the contract parses: {parsed:?}"));
        return None;
    };
    Table::of_rows(contract.components().to_vec())
}

fn component(id: &str, packages: &str, exact: &str) -> String {
    format!(
        r#"{{"id": "{id}", "label": "{id}", "role": "component", "packages": {packages},
        "responsibilities": ["Own it."], "forbidden_responsibilities": [], "provenance": ["docs/a.md"],
        "exact_modules": {exact}}}"#
    )
}

#[test]
fn a_module_has_an_owner_only_when_exactly_one_component_claims_it() {
    let Some(table) = components(&format!(
        "[{}, {}, {}]",
        component("COMP-A", r#"["shop"]"#, "[]"),
        component("COMP-B", r#"["shop.inner"]"#, r#"["other.one"]"#),
        component("COMP-C", r#"["other"]"#, "[]"),
    )) else {
        fail("three components make a table");
        return;
    };
    let id = |index| Some(ComponentId::from_index(index));
    assert_eq!(owner_of(&table, "shop.outer"), id(0));
    // A nested package of two components and a module named by two components own nothing.
    assert_eq!(owner_of(&table, "shop.inner.x"), None);
    assert_eq!(owner_of(&table, "other.one"), None);
    assert_eq!(owner_of(&table, "other.two"), id(2));
    assert_eq!(owner_of(&table, "elsewhere"), None);
}

#[test]
fn a_source_that_names_a_component_package_selects_all_its_modules() {
    let Some(table) = components(&format!(
        "[{}]",
        component("COMP-A", r#"["shop.a", "shop.b"]"#, "[]")
    )) else {
        fail("one component makes a table");
        return;
    };
    let files = [
        file("shop.a.x", "shop.a", "a/x.ts"),
        file("shop.b.y", "shop.b", "b/y.ts"),
    ];
    let Ok((modules, _)) = crate::modules::tables(&files) else {
        fail("two files make a model");
        return;
    };
    assert_eq!(source_modules(&table, &modules, "shop.a").len(), 2);
    assert_eq!(source_modules(&table, &modules, "shop.b.y").len(), 1);
    assert_eq!(source_modules(&table, &modules, "shop.c").len(), 0);
}

fn coverage(selected: &[&str], gaps: Vec<Record<GapFact>>) -> Coverage {
    Coverage {
        files_parsed: 1,
        files_read: 1,
        full_scope: gaps.is_empty(),
        gaps,
        selected_files: selected.iter().map(|path| (*path).to_owned()).collect(),
    }
}

fn gap(source_module: Option<&str>) -> Record<GapFact> {
    let mut data = GapData::at("unreadable", "shop.a");
    data.source_module = source_module.map(ModuleName::new);
    Record::unknown(
        FactId::new("UNKNOWN-1"),
        "unreadable",
        None,
        "shop.a",
        GapFact::CollectionGap(data),
    )
}

#[test]
fn the_reply_proves_an_incomplete_scope_only_with_a_gap_that_no_contract_drops() {
    assert_eq!(incomplete(&coverage(&["a.ts"], Vec::new())), None);
    assert_eq!(
        incomplete(&coverage(&[], Vec::new())),
        Some(Incomplete::NoSourceFiles)
    );
    let certain = coverage(&["a.ts"], vec![gap(None), gap(Some("shop.a"))]);
    assert_eq!(incomplete(&certain), Some(Incomplete::CoverageGaps(2)));
    // A gap between two modules can be allowed by the contract (`drop_allowed_pair_gaps`).
    assert_eq!(
        incomplete(&coverage(&["a.ts"], vec![gap(Some("shop.b"))])),
        None
    );
}

/// Fail the test with a message (clippy refuses `panic!` in this workspace).
fn fail(message: &str) {
    assert_eq!(message, "", "the test setup failed");
}
