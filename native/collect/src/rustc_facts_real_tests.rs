// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `rustc_facts.rs`. These tests run the real toolchain, so they are ignored: `make
// rustc-facts-e2e` runs them.

use crate::rustc_facts::tests::scratch;
use crate::rustc_facts::{channel, toolchain, FactsTools};
use archkeel_facts::type_reach::Unavailable;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

/// One directory for all real runs of this process, so that the driver is built once.
fn real_cache() -> &'static PathBuf {
    static CACHE: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();
    CACHE.get_or_init(|| {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!(
            "archkeel-facts-real-{}-{nanos}",
            std::process::id()
        ))
    })
}

/// The real runs share one driver build: one test at a time.
static REAL: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// The system tools. A test that needs `rustc-dev` fails with the cause when it is missing: it runs
/// only on request (`make rustc-facts-e2e`), so a missing toolchain must not look like a pass.
fn real_tools() -> FactsTools {
    let tools = FactsTools::system();
    let ready = toolchain(&tools, channel().unwrap());
    let cause = ready.as_ref().err().map(Unavailable::describe);
    assert!(
        ready.is_ok(),
        "this test needs the pinned toolchain with rustc-dev: {cause:?}"
    );
    tools
}
/// The directory where the descriptors go for the reader tests of `archkeel-rust-collector`
/// (`type_reach_real_tests.rs`): a test of the collect crate may not depend on that crate.
fn out_dir() -> PathBuf {
    let dir = PathBuf::from(std::env::var("ARCHKEEL_E2E_OUT").expect("set ARCHKEEL_E2E_OUT"));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(name: &str, text: &str) {
    std::fs::write(out_dir().join(name), text).unwrap();
}

#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn the_producer_gives_facts_for_the_native_workspace() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let made = tools
        .produce(&root, &root.join("native/Cargo.toml"), real_cache())
        .map_err(|e| e.describe())
        .unwrap();
    // The three fixed configurations, and each feature of a member alone (the native workspace has six).
    let names: Vec<String> = made.runs.iter().map(|run| run.config.cfg_name()).collect();
    assert_eq!(
        names[..3],
        ["default", "no-default-features", "all-features"]
    );
    assert_eq!(names.len(), 9, "{names:?}");
    assert!(names[3..].iter().all(|n| n.starts_with("feature:")));
    write("native.json", &crate::descriptor_of(&made).to_string());
}

/// A workspace whose `.cargo/config.toml` adds `--cfg foo` for the build and for the host target.
#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn a_cargo_config_file_cannot_change_the_cfg_of_the_facts() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let dir = scratch("cfg-leak").canonicalize().unwrap();
    let host = toolchain(&tools, channel().unwrap()).ok().unwrap();
    let host = host
        .lines()
        .find_map(|l| l.strip_prefix("host: "))
        .unwrap()
        .to_string();
    std::fs::create_dir_all(dir.join(".cargo")).unwrap();
    std::fs::create_dir_all(dir.join("src")).unwrap();
    let config = format!("[build]\nrustflags = [\"--cfg\", \"foo\"]\n[target.{host}]\nrustflags = [\"--cfg\", \"bar\"]\n");
    std::fs::write(dir.join(".cargo/config.toml"), config).unwrap();
    std::fs::write(
        dir.join("Cargo.toml"),
        "[package]\nname = \"t\"\nversion = \"0.0.0\"\nedition = \"2021\"\n",
    )
    .unwrap();
    std::fs::write(
        dir.join("Cargo.lock"),
        "version = 4\n\n[[package]]\nname = \"t\"\nversion = \"0.0.0\"\n",
    )
    .unwrap();
    std::fs::write(dir.join("src/lib.rs"), "pub fn f() {}\n").unwrap();
    let made = tools
        .produce(&dir, &dir.join("Cargo.toml"), real_cache())
        .map_err(|e| e.describe())
        .unwrap();
    for run in &made.runs {
        assert!(!run.units.is_empty());
        for unit in &run.units {
            let text = std::fs::read_to_string(run.dir.join(format!("{unit}.jsonl"))).unwrap();
            assert!(text.lines().next().unwrap().contains("\"cfg_args\":[]"));
        }
    }
}

/// The count of real dispatches of each case. A case under a `cfg` that only some builds enable runs in the
/// build with that cfg: the counts of the builds add up.
fn dispatch_counts(channel: &str) -> BTreeMap<String, usize> {
    let builds: [&[&str]; 2] = [&[], &["--no-default-features", "--features", "fb"]];
    let mut total = BTreeMap::new();
    for build in builds {
        let ws = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/rust_reach_fixtures/ws/Cargo.toml");
        for (case, count) in dispatch_counts_of(channel, &ws, build) {
            *total.entry(case).or_insert(0) += count;
        }
    }
    total
}

fn dispatch_counts_of(channel: &str, ws: &Path, build: &[&str]) -> BTreeMap<String, usize> {
    let target = real_cache().join(format!("fixture-run-{}", ws.display().to_string().len()));
    let run = Command::new("rustup")
        .args([
            "run",
            channel,
            "cargo",
            "run",
            "--offline",
            "--locked",
            "--quiet",
            "--manifest-path",
        ])
        .arg(ws)
        .args(build)
        .env("CARGO_TARGET_DIR", target)
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&run.stdout).to_string();
    text.lines()
        .filter_map(|l| l.split_once('='))
        .map(|(n, c)| (n.to_string(), c.parse().unwrap()))
        .collect()
}

/// Produce the facts of the fixture workspace, and write them with the count of real dispatches of
/// each case, for the reader test.
#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn the_producer_gives_facts_for_the_fixture_workspace_and_runs_its_dispatches() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/rust_reach_fixtures/ws")
        .canonicalize()
        .unwrap();
    let made = tools
        .produce(&root, &root.join("Cargo.toml"), real_cache())
        .map_err(|e| e.describe())
        .unwrap();
    write("fixtures.json", &crate::descriptor_of(&made).to_string());
    let truth = dispatch_counts(channel().unwrap());
    write("truth.json", &serde_json::to_string(&truth).unwrap());
}

/// The collision workspace: path dependencies of the repository that are no members, with the package name of
/// a member, and members whose directory name differs from their package name.
#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn the_producer_gives_facts_for_the_collision_workspace_and_runs_its_dispatches() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/rust_reach_fixtures/coll")
        .canonicalize()
        .unwrap();
    let manifest = root.join("crates/Cargo.toml");
    let made = tools
        .produce(&root, &manifest, real_cache())
        .map_err(|e| e.describe())
        .unwrap();
    write("coll.json", &crate::descriptor_of(&made).to_string());
    let truth = dispatch_counts_of(channel().unwrap(), &manifest, &[]);
    write("coll-truth.json", &serde_json::to_string(&truth).unwrap());
}

/// A `[env]` table of the repository that forces the variables of the driver. The producer sets them with
/// `--config`, which ranks above every config file, so the run is the same as without the table.
#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn a_cargo_config_env_table_cannot_override_the_variables_of_the_driver() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let dir = scratch("env-force").canonicalize().unwrap();
    std::fs::create_dir_all(dir.join(".cargo")).unwrap();
    std::fs::create_dir_all(dir.join("src")).unwrap();
    let forced = ["AK_FACTS_MEMBERS", "AK_FACTS_DIR", "AK_FACTS_REGISTRY"]
        .map(|name| format!("{name} = {{ value = \"/nonexistent\", force = true }}\n"));
    std::fs::write(
        dir.join(".cargo/config.toml"),
        format!("[env]\n{}", forced.concat()),
    )
    .unwrap();
    std::fs::write(
        dir.join("Cargo.toml"),
        "[package]\nname = \"t\"\nversion = \"0.0.0\"\nedition = \"2021\"\n",
    )
    .unwrap();
    std::fs::write(
        dir.join("Cargo.lock"),
        "version = 4\n\n[[package]]\nname = \"t\"\nversion = \"0.0.0\"\n",
    )
    .unwrap();
    std::fs::write(dir.join("src/lib.rs"), "pub fn f() {}\n").unwrap();
    let made = tools
        .produce(&dir, &dir.join("Cargo.toml"), real_cache())
        .map_err(|e| e.describe())
        .unwrap();
    assert!(made.runs.iter().all(|run| !run.units.is_empty()));
}

/// The text of each facts file of one configuration whose name starts with `krate-`.
fn facts_of(run: &crate::rustc_facts::FactsRun, krate: &str) -> String {
    let prefix = format!("{krate}-");
    let files = std::fs::read_dir(&run.dir)
        .unwrap()
        .map(|e| e.unwrap().path());
    let mine = files.filter(|f| {
        let name = f.file_name().unwrap().to_string_lossy().to_string();
        name.starts_with(&prefix) && !name.ends_with("-test.jsonl")
    });
    mine.map(|f| std::fs::read_to_string(f).unwrap()).collect()
}

/// A scan with a warm cache after an edit of a dependent crate gives the facts of a cold scan. Cargo keeps
/// the unchanged members fresh, so the driver does not run for them: the crate ids of the members must
/// survive in the registry, or the types of a fresh member look foreign in the dependent (a Codex review
/// finding of #1964). `rn_pkg::erase_any` is a function of a member: the call from `fx` seeds it.
#[test]
#[ignore = "needs the pinned toolchain with rustc-dev; run `make rustc-facts-e2e`"]
fn a_warm_scan_after_an_edit_gives_the_facts_of_a_cold_scan() {
    let _one = REAL.lock().unwrap_or_else(|e| e.into_inner());
    let tools = real_tools();
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/rust_reach_fixtures/coll");
    let ws = real_cache().join("warm-coll");
    std::fs::create_dir_all(real_cache()).unwrap();
    let _ = std::fs::remove_dir_all(&ws);
    let copied = Command::new("cp")
        .arg("-R")
        .arg(&source)
        .arg(&ws)
        .status()
        .unwrap();
    assert!(copied.success());
    let ws = ws.canonicalize().unwrap();
    let manifest = ws.join("crates/Cargo.toml");
    let (warm_cache, cold_cache) = (real_cache().join("warm"), real_cache().join("cold"));
    let first = tools
        .produce(&ws, &manifest, &warm_cache)
        .map_err(|e| e.describe())
        .unwrap();
    assert!(facts_of(&first.runs[0], "fx").contains("rn_pkg::erase_any"));
    let main = ws.join("crates/fx/src/main.rs");
    let text = std::fs::read_to_string(&main).unwrap();
    std::fs::write(&main, format!("{text}\n// edited\n")).unwrap();
    let warm = tools
        .produce(&ws, &manifest, &warm_cache)
        .map_err(|e| e.describe())
        .unwrap();
    let cold = tools
        .produce(&ws, &manifest, &cold_cache)
        .map_err(|e| e.describe())
        .unwrap();
    for (w, c) in warm.runs.iter().zip(&cold.runs) {
        let (warm_fx, cold_fx) = (facts_of(w, "fx"), facts_of(c, "fx"));
        assert_eq!(
            warm_fx.matches("rn_pkg::erase_any").count() > 0,
            cold_fx.matches("rn_pkg::erase_any").count() > 0,
            "the warm facts of fx in {} differ from the cold facts",
            w.config.cfg_name()
        );
        assert_eq!(warm_fx.lines().count(), cold_fx.lines().count());
    }
}
