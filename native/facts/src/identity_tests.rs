// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host matches these identities against the Python collector, so each expected
// value below was printed by the named Python function.

use super::*;

#[test]
fn stable_id_matches_python_stable_id() {
    // archkeel.ir.facts.stable_id("FILE", "shop.src.main_x2e_ts")
    assert_eq!(
        stable_id("FILE", &[Part::Text("shop.src.main_x2e_ts")]),
        "FILE-854275065e73afdd"
    );
    // stable_id("UNKNOWN", "reason", "EVD-x", "mod")
    assert_eq!(
        stable_id(
            "UNKNOWN",
            &[Part::Text("reason"), Part::Text("EVD-x"), Part::Text("mod")]
        ),
        "UNKNOWN-db1f7d91ae307acd"
    );
    // stable_id("X")
    assert_eq!(stable_id("X", &[]), "X-e3b0c44298fc1c14");
}

#[test]
fn stable_id_spells_parts_as_python_str() {
    // stable_id("X", True, None, 3, "ü\x1f")
    assert_eq!(
        stable_id(
            "X",
            &[
                Part::Flag(true),
                Part::Nothing,
                Part::Number(3),
                Part::Text("ü\u{1f}")
            ]
        ),
        "X-711d7688afca3bad"
    );
    // stable_id("X", False, -7, "")
    assert_eq!(
        stable_id("X", &[Part::Flag(false), Part::Number(-7), Part::Text("")]),
        "X-af8c1e7f4c3ffd70"
    );
}

#[test]
fn evidence_id_matches_python_evidence_id() {
    // archkeel.ir.source_records.evidence_id("src/main.ts", 1, 1, 0)
    assert_eq!(evidence_id("src/main.ts", 1, 1, 0), "EVD-bd392def0065ae02");
}

#[test]
fn module_identity_matches_python_module_identity() {
    // archkeel.ir.identity.module_identity(namespace, path)
    let cases = [
        ("shop", "src/main.ts", "shop.src.main_x2e_ts"),
        ("shop", "src/1a/b-c.tsx", "shop.src._x31_a.b_x2d_c_x2e_tsx"),
        (
            "a.b",
            "src/ü/über.d.ts",
            "a.b.src._xfc_._xfc_ber_x2e_d_x2e_ts",
        ),
        ("n", "9/x y.ts", "n._x39_.x_x20_y_x2e_ts"),
        ("n", "src/😀.ts", "n.src._x1f600__x2e_ts"),
    ];
    for (namespace, path, expected) in cases {
        assert_eq!(module_identity(namespace, path).as_deref(), Ok(expected));
    }
}

#[test]
fn module_identity_refuses_unsafe_paths_and_namespaces() {
    for path in [
        "",
        "/a.ts",
        "a/../b.ts",
        "a//b.ts",
        "./a.ts",
        "a\\b.ts",
        "a\0.ts",
    ] {
        assert!(module_identity("shop", path).is_err(), "{path:?}");
    }
    for namespace in ["", "1shop", "shop.", "shop-x"] {
        assert!(module_identity(namespace, "a.ts").is_err(), "{namespace:?}");
    }
}

#[test]
fn package_is_the_module_without_its_last_name() {
    assert_eq!(package_of("shop.src.main_x2e_ts"), "shop.src");
    assert_eq!(package_of("shop"), "");
}

#[test]
fn a_path_is_inside_when_it_is_relative_and_has_no_parent_part() {
    for path in ["a/b.ts", "a/..b/c", "a/./b", ""] {
        assert!(inside(path), "{path}");
    }
    for path in ["/a", "a/../b", "..", "a\\b", "c:/a", "a:b"] {
        assert!(!inside(path), "{path}");
    }
}
