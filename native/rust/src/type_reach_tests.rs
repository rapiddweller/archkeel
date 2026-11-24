// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `type_reach.rs`. Each test changes one part of a matching binding.

use super::*;
use serde_json::json;

const RUSTC: &str = "rustc 1.97.0 (2d8144b78 2026-07-07)\nhost: aarch64-apple-darwin\n";

fn expected<'a>(config: &'a Config, units: &'a [String]) -> Expected<'a> {
    Expected {
        rustc: RUSTC,
        driver_sha256: "d1",
        target_triple: "aarch64-apple-darwin",
        config,
        cargo_lock_sha256: "c1",
        units,
    }
}

fn build(unit: &str, edit: impl FnOnce(&mut Value)) -> String {
    let mut line = json!({
        "k": "build", "schema": 1, "unit": unit, "test": unit.ends_with("-test"), "rustc": RUSTC,
        "driver_sha256": "d1", "target_triple": "aarch64-apple-darwin", "cfg": "default",
        "cfg_args": ["feature=\"x\""], "cargo_lock_sha256": "c1",
        "files": [["a/src/lib.rs", "h1"], ["gen/out.rs", "h9"]],
    });
    edit(&mut line);
    line.to_string()
}

/// A whole file: the build line, the string table, one record and the end record.
fn file(unit: &str, edit: impl FnOnce(&mut Value)) -> (String, String) {
    let text = format!(
        "{}\n{{\"k\":\"str\",\"v\":[]}}\n{{\"k\":\"fn\"}}\n{{\"k\":\"end\",\"lines\":3}}\n",
        build(unit, edit)
    );
    (unit.to_string(), text)
}

fn units(names: &[&str]) -> Vec<String> {
    names.iter().map(|name| name.to_string()).collect()
}

fn scan() -> BTreeMap<String, String> {
    [("a/src/lib.rs", "h1"), ("a/src/other.rs", "h2")]
        .into_iter()
        .map(|(path, sha)| (path.to_string(), sha.to_string()))
        .collect()
}

fn field(result: Result<Verified, Unavailable>) -> String {
    match result {
        Err(Unavailable::BindingMismatch(field)) => field.describe(),
        Err(other) => other.describe(),
        Ok(_) => "matched".to_string(),
    }
}

fn check(names: &[&str], files: &[(String, String)]) -> String {
    let (config, wanted) = (Config::Default, units(names));
    field(expected(&config, &wanted).verify(files, &scan()))
}

#[test]
fn a_matching_binding_lists_the_files_that_no_unit_read_and_counts_the_unscanned_ones() {
    let (config, wanted) = (Config::Default, units(&["a-1"]));
    let done = expected(&config, &wanted)
        .verify(&[file("a-1", |_| ())], &scan())
        .ok()
        .unwrap();
    assert_eq!(done.units, 1);
    assert_eq!(done.not_built, ["a/src/other.rs"]);
    assert!(done.test_only.is_empty());
    assert_eq!(done.outside_scan, 1);
}

#[test]
fn a_file_that_only_a_test_unit_read_is_listed_as_test_only() {
    let (config, wanted) = (Config::Default, units(&["a-1", "a-1-test"]));
    let lib = file("a-1", |v| v["files"] = json!([["a/src/lib.rs", "h1"]]));
    let test = file("a-1-test", |v| {
        v["files"] = json!([["a/src/lib.rs", "h1"], ["a/src/other.rs", "h2"]])
    });
    let done = expected(&config, &wanted)
        .verify(&[lib, test], &scan())
        .ok()
        .unwrap();
    assert!(done.not_built.is_empty());
    assert_eq!(done.test_only, ["a/src/other.rs"]);
}

#[test]
fn a_scanned_file_with_another_hash_names_its_path() {
    let files = [file("a-1", |v| v["files"][0][1] = json!("h-old"))];
    assert_eq!(check(&["a-1"], &files), "file a/src/lib.rs");
}

#[test]
fn an_unknown_schema_is_a_refusal() {
    for schema in [json!(2), json!(0), json!("1"), Value::Null] {
        let files = [file("a-1", |v| v["schema"] = schema)];
        assert_eq!(check(&["a-1"], &files), "schema");
    }
}

#[test]
fn each_part_of_the_binding_is_checked() {
    for key in [
        "rustc",
        "driver_sha256",
        "target_triple",
        "cfg",
        "cargo_lock_sha256",
    ] {
        let files = [file("a-1", |v| v[key] = json!("other"))];
        assert_eq!(check(&["a-1"], &files), key);
    }
}

#[test]
fn the_config_is_the_one_that_the_scan_asks_for() {
    let (config, wanted) = (Config::AllFeatures, units(&["a-1"]));
    let result = expected(&config, &wanted).verify(&[file("a-1", |_| ())], &scan());
    assert_eq!(field(result), "cfg");
}

#[test]
fn a_cfg_that_is_no_feature_is_refused_so_that_another_config_cannot_pass_as_default() {
    for cfgs in [
        json!(["foo"]),
        json!(["feature=\"x\"", "bar"]),
        json!(["target_os=\"x\""]),
        Value::Null,
    ] {
        let files = [file("a-1", |v| v["cfg_args"] = cfgs)];
        assert_eq!(check(&["a-1"], &files), "cfg_args");
    }
}

#[test]
fn no_unit_is_a_refusal() {
    assert_eq!(check(&[], &[file("a-1", |_| ())]), "build");
}

#[test]
fn a_line_that_is_no_build_record_is_refused() {
    let text = "{\"k\":\"str\"}\n{\"k\":\"end\",\"lines\":1}\n".to_string();
    assert_eq!(check(&["a-1"], &[("a-1".to_string(), text)]), "build");
    let text = "not json\n{\"k\":\"end\",\"lines\":1}\n".to_string();
    assert_eq!(check(&["a-1"], &[("a-1".to_string(), text)]), "build");
}

#[test]
fn a_cut_off_file_and_a_file_without_an_end_record_are_refused() {
    let (unit, text) = file("a-1", |_| ());
    let lines: Vec<&str> = text.lines().collect();
    let cut = lines[..lines.len() - 2].join("\n");
    assert_eq!(check(&["a-1"], &[(unit.clone(), cut)]), "end of unit a-1");
    let no_end = lines[..lines.len() - 1].join("\n");
    assert_eq!(
        check(&["a-1"], &[(unit.clone(), no_end)]),
        "end of unit a-1"
    );
    let wrong = text.replace("\"lines\":3", "\"lines\":4");
    assert_eq!(check(&["a-1"], &[(unit, wrong)]), "end of unit a-1");
}

#[test]
fn an_expected_unit_without_a_file_is_refused_and_a_stale_file_is_ignored() {
    let stale = file("gone-9", |_| ());
    assert_eq!(
        check(&["a-1", "b-2"], &[file("a-1", |_| ()), stale.clone()]),
        "unit b-2"
    );
    assert_eq!(check(&["a-1"], &[file("a-1", |_| ()), stale]), "matched");
}

#[test]
fn a_file_that_names_another_unit_is_refused() {
    let (_, text) = file("other-3", |_| ());
    assert_eq!(check(&["a-1"], &[("a-1".to_string(), text)]), "unit a-1");
}

#[test]
fn one_bad_unit_refuses_the_whole_configuration() {
    let bad = file("a-1-test", |v| v["driver_sha256"] = json!("other"));
    assert_eq!(
        check(&["a-1", "a-1-test"], &[file("a-1", |_| ()), bad]),
        "driver_sha256"
    );
}

#[test]
fn a_directory_is_read_for_the_expected_units_only() {
    let (config, wanted) = (Config::Default, units(&["a-1", "b-2"]));
    let dir = std::env::temp_dir().join(format!("archkeel-type-reach-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("a-1.jsonl"), file("a-1", |_| ()).1).unwrap();
    std::fs::write(dir.join("old-7.jsonl"), "stale").unwrap();
    assert_eq!(
        field(expected(&config, &wanted).verify_dir(&dir, &scan())),
        "unit b-2"
    );
    std::fs::write(dir.join("b-2.jsonl"), file("b-2", |_| ()).1).unwrap();
    let done = expected(&config, &wanted)
        .verify_dir(&dir, &scan())
        .ok()
        .unwrap();
    assert_eq!(done.units, 2);
    std::fs::remove_dir_all(&dir).unwrap();
}

fn descriptor(text: &str) -> Result<Vec<Facts>, String> {
    let dir = std::env::temp_dir().join(format!(
        "archkeel-descriptor-{}-{}",
        std::process::id(),
        text.len()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("descriptor.json");
    std::fs::write(&path, text).unwrap();
    let found = read_descriptor(&path, &scan());
    std::fs::remove_dir_all(&dir).unwrap();
    found
}

#[test]
fn a_descriptor_that_names_no_facts_says_why_and_never_gives_empty_facts() {
    let why = descriptor("{\"unavailable\": \"the pinned Rust toolchain is not installed\"}");
    assert_eq!(
        why.err().unwrap(),
        "the pinned Rust toolchain is not installed"
    );
    assert!(descriptor("not json").err().unwrap().contains("no JSON"));
    assert!(descriptor("{\"configs\": []}")
        .err()
        .unwrap()
        .contains("no configuration"));
    let unknown = "{\"configs\": [{\"name\": \"other\", \"dir\": \"x\", \"units\": []}]}";
    assert!(descriptor(unknown)
        .err()
        .unwrap()
        .contains("unknown configuration"));
}

#[test]
fn a_descriptor_whose_facts_do_not_match_the_scan_names_the_field() {
    let dir =
        std::env::temp_dir().join(format!("archkeel-descriptor-facts-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("a-1.jsonl"),
        file("a-1", |v| v["files"][0][1] = json!("h-old")).1,
    )
    .unwrap();
    let text = format!(
        "{{\"rustc\": {}, \"driver_sha256\": \"d1\", \"target_triple\": \"aarch64-apple-darwin\", \"cargo_lock_sha256\": \"c1\", \"configs\": [{{\"name\": \"default\", \"dir\": {}, \"units\": [\"a-1\"]}}]}}",
        json!(RUSTC),
        json!(dir.display().to_string())
    );
    let why = descriptor(&text).err().unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    assert!(why.contains("file a/src/lib.rs"), "{why}");
}

#[test]
fn the_schema_number_of_the_driver_is_the_one_of_the_reader() {
    let out = include_str!("../../../tools/rustc-facts/src/out.rs");
    assert!(out.contains(&format!("const SCHEMA: u32 = {};", super::SCHEMA)));
}
