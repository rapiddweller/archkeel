// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `type_reach.rs` and the reach model. These tests read the facts that the real toolchain
// produced. They are ignored: `make rustc-facts-e2e` produces the descriptors (`ARCHKEEL_E2E_OUT`) and
// runs them.

use super::read_descriptor;
use crate::type_reach_filter::Filter;
use archkeel_facts::identity::sha256_hex;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// The facts of the producer, or the reason why the test cannot run.
fn out(name: &str) -> PathBuf {
    let dir = std::env::var("ARCHKEEL_E2E_OUT")
        .expect("set ARCHKEEL_E2E_OUT; run `make rustc-facts-e2e`");
    Path::new(&dir).join(name)
}

/// Every `.rs` file under `dir`, as a path relative to `root` with `/`, with its SHA-256.
fn scan_rust_files(root: &Path, dir: &Path, found: &mut BTreeMap<String, String>) {
    for entry in std::fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        if path.is_dir() && name != "target" && !name.starts_with('.') {
            scan_rust_files(root, &path, found);
        } else if name.ends_with(".rs") {
            let relative = path
                .strip_prefix(root)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            found.insert(relative, sha256_hex(&std::fs::read(&path).unwrap()));
        }
    }
}

#[test]
#[ignore = "reads the facts of `make rustc-facts-e2e`"]
fn the_reader_verifies_the_facts_of_the_native_workspace() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let mut scanned = BTreeMap::new();
    scan_rust_files(&root, &root.join("native"), &mut scanned);
    let facts = read_descriptor(&out("native.json"), &scanned).unwrap().0;
    assert_eq!(facts.len(), 9);
}

/// The cases of `tests/rust_reach_fixtures/ws`: each has `<case>_a`, whose code dispatches into an impl
/// in `<case>_b`. The first group runs that impl at run time, so the pair is real and must stay;
/// the controls never run it, and the filter may exclude the pair.
const KEPT: [&str; 72] = [
    "direct",
    "h1",
    "h2",
    "h3",
    "fnvalue",
    "dropgen",
    "upcast",
    "async",
    "opaque",
    "fielddrop",
    "closure",
    "cgen",
    "ioerr",
    "panic",
    "gdyn",
    "gvec",
    "esend",
    "eany",
    "ctl",
    "boxerr",
    "rcrefcell",
    "arcfn",
    "foreach",
    "spawn",
    "mpsc",
    "anybox",
    "ops",
    "deref",
    "iter",
    "trep",
    "dropu",
    "stat",
    "send",
    "wrapi",
    "proj",
    "intoc",
    "derefc",
    "waker",
    "wakearc",
    "fnptr",
    "pinfut",
    "localkey",
    "intoraw",
    "autoup",
    "down",
    "fup",
    "stash",
    "feach",
    "arcraw",
    "fhold",
    "hand",
    "princ",
    "futhold",
    "jobup",
    "bptr",
    "vtany",
    "vtsend",
    "vtreg",
    "vtblanket",
    "cfg_feature_only_fb",
    "opgen",
    "asyncg",
    "gdrop",
    "assoc",
    "blanket",
    "fnsame",
    "fnrc",
    "fnhr",
    "fngen",
    "fnonce",
    "fnmut",
    "fnpass",
];
// `fnsig` and `fnmutsig` (AD-1160): the closure that holds the type has another `dyn Fn*` signature than the receiver.
const CONTROLS: [&str; 7] = [
    "none", "dyn", "generic", "other", "unbound", "fnsig", "fnmutsig",
];

#[test]
#[ignore = "reads the facts of `make rustc-facts-e2e`"]
fn each_hole_keeps_its_real_dispatch_pair_and_each_control_is_excluded() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/rust_reach_fixtures/ws")
        .canonicalize()
        .unwrap();
    let mut scanned = BTreeMap::new();
    scan_rust_files(&root, &root, &mut scanned);
    let loaded = read_descriptor(&out("fixtures.json"), &scanned).unwrap().0;
    let truth: BTreeMap<String, usize> =
        serde_json::from_str(&std::fs::read_to_string(out("truth.json")).unwrap()).unwrap();
    let cases = KEPT
        .iter()
        .map(|c| (c, true))
        .chain(CONTROLS.iter().map(|c| (c, false)));
    let known: BTreeSet<String> = cases
        .clone()
        .flat_map(|(c, _)| ["a", "b", "g"].map(|s| format!("native.fx.{c}_{s}")))
        .collect();
    let filter = Filter::new(&loaded, &known);
    let mut wrong: Vec<String> = Vec::new();
    for (case, kept) in cases {
        // `cgen`: the generic function that the closure calls is the code that dispatches. `fnhr`: `g` drops the box.
        let caller = if matches!(*case, "cgen" | "fnhr") {
            "g"
        } else {
            "a"
        };
        let excluded = filter.excluded(
            &format!("native.fx.{case}_{caller}"),
            &format!("native.fx.{case}_b"),
        );
        assert_eq!(
            truth[*case] > 0,
            kept,
            "the run decides the truth of {case}"
        );
        // The class hierarchy keeps `dyn`: its type implements the trait in reach although nothing coerces it.
        if excluded == (kept || *case == "dyn") {
            wrong.push((*case).to_string());
        }
    }
    assert!(wrong.is_empty(), "the filter is wrong on {wrong:?}");
}

/// The cases of `tests/rust_reach_fixtures/coll`: an erasing crate that is a vendored path dependency with the
/// package name of a member (the old reader took it for workspace code), and members that the name does not
/// give away. Each runs its dispatch, so each pair must stay.
#[test]
#[ignore = "reads the facts of `make rustc-facts-e2e`"]
fn a_vendored_crate_with_the_name_of_a_member_is_foreign_and_a_renamed_member_is_not() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/rust_reach_fixtures/coll")
        .canonicalize()
        .unwrap();
    let mut scanned = BTreeMap::new();
    scan_rust_files(&root, &root, &mut scanned);
    let loaded = read_descriptor(&out("coll.json"), &scanned).unwrap().0;
    let truth: BTreeMap<String, usize> =
        serde_json::from_str(&std::fs::read_to_string(out("coll-truth.json")).unwrap()).unwrap();
    let cases = [
        "mcoll", "mcollhy", "mrenamed", "mhyph", "mshared", "msymlink",
    ];
    let known: BTreeSet<String> = cases
        .iter()
        .flat_map(|c| ["a", "b"].map(|s| format!("native.fx.{c}_{s}")))
        .collect();
    let filter = Filter::new(&loaded, &known);
    let mut dropped = Vec::new();
    for case in cases {
        assert_eq!(truth[case], 1, "the run decides the truth of {case}");
        let excluded = filter.excluded(
            &format!("native.fx.{case}_a"),
            &format!("native.fx.{case}_b"),
        );
        if excluded {
            dropped.push(case);
        }
    }
    assert!(
        dropped.is_empty(),
        "the filter dropped the real dispatch of {dropped:?}"
    );
}
