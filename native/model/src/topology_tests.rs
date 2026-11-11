// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The fan counts and ranks of slice S3 (`module_records`, `package_records`,
//! `count_macro_bodies`) and the ranks of the edges (`aggregate_edges`).

use archkeel_facts::envelope::FileFact;
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};

use super::{modules, packages, Measure};
use crate::edges::{both, Edge};
use crate::imports::{Import, MacroBody, Resolved};
use crate::modules::tables;

pub(crate) fn file(module: &str, package: &str) -> FileFact {
    FileFact {
        id: FactId::new(format!("FILE-{module}")),
        rel_path: format!("{module}.src"),
        module: ModuleName::new(module),
        package: PackageName::new(package),
        all_exports: Vec::new(),
        all_literal: false,
        compatibility_logic_free: false,
        stable_bindings: Vec::new(),
        blank: false,
        evidence_id: EvidenceId::new(format!("EVD-{module}")),
    }
}

/// An import from one module to another; the package is the name before the last dot.
pub(crate) fn import(id: &str, source: &str, target: &str) -> Import {
    let package = |name: &str| {
        name.rsplit_once('.')
            .map_or("", |(head, _)| head)
            .to_owned()
    };
    Import {
        id: id.to_owned(),
        source_module: source.to_owned(),
        target_module: target.to_owned(),
        source_package: package(source),
        target_package: package(target),
        under_type_checking: false,
        relative: false,
        resolved: Resolved::Local,
        evidence: Vec::new(),
    }
}

fn body(source: &str, target: &str) -> MacroBody {
    MacroBody {
        id: format!("M-{source}-{target}"),
        source_module: source.to_owned(),
        target_module: target.to_owned(),
    }
}

fn measure(fan_in: usize, fan_out: usize, rank: usize) -> Measure {
    Measure {
        fan_in,
        fan_out,
        rank,
    }
}

fn files() -> Vec<FileFact> {
    vec![
        file("shop.a.x", "shop.a"),
        file("shop.a.y", "shop.a"),
        file("shop.b.z", "shop.b"),
        file("shop.c.w", "shop.c"),
    ]
}

fn ranks(edges: &[Edge]) -> Vec<(&str, usize, &str, usize)> {
    edges
        .iter()
        .map(|e| (e.source(), e.source_rank(), e.target(), e.target_rank()))
        .collect()
}

#[test]
fn the_modules_take_the_fan_counts_and_ranks_of_the_module_edges() {
    let imports = [
        import("I1", "shop.a.x", "shop.a.y"),
        import("I2", "shop.a.y", "shop.b.z"),
        import("I3", "shop.a.x", "shop.b.z"),
    ];
    let (module_edges, _) = both(&files(), &imports, "shop");
    let (table, _) = tables(&files()).unwrap();
    let found = modules(&table, &module_edges, &[]).measures;
    assert_eq!(
        found,
        vec![
            measure(0, 2, 0),
            measure(1, 1, 1),
            measure(2, 0, 2),
            measure(0, 0, 0)
        ]
    );
}

#[test]
fn a_macro_body_adds_a_fan_count_only_for_a_new_pair_of_two_modules() {
    let imports = [import("I1", "shop.a.x", "shop.a.y")];
    let (module_edges, _) = both(&files(), &imports, "shop");
    let (table, _) = tables(&files()).unwrap();
    let bodies = [
        // The pair of an edge, a self pair and a module outside the reply add nothing.
        body("shop.a.x", "shop.a.y"),
        body("shop.b.z", "shop.b.z"),
        body("shop.b.z", "shop.gone"),
        // A new pair adds one fan-out and one fan-in, also when two bodies name it.
        body("shop.b.z", "shop.c.w"),
        body("shop.b.z", "shop.c.w"),
    ];
    let found = modules(&table, &module_edges, &bodies).measures;
    assert_eq!(
        found,
        vec![
            measure(0, 1, 0),
            measure(1, 0, 1),
            measure(0, 1, 0),
            measure(1, 0, 0)
        ]
    );
}

#[test]
fn an_edge_to_a_package_outside_the_reply_counts_but_ranks_only_in_the_edge_rows() {
    let imports = [
        import("I1", "shop.a.x", "shop.b.z"),
        import("I2", "shop.b.z", "shop.gone.v"),
    ];
    let (_, package_edges) = both(&files(), &imports, "shop");
    assert_eq!(
        ranks(&package_edges),
        vec![("shop.a", 0, "shop.b", 1), ("shop.b", 1, "shop.gone", 2)]
    );
    let (_, table) = tables(&files()).unwrap();
    let found = packages(&table, &package_edges).measures;
    assert_eq!(
        found,
        vec![measure(0, 1, 0), measure(1, 1, 1), measure(0, 0, 0)]
    );
}

#[test]
fn the_edge_rows_rank_a_cycle_as_one_node() {
    let imports = [
        import("I1", "shop.a.x", "shop.b.z"),
        import("I2", "shop.b.z", "shop.a.y"),
        import("I3", "shop.a.y", "shop.a.x"),
        import("I4", "shop.a.y", "shop.c.w"),
    ];
    let (module_edges, package_edges) = both(&files(), &imports, "shop");
    assert_eq!(
        ranks(&module_edges),
        vec![
            ("shop.a.x", 0, "shop.b.z", 0),
            ("shop.a.y", 0, "shop.a.x", 0),
            ("shop.a.y", 0, "shop.c.w", 1),
            ("shop.b.z", 0, "shop.a.y", 0),
        ]
    );
    assert_eq!(
        ranks(&package_edges),
        vec![
            ("shop.a", 0, "shop.b", 0),
            ("shop.a", 0, "shop.c", 1),
            ("shop.b", 0, "shop.a", 0)
        ]
    );
}
