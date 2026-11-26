// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `rustc_facts.rs`. A shell script stands in for `rustup`, so no test removes a toolchain.
// The tests that run the real toolchain are ignored: `make rustc-facts-e2e` runs them.

use crate::rustc_facts::{channel, channel_of, sha256, units_of, FactsTools, SOURCES};
use crate::rustc_facts_merge::{compact, load, merge};
use archkeel_facts::type_reach::{Config, Field, Unavailable};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

pub(super) fn scratch(name: &str) -> crate::repository::tests::Scratch {
    crate::repository::tests::scratch(name)
}

/// A workspace with a `Cargo.toml` and a `Cargo.lock`, and a cache directory.
fn project(dir: &Path) -> (PathBuf, PathBuf) {
    std::fs::write(dir.join("Cargo.toml"), "[workspace]\n").unwrap();
    std::fs::write(dir.join("Cargo.lock"), "version = 4\n").unwrap();
    (dir.join("Cargo.toml"), dir.join("cache"))
}

#[cfg(unix)]
#[test]
fn work_cache_keeps_only_three_recent_paths() {
    let dir = scratch("cache-bound");
    let cache = dir.join("cache");
    let tools = fake(&dir, &WORKS);
    for n in 0..4 {
        let root = dir.join(format!("project-{n}"));
        std::fs::create_dir(&root).unwrap();
        let (manifest, _) = project(&root);
        assert!(tools.produce(&root, &manifest, &cache).is_ok());
    }
    assert!(std::fs::read_dir(cache.join("work")).unwrap().count() <= 3);
}

#[test]
fn work_cache_evicts_the_oldest_unused_path() {
    let dir = scratch("cache-lru");
    let paths: Vec<_> = (0..4).map(|n| dir.join(format!("{n}"))).collect();
    for (index, path) in paths.iter().take(3).enumerate() {
        std::fs::create_dir(path).unwrap();
        let file = std::fs::File::create(path.join("last-used")).unwrap();
        let time = std::time::SystemTime::UNIX_EPOCH
            + std::time::Duration::from_secs(u64::try_from(index).unwrap() + 1);
        file.set_times(std::fs::FileTimes::new().set_modified(time))
            .unwrap();
    }
    super::prune_work(&paths[0]);
    super::prune_work(&paths[3]);
    assert!(paths[0].exists());
    assert!(!paths[1].exists());
    assert!(paths[2].exists());
    assert!(paths[3].exists());
}

/// The behaviour of the fake `rustup`: each field is the exit status of one command.
struct Fake {
    rustc: u8,
    rustc_dev: bool,
    build: u8,
    check: u8,
    check_fails_with: &'static str,
    /// The body of the `features` object of the one member that `cargo metadata` names.
    features: &'static str,
    metadata: u8,
}

const WORKS: Fake = Fake {
    rustc: 0,
    rustc_dev: true,
    build: 0,
    check: 0,
    check_fails_with: "",
    features: "",
    metadata: 0,
};

/// The fake refuses (exit 7) a Cargo call without `--offline` and `--locked`, and one where
/// `RUSTFLAGS` is not set to the empty text. So a test fails when the producer drops one of them.
#[cfg(unix)]
fn fake(dir: &Path, how: &Fake) -> FactsTools {
    use std::os::unix::fs::PermissionsExt;
    let components = if how.rustc_dev {
        "cargo-x\\nrustc-dev-x\\nrustc-x"
    } else {
        "cargo-x\\nrustc-x"
    };
    let script = format!(
        r#"#!/bin/sh
need() {{ for want in "$@"; do found=0; for a in $ARGS; do [ "$a" = "$want" ] && found=1; done; [ $found = 1 ] || exit 7; done; }}
case "$1" in
  component) printf '{components}\n'; exit 0 ;;
  run) shift; shift
    case "$1" in
      rustc) [ {rustc} -ne 0 ] && exit {rustc}; printf 'rustc 1.97.0 (fake)\nhost: test-triple\n'; exit 0 ;;
      cargo) ARGS="$*"
        [ "${{RUSTFLAGS+x}}" = x ] && [ -z "$RUSTFLAGS" ] || exit 7
        case "$2" in
          build) need --offline --locked; [ {build} -ne 0 ] && exit {build}
            mkdir -p "$CARGO_TARGET_DIR/release"; : > "$CARGO_TARGET_DIR/release/archkeel-rustc-facts"; exit 0 ;;
          metadata) need --offline --locked; [ {metadata} -ne 0 ] && exit {metadata}
            while [ $# -gt 0 ]; do [ "$1" = "--manifest-path" ] && manifest="$2"; shift; done
            printf '{{"packages":[{{"id":"t 0.0.0","name":"t","manifest_path":"%s","features":{{{features}}},"targets":[{{"kind":["lib"],"name":"t"}}]}},{{"id":"d 0.0.0","name":"d","manifest_path":"/elsewhere/Cargo.toml","features":{{}},"targets":[]}}],"workspace_members":["t 0.0.0"]}}\n' "$manifest"
            exit 0 ;;
          check) need --offline --locked --message-format=json
            for a in "$@"; do [ "$a" = "{fails_with}" ] && exit {check}; done
            [ -z "{fails_with}" ] && [ {check} -ne 0 ] && exit {check}
            while [ $# -gt 0 ]; do [ "$1" = "--manifest-path" ] && manifest="$2"; shift; done
            printf '{{"k":"build","schema":1,"unit":"t-abc","test":false,"crate_types":["lib"],"files":[]}}\n{{"k":"str","v":[]}}\n{{"k":"end","lines":2}}\n' > "$AK_FACTS_DIR/t-abc.jsonl"
            printf '{{"reason":"compiler-artifact","manifest_path":"%s","target":{{"kind":["lib"],"name":"t"}},"profile":{{"test":false}},"filenames":["/x/libt-abc.rmeta"]}}\n' "$manifest"
            exit 0 ;;
        esac ;;
    esac ;;
esac
exit 9
"#,
        rustc = how.rustc,
        build = how.build,
        check = how.check,
        fails_with = how.check_fails_with,
        features = how.features,
        metadata = how.metadata,
    );
    let path = dir.join("rustup");
    std::fs::write(&path, script).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
    FactsTools { rustup: path }
}

#[cfg(unix)]
fn refusal(name: &str, how: &Fake) -> Option<Unavailable> {
    let dir = scratch(name);
    let (manifest, cache) = project(&dir);
    let tools = fake(&dir, how);
    tools.produce(&dir, &manifest, &cache).err()
}

#[test]
fn the_two_toolchain_files_name_one_channel() {
    let native = include_str!("../../rust-toolchain.toml");
    assert!(channel().is_some());
    assert_eq!(channel_of(native), channel());
}

#[test]
fn the_embedded_driver_source_is_every_file_of_the_crate() {
    let crate_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tools/rustc-facts");
    let mut on_disk = Vec::new();
    for entry in std::fs::read_dir(crate_dir.join("src")).unwrap() {
        on_disk.push(format!(
            "src/{}",
            entry.unwrap().file_name().to_string_lossy()
        ));
    }
    on_disk.extend(["Cargo.toml", "Cargo.lock", "rust-toolchain.toml"].map(String::from));
    on_disk.sort();
    let mut embedded: Vec<String> = SOURCES.iter().map(|(name, _)| name.to_string()).collect();
    embedded.sort();
    assert_eq!(embedded, on_disk);
    for (name, text) in SOURCES {
        assert_eq!(std::fs::read_to_string(crate_dir.join(name)).unwrap(), text);
    }
}

#[cfg(unix)]
#[test]
fn a_missing_toolchain_is_a_refusal_that_names_it() {
    let missing = Fake { rustc: 1, ..WORKS };
    assert!(matches!(
        refusal("toolchain", &missing),
        Some(Unavailable::ToolchainMissing)
    ));
    let dir = scratch("no-rustup");
    let (manifest, cache) = project(&dir);
    let tools = FactsTools {
        rustup: dir.join("not-installed"),
    };
    assert!(matches!(
        tools.produce(&dir, &manifest, &cache).err(),
        Some(Unavailable::ToolchainMissing)
    ));
}

#[cfg(unix)]
#[test]
fn a_toolchain_without_rustc_dev_is_a_refusal_that_names_it() {
    let no_dev = Fake {
        rustc_dev: false,
        ..WORKS
    };
    assert!(matches!(
        refusal("rustc-dev", &no_dev),
        Some(Unavailable::RustcDevMissing)
    ));
}

#[cfg(unix)]
#[test]
fn a_driver_that_does_not_build_is_a_refusal_that_names_it() {
    let broken = Fake { build: 1, ..WORKS };
    assert!(matches!(
        refusal("driver", &broken),
        Some(Unavailable::DriverBuildFailed)
    ));
}

#[cfg(unix)]
#[test]
fn a_cargo_check_that_fails_names_its_configuration() {
    let all = Fake {
        check: 1,
        check_fails_with: "--all-features",
        ..WORKS
    };
    assert!(matches!(
        refusal("check-all", &all),
        Some(Unavailable::CargoCheckFailed(Config::AllFeatures))
    ));
    let none = Fake {
        check: 1,
        check_fails_with: "--no-default-features",
        ..WORKS
    };
    assert!(matches!(
        refusal("check-none", &none),
        Some(Unavailable::CargoCheckFailed(Config::NoDefaultFeatures))
    ));
    let every = Fake { check: 1, ..WORKS };
    assert!(matches!(
        refusal("check-first", &every),
        Some(Unavailable::CargoCheckFailed(Config::Default))
    ));
}

#[cfg(unix)]
#[test]
fn a_workspace_without_a_lock_file_is_a_refusal_of_cargo_check() {
    let dir = scratch("no-lock");
    let (manifest, cache) = project(&dir);
    std::fs::remove_file(dir.join("Cargo.lock")).unwrap();
    let tools = fake(&dir, &WORKS);
    assert!(matches!(
        tools.produce(&dir, &manifest, &cache).err(),
        Some(Unavailable::CargoCheckFailed(Config::Default))
    ));
}

/// The fake exits 7 when `--offline`, `--locked` or the empty `RUSTFLAGS` is missing, so this test
/// fails when the producer drops one of them, for the driver build and for each `cargo check`.
#[cfg(unix)]
#[test]
fn a_working_toolchain_gives_one_facts_file_for_each_unit_of_each_configuration() {
    let dir = scratch("works");
    let (manifest, cache) = project(&dir);
    let tools = fake(&dir, &WORKS);
    let made = tools
        .produce(&dir, &manifest, &cache)
        .map_err(|e| e.describe())
        .unwrap();
    let names: Vec<String> = made.runs.iter().map(|run| run.config.cfg_name()).collect();
    assert_eq!(names, ["default", "no-default-features", "all-features"]);
    for run in &made.runs {
        assert_eq!(run.units, ["t-abc"]);
        assert!(run.dir.join("t-abc.jsonl").is_file());
    }
    assert_eq!(made.members, [""]);
    assert_eq!(made.target_triple, "test-triple");
    assert_eq!(made.driver_sha256, sha256());
}

#[test]
fn every_refusal_has_a_sentence_that_names_its_cause() {
    let all = [
        Unavailable::ToolchainMissing,
        Unavailable::RustcDevMissing,
        Unavailable::DriverBuildFailed,
        Unavailable::CargoCheckFailed(Config::NoDefaultFeatures),
        Unavailable::TooManyFeatures(17),
        Unavailable::MetadataFailed,
        Unavailable::BindingMismatch(Field::SourceFile("a.rs".to_string())),
        Unavailable::BindingMismatch(Field::Unit("u-1".to_string())),
        Unavailable::BindingMismatch(Field::End("u-1".to_string())),
    ];
    let said: Vec<String> = all.iter().map(Unavailable::describe).collect();
    assert!(said[0].contains("toolchain"));
    assert!(said[1].contains("rustc-dev"));
    assert!(said[2].contains("driver"));
    assert!(said[3].contains("no-default-features"));
    assert!(said[4].contains("17") && said[5].contains("metadata"));
    assert!(said[6].contains("a.rs"));
    assert!(said[7].contains("u-1") && said[8].contains("end"));
}

#[cfg(unix)]
#[test]
fn each_feature_of_a_member_is_a_configuration_alone_and_default_is_not_one() {
    let dir = scratch("features");
    let (manifest, cache) = project(&dir);
    let how = Fake {
        features: "\"default\":[\"fa\"],\"fa\":[],\"fb\":[]",
        ..WORKS
    };
    let made = fake(&dir, &how)
        .produce(&dir, &manifest, &cache)
        .map_err(|e| e.describe())
        .unwrap();
    let names: Vec<String> = made.runs.iter().map(|run| run.config.cfg_name()).collect();
    assert_eq!(
        names,
        [
            "default",
            "no-default-features",
            "all-features",
            "feature:t/fa",
            "feature:t/fb"
        ]
    );
}

#[cfg(unix)]
#[test]
fn more_features_than_the_cap_refuse_and_a_failed_metadata_refuses() {
    let many: String = (0..=archkeel_facts::type_reach::MAX_FEATURES)
        .map(|n| format!("\"f{n}\":[]"))
        .collect::<Vec<_>>()
        .join(",");
    let how = Fake {
        features: Box::leak(many.into_boxed_str()),
        ..WORKS
    };
    assert!(matches!(
        refusal("cap", &how),
        Some(Unavailable::TooManyFeatures(17))
    ));
    let how = Fake {
        metadata: 4,
        ..WORKS
    };
    assert!(matches!(
        refusal("metadata", &how),
        Some(Unavailable::MetadataFailed)
    ));
}

fn artifact(manifest: &str, kind: &str, file: &str, test: bool) -> String {
    format!(
        "{{\"reason\":\"compiler-artifact\",\"manifest_path\":\"{manifest}\",\"target\":{{\"kind\":[\"{kind}\"]}},\"profile\":{{\"test\":{test}}},\"filenames\":[\"{file}\"]}}\n"
    )
}

#[test]
fn the_units_are_the_artifacts_of_the_workspace_with_the_hash_of_their_rmeta_file() {
    // `/w/vendor/dep` is under the workspace directory and is no member: a path dependency.
    let (inside, outside) = ("/w/crate/Cargo.toml", "/w/vendor/dep/Cargo.toml");
    let text = [
        artifact(inside, "lib", "/t/deps/libfoo_bar-1a2b.rmeta", false),
        artifact(inside, "lib", "/t/deps/libfoo_bar-9f9f.rmeta", true),
        artifact(
            inside,
            "custom-build",
            "/t/build/build_script_build-77.rmeta",
            false,
        ),
        artifact(outside, "lib", "/t/deps/libdep-55.rmeta", false),
        "{\"reason\":\"build-finished\",\"success\":true}\n".to_string(),
        "not json\n".to_string(),
    ]
    .concat();
    let members: BTreeSet<String> = [inside.to_string()].into();
    let units: Vec<String> = units_of(&text, &members).into_iter().collect();
    assert_eq!(units, ["foo_bar-1a2b", "foo_bar-9f9f-test"]);
}

/// A facts file as the driver writes it: build line, string table, records, end record.
fn raw(crate_types: &str, strings: &[&str], records: &[&str]) -> String {
    let names: Vec<String> = strings.iter().map(|s| format!("\"{s}\"")).collect();
    let mut lines = vec![
        format!("{{\"k\":\"build\",\"crate_types\":[{crate_types}]}}"),
        format!("{{\"k\":\"str\",\"v\":[{}]}}", names.join(",")),
    ];
    lines.extend(records.iter().map(|r| r.to_string()));
    format!(
        "{}\n{{\"k\":\"end\",\"lines\":{}}}\n",
        lines.join("\n"),
        lines.len()
    )
}

#[test]
fn a_union_keeps_each_record_once_and_resolves_the_ids_of_each_file() {
    let lib = raw(
        "\"lib\"",
        &["a::A", "a::B"],
        &["{\"k\":\"adt\",\"d\":0,\"fields\":[1],\"line\":4}"],
    );
    let test = raw(
        "",
        &["a::B", "a::A", "a::T"],
        &[
            "{\"k\":\"adt\",\"d\":1,\"fields\":[0],\"line\":4}",
            "{\"k\":\"adt\",\"d\":2,\"fields\":[],\"line\":9}",
        ],
    );
    let both = merge(&lib, &[&test]).unwrap();
    let (build, records) = load(&both).unwrap();
    assert!(build.contains("\"lib\""));
    assert_eq!(records.len(), 2);
    assert!(records
        .iter()
        .any(|r| r.contains("\"k\":\"adt\"") && r.contains("a::T")));
    assert!(records
        .iter()
        .any(|r| r.contains("\"d\":\"a::A\"") && r.contains("\"fields\":[\"a::B\"]")));
    let again = merge(&both, &[&lib, &test]).unwrap();
    assert_eq!(load(&again).unwrap().1, records);
}

#[test]
fn a_cut_off_raw_file_is_not_merged() {
    let whole = raw(
        "\"lib\"",
        &["a"],
        &["{\"k\":\"adt\",\"d\":0,\"fields\":[],\"line\":1}"],
    );
    let cut: Vec<&str> = whole.lines().collect();
    assert!(load(&cut[..cut.len() - 1].join("\n")).is_none());
    assert!(load(&whole.replace("\"lines\":3", "\"lines\":9")).is_none());
}

#[test]
fn a_test_unit_goes_into_its_library_unit_and_a_missing_or_cut_off_file_is_refused() {
    let dir = scratch("compact");
    let (rawdir, out) = (dir.join("raw"), dir.join("facts"));
    std::fs::create_dir_all(&rawdir).unwrap();
    let rec = "{\"k\":\"adt\",\"d\":0,\"fields\":[],\"line\":1}";
    let lib = raw("\"lib\"", &["a::A"], &[rec]);
    std::fs::write(rawdir.join("a-1.jsonl"), &lib).unwrap();
    std::fs::write(
        rawdir.join("a-1-test.jsonl"),
        raw(
            "",
            &["a::A", "a::T"],
            &[rec, "{\"k\":\"adt\",\"d\":1,\"fields\":[],\"line\":2}"],
        ),
    )
    .unwrap();
    std::fs::write(rawdir.join("old-9.jsonl"), "stale").unwrap();
    let units: BTreeSet<String> = ["a-1", "a-1-test"].map(String::from).into();
    assert!(compact(&rawdir, &out, &units).is_ok());
    assert_eq!(
        load(&std::fs::read_to_string(out.join("a-1.jsonl")).unwrap())
            .unwrap()
            .1
            .len(),
        2
    );
    assert!(std::fs::read_to_string(out.join("a-1-test.jsonl"))
        .unwrap()
        .contains("\"into\":\"a-1\""));
    assert!(!out.join("old-9.jsonl").exists());
    let missing: BTreeSet<String> = ["a-1", "b-2"].map(String::from).into();
    let result = compact(&rawdir, &out, &missing).err().map(|e| e.describe());
    assert!(result.unwrap().contains("unit b-2"));
    std::fs::write(
        rawdir.join("a-1.jsonl"),
        lib.replace("\"lines\":3", "\"lines\":4"),
    )
    .unwrap();
    assert!(compact(&rawdir, &out, &units)
        .err()
        .unwrap()
        .describe()
        .contains("end of unit a-1"));
}

#[path = "rustc_facts_real_tests.rs"]
mod real;

#[test]
fn the_sealed_cargo_run_cannot_inherit_the_operator_permission() {
    assert!(!crate::rustc_facts_members::KEPT_ENV.contains(&crate::ALLOW_BUILD));
}
