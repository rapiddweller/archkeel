// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cycles of slice S3 (`cycle_sections`, `_cycle_records`, `_backed_package_cycles`).

use archkeel_facts::envelope::FileFact;
use archkeel_facts::identity::{stable_id, Part};

use super::{cycles, Cycle};
use crate::edges::{both, Level};
use crate::imports::Import;
use crate::modules::tables;
use crate::topology::tests::{file, import};
use crate::topology::{modules, packages};

fn cycles_of(files: &[FileFact], imports: &[Import]) -> Vec<Cycle> {
    let (module_edges, package_edges) = both(files, imports, "shop");
    let (module_table, package_table) = tables(files).unwrap();
    let module_measured = modules(&module_table, &module_edges, &[]);
    let package_measured = packages(&package_table, &package_edges);
    cycles(
        &module_table,
        &package_table,
        (&module_measured, &module_edges),
        (&package_measured, &package_edges),
    )
}

fn id(level: &str, members: &[&str]) -> String {
    let mut parts = vec![Part::Text(level)];
    parts.extend(members.iter().map(|member| Part::Text(member)));
    stable_id("SCC", &parts)
}

fn edge(level: &str, source: &str, target: &str) -> String {
    stable_id(
        "EDGE",
        &[Part::Text(level), Part::Text(source), Part::Text(target)],
    )
}

fn files() -> Vec<FileFact> {
    vec![
        file("shop.a.x", "shop.a"),
        file("shop.a.y", "shop.a"),
        file("shop.b.z", "shop.b"),
        file("shop.b.v", "shop.b"),
    ]
}

#[test]
fn a_dag_and_a_self_import_have_no_cycle() {
    let imports = [
        import("I1", "shop.a.x", "shop.a.y"),
        import("I2", "shop.a.y", "shop.b.z"),
        import("I3", "shop.b.z", "shop.b.z"),
    ];
    assert!(cycles_of(&files(), &imports).is_empty());
}

#[test]
fn a_module_cycle_across_two_packages_backs_the_package_cycle() {
    let imports = [
        import("I1", "shop.b.z", "shop.a.x"),
        import("I2", "shop.a.x", "shop.b.z"),
    ];
    let found = cycles_of(&files(), &imports);
    let module = id("module", &["shop.a.x", "shop.b.z"]);
    let package = id("package", &["shop.a", "shop.b"]);
    let mut ids = vec![module.clone(), package.clone()];
    ids.sort();
    assert_eq!(found.iter().map(Cycle::id).collect::<Vec<_>>(), ids);
    let module_cycle = found.iter().find(|c| c.level() == Level::Module).unwrap();
    assert_eq!(module_cycle.members(), ["shop.a.x", "shop.b.z"]);
    // The internal edges keep the order of their (source, target) pairs.
    assert_eq!(
        module_cycle.internal_edges(),
        [
            edge("module", "shop.a.x", "shop.b.z"),
            edge("module", "shop.b.z", "shop.a.x")
        ]
    );
    assert_eq!(module_cycle.backed_by(), None);
    let package_cycle = found.iter().find(|c| c.level() == Level::Package).unwrap();
    assert_eq!(package_cycle.backed_by(), Some(&[module][..]));
}

#[test]
fn a_package_cycle_that_no_module_cycle_crosses_is_a_roll_up() {
    // shop.a.x -> shop.b.z and shop.b.v -> shop.a.y: the packages close a cycle, the modules not.
    let imports = [
        import("I1", "shop.a.x", "shop.b.z"),
        import("I2", "shop.b.v", "shop.a.y"),
        // A module cycle inside one package backs no package cycle.
        import("I3", "shop.a.x", "shop.a.y"),
        import("I4", "shop.a.y", "shop.a.x"),
    ];
    let found = cycles_of(&files(), &imports);
    let package_cycle = found.iter().find(|c| c.level() == Level::Package).unwrap();
    assert_eq!(package_cycle.backed_by(), Some(&[][..]));
    assert_eq!(found.len(), 2);
}

#[test]
fn an_edge_to_a_package_outside_the_reply_closes_no_cycle() {
    let imports = [
        import("I1", "shop.a.x", "shop.gone.q"),
        import("I2", "shop.a.x", "shop.b.z"),
    ];
    assert!(cycles_of(&files(), &imports).is_empty());
}

#[test]
fn disconnected_cycles_are_sorted_by_id() {
    let mut all = files();
    all.push(file("shop.c.p", "shop.c"));
    all.push(file("shop.c.q", "shop.c"));
    let imports = [
        import("I1", "shop.c.p", "shop.c.q"),
        import("I2", "shop.c.q", "shop.c.p"),
        import("I3", "shop.a.x", "shop.a.y"),
        import("I4", "shop.a.y", "shop.a.x"),
    ];
    let found = cycles_of(&all, &imports);
    let ids: Vec<&str> = found.iter().map(Cycle::id).collect();
    let mut sorted = ids.clone();
    sorted.sort_unstable();
    assert_eq!(ids, sorted);
    assert_eq!(found.len(), 2);
}
