// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The producer of compiler type-reach facts (AD-1047).
//!
//! It checks the pinned toolchain and `rustc-dev`, builds the rustc driver in a cache directory, and
//! runs `cargo check --all-targets` of the scanned workspace with the driver as
//! `RUSTC_WORKSPACE_WRAPPER`, once for each configuration of the matrix. Each unit writes one facts
//! file. The producer installs nothing and has no fallback: a failure is one typed cause, and the
//! reader keeps every gap of the syntax scan. `archkeel_rust_collector::type_reach` verifies the facts.
//!
//! Cargo skips a fresh unit, and the driver does not run for it. So the target and raw directories of a
//! configuration persist together. Each run writes the facts directory again from the raw files of the
//! units that Cargo reported, so a stale file of a removed crate never reaches the reader.

use archkeel_facts::identity::sha256_hex;
use archkeel_facts::type_reach::{Config, Unavailable};
use serde_json::Value;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::rustc_facts_members::{configs, flags, members, set_driver_vars, Members, KEPT_ENV};
use crate::rustc_facts_merge::compact;

/// Each file of `tools/rustc-facts` that a build needs, with its path inside that crate.
macro_rules! driver_files {
    ($($name:literal),*) => {
        [$(($name, include_str!(concat!("../../../tools/rustc-facts/", $name)))),*]
    };
}

/// The toolchain file of the driver: its channel is the pin.
const TOOLCHAIN: &str = include_str!("../../../tools/rustc-facts/rust-toolchain.toml");

pub(crate) const SOURCES: [(&str, &str); 13] = driver_files![
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "src/body.rs",
    "src/bounds.rs",
    "src/items.rs",
    "src/json.rs",
    "src/main.rs",
    "src/names.rs",
    "src/out.rs",
    "src/reach.rs",
    "src/selected.rs",
    "src/state.rs"
];

/// The channel in the text of a `rust-toolchain.toml`.
pub(crate) fn channel_of(toolchain: &str) -> Option<&str> {
    let line = toolchain
        .lines()
        .find(|l| l.trim_start().starts_with("channel"))?;
    line.split('"').nth(1)
}

/// The channel that the driver pins.
pub(crate) fn channel() -> Option<&'static str> {
    channel_of(TOOLCHAIN)
}

/// The SHA-256 of the names and the texts of the driver source, in a fixed order.
pub(crate) fn sha256() -> String {
    let mut all = Vec::new();
    for (name, text) in SOURCES {
        all.extend_from_slice(format!("{name}\0{}\0", text.len()).as_bytes());
        all.extend_from_slice(text.as_bytes());
    }
    sha256_hex(&all)
}

const WORK_CACHE_LIMIT: usize = 3;

fn prune_work(work: &Path) {
    let Some(parent) = work.parent() else { return };
    if let Err(error) = std::fs::create_dir_all(work) {
        eprintln!("rustc facts: cannot prepare work cache: {error}");
        return;
    }
    let marker = work.join("last-used");
    if let Err(error) = std::fs::File::create(marker) {
        eprintln!("rustc facts: cannot update work cache marker: {error}");
    }
    let entries = match std::fs::read_dir(parent) {
        Ok(entries) => entries,
        Err(error) => {
            eprintln!("rustc facts: cannot read work cache: {error}");
            return;
        }
    };
    let mut others: Vec<_> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path != work && path.is_dir())
        .collect();
    others.sort_by_key(|path| {
        std::fs::metadata(path.join("last-used"))
            .and_then(|metadata| metadata.modified())
            .ok()
    });
    let remove = others.len().saturating_sub(WORK_CACHE_LIMIT - 1);
    for path in others.into_iter().take(remove) {
        if let Err(error) = std::fs::remove_dir_all(&path) {
            eprintln!("rustc facts: cannot remove {}: {error}", path.display());
        }
    }
}

/// `rustup run <channel> cargo <subcommand> --offline` with a clean environment. An empty `RUSTFLAGS`
/// beats the `build.rustflags` and `target.<triple>.rustflags` of each config file; the options below
/// set the rest of `[build]` that could change the compiler or the flags.
pub(crate) fn sealed(rustup: &Path, channel: &str, subcommand: &str) -> Command {
    let mut cmd = Command::new(rustup);
    cmd.args(["run", channel, "cargo", subcommand, "--offline"]);
    cmd.args(["--config", "build.rustflags=[]"]);
    cmd.args(["--config", "build.rustc-wrapper=\"\""]);
    cmd.args(["--config", "build.rustc=\"rustc\""]);
    cmd.env_clear().env("RUSTFLAGS", "");
    for name in KEPT_ENV {
        if let Some(value) = std::env::var_os(name) {
            cmd.env(name, value);
        }
    }
    cmd
}

/// The driver binary for this source and channel. It is built on first use.
fn ensure(rustup: &Path, channel: &str, sha: &str, cache: &Path) -> Result<PathBuf, Unavailable> {
    let dir = cache.join(format!("{channel}-{sha}"));
    let name = format!("archkeel-rustc-facts{}", std::env::consts::EXE_SUFFIX);
    let binary = dir.join("target/release").join(name);
    if binary.is_file() {
        return Ok(binary);
    }
    let fail = |_: std::io::Error| Unavailable::DriverBuildFailed;
    for (name, text) in SOURCES {
        let file = dir.join(name);
        std::fs::create_dir_all(file.parent().unwrap_or(&dir)).map_err(fail)?;
        std::fs::write(&file, text).map_err(fail)?;
    }
    let built = sealed(rustup, channel, "build")
        .args(["--release", "--locked", "--manifest-path"])
        .arg(dir.join("Cargo.toml"))
        // `rustc_private` is unstable: this is the stated limit of the driver on a stable toolchain.
        .env("RUSTC_BOOTSTRAP", "1")
        .env("CARGO_TARGET_DIR", dir.join("target"))
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    match built {
        Ok(status) if status.success() && binary.is_file() => Ok(binary),
        _ => Err(Unavailable::DriverBuildFailed),
    }
}

/// The programs that the producer starts. A test replaces `rustup` to simulate a missing toolchain.
pub(crate) struct FactsTools {
    pub(crate) rustup: PathBuf,
}

impl FactsTools {
    /// `rustup` from the `PATH`.
    pub(crate) fn system() -> FactsTools {
        FactsTools {
            rustup: PathBuf::from("rustup"),
        }
    }

    /// Produce the facts of the Cargo workspace at `manifest` (a `Cargo.toml`) for each configuration.
    ///
    /// `scan_root` is the root of the scan: the facts record each path relative to it. `cache` is the
    /// directory for the driver build and for the target and facts directories.
    pub(crate) fn produce(
        &self,
        scan_root: &Path,
        manifest: &Path,
        cache: &Path,
    ) -> Result<FactsProduced, Unavailable> {
        produce(self, scan_root, manifest, cache)
    }
}

/// The facts of one configuration.
pub(crate) struct FactsRun {
    pub(crate) config: Config,
    pub(crate) dir: PathBuf,
    pub(crate) units: Vec<String>,
    pub(crate) elapsed: Duration,
}

/// What the producer made, with the binding values that the reader expects.
pub(crate) struct FactsProduced {
    pub(crate) rustc: String,
    pub(crate) target_triple: String,
    pub(crate) driver_sha256: String,
    pub(crate) cargo_lock_sha256: String,
    /// The directory of each workspace member, relative to the scan root, with a closing slash.
    pub(crate) members: Vec<String>,
    pub(crate) runs: Vec<FactsRun>,
}

fn output_of(tools: &FactsTools, args: &[&str]) -> Option<String> {
    let out = Command::new(&tools.rustup).args(args).output().ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).to_string())
}

/// The text of `rustc -vV` of the pinned toolchain, and whether it has `rustc-dev`.
pub(crate) fn toolchain(tools: &FactsTools, channel: &str) -> Result<String, Unavailable> {
    let rustc =
        output_of(tools, &["run", channel, "rustc", "-vV"]).ok_or(Unavailable::ToolchainMissing)?;
    let installed = output_of(
        tools,
        &["component", "list", "--installed", "--toolchain", channel],
    );
    let has_dev = installed.is_some_and(|list| list.lines().any(|l| l.starts_with("rustc-dev")));
    if has_dev {
        Ok(rustc)
    } else {
        Err(Unavailable::RustcDevMissing)
    }
}

struct Job<'a> {
    tools: &'a FactsTools,
    channel: &'a str,
    manifest: &'a Path,
    driver: &'a Path,
    root: &'a str,
    driver_sha256: &'a str,
    lock_sha256: &'a str,
    work: &'a Path,
    members: &'a Members,
}

/// The units of the workspace that `cargo check` reported, fresh ones too. The name of a unit is the
/// crate name and the metadata hash of its `.rmeta` file, as the driver names its file, and `-test`.
pub(crate) fn units_of(stdout: &str, members: &BTreeSet<String>) -> BTreeSet<String> {
    let mut units = BTreeSet::new();
    for message in stdout
        .lines()
        .filter_map(|l| serde_json::from_str::<Value>(l).ok())
    {
        let text =
            |value: &Value, key: &str| value.get(key).and_then(Value::as_str).map(str::to_string);
        let member = text(&message, "manifest_path").is_some_and(|m| members.contains(&m));
        let kinds = message.pointer("/target/kind").and_then(Value::as_array);
        let script = kinds.is_some_and(|k| k.iter().any(|kind| kind == "custom-build"));
        let rmeta = message
            .get("filenames")
            .and_then(Value::as_array)
            .and_then(|all| {
                all.iter()
                    .filter_map(Value::as_str)
                    .find(|f| f.ends_with(".rmeta"))
                    .map(str::to_string)
            });
        if text(&message, "reason").as_deref() != Some("compiler-artifact") || !member || script {
            continue;
        }
        let stem = rmeta.and_then(|f| {
            Path::new(&f)
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
        });
        let test = message.pointer("/profile/test") == Some(&Value::Bool(true));
        units.extend(stem.map(|s| {
            format!(
                "{}{}",
                s.trim_start_matches("lib"),
                if test { "-test" } else { "" }
            )
        }));
    }
    units
}

/// Run `cargo check` for one configuration: the units that it reported, or `None` when it fails.
fn run_check(job: &Job<'_>, config: &Config, raw: &Path) -> Option<BTreeSet<String>> {
    let base = raw.parent()?;
    std::fs::create_dir_all(raw).ok()?;
    let log = std::fs::File::create(base.join("cargo.log")).ok()?;
    let mut cmd = sealed(&job.tools.rustup, job.channel, "check");
    cmd.args([
        "--workspace",
        "--all-targets",
        "--locked",
        "--message-format=json",
    ])
    .args(flags(config))
    .arg("--manifest-path")
    .arg(job.manifest)
    .current_dir(job.manifest.parent().unwrap_or(job.manifest))
    .env("CARGO_TARGET_DIR", base.join("target"))
    .env("RUSTC_WORKSPACE_WRAPPER", job.driver)
    .stderr(log);
    let base_vars = [
        ("AK_FACTS_DIR", raw.display().to_string()),
        ("AK_FACTS_CFG", config.cfg_name()),
        ("AK_FACTS_ROOT", job.root.to_string()),
        ("AK_FACTS_DRIVER_SHA256", job.driver_sha256.to_string()),
        ("AK_FACTS_LOCK_SHA256", job.lock_sha256.to_string()),
    ];
    set_driver_vars(&mut cmd, base, job.members, &base_vars)?;
    let output = cmd.output().ok()?;
    let text = String::from_utf8_lossy(&output.stdout);
    output
        .status
        .success()
        .then(|| units_of(&text, &job.members.manifests))
}

/// Run `cargo check` for one configuration, then write the facts directory.
fn check(job: &Job<'_>, config: Config) -> Result<FactsRun, Unavailable> {
    let base = job.work.join(config.dir_name());
    let (raw, facts) = (base.join("raw"), base.join("facts"));
    let started = Instant::now();
    let Some(units) = run_check(job, &config, &raw) else {
        return Err(Unavailable::CargoCheckFailed(config));
    };
    compact(&raw, &facts, &units)?;
    let units = units.into_iter().collect();
    Ok(FactsRun {
        config,
        dir: facts,
        units,
        elapsed: started.elapsed(),
    })
}

fn produce(
    tools: &FactsTools,
    scan_root: &Path,
    manifest: &Path,
    cache: &Path,
) -> Result<FactsProduced, Unavailable> {
    // Both sides are real paths: macOS `/var` is `/private/var`, and the driver compares text.
    let real = |path: &Path| {
        path.canonicalize()
            .map_err(|_| Unavailable::CargoCheckFailed(Config::Default))
    };
    let (scan_root, manifest) = (&real(scan_root)?, &real(manifest)?);
    let channel = channel().ok_or(Unavailable::ToolchainMissing)?;
    let rustc = toolchain(tools, channel)?;
    let sha = sha256();
    let binary = ensure(&tools.rustup, channel, &sha, cache)?;
    let lock = std::fs::read(manifest.with_file_name("Cargo.lock"))
        .map_err(|_| Unavailable::CargoCheckFailed(Config::Default))?;
    let lock_sha256 = sha256_hex(&lock);
    let key = sha256_hex(manifest.display().to_string().as_bytes());
    let work = cache
        .join("work")
        .join(format!("{channel}-{}-{}", &sha[..16], &key[..16]));
    let metadata = sealed(&tools.rustup, channel, "metadata")
        .args([
            "--format-version",
            "1",
            "--no-deps",
            "--locked",
            "--manifest-path",
        ])
        .arg(manifest)
        .output()
        .ok()
        .filter(|out| out.status.success())
        .ok_or(Unavailable::MetadataFailed)?;
    let members = members(&metadata.stdout, scan_root)?;
    // Cargo keeps a unit fresh when only `Cargo.lock` changed, and its raw file would carry the old hash. A
    // fresh member does not run the driver, so its registry entry (its crate id) must be of this member set:
    // one lock and one member set, one work directory.
    let marker = work.join("identity.sha256");
    let identity = sha256_hex(format!("{lock_sha256}\n{:?}", members.roots).as_bytes());
    if std::fs::read_to_string(&marker).ok().as_deref() != Some(identity.as_str()) {
        let _ = std::fs::remove_dir_all(&work);
        std::fs::create_dir_all(&work)
            .and_then(|()| std::fs::write(&marker, &identity))
            .map_err(|_| Unavailable::CargoCheckFailed(Config::Default))?;
    }

    prune_work(&work);
    let configs = configs(&members)?;
    let root = format!("{}/", scan_root.display());
    let job = Job {
        tools,
        channel,
        manifest,
        driver: &binary,
        root: &root,
        driver_sha256: &sha,
        lock_sha256: &lock_sha256,
        work: &work,
        members: &members,
    };
    let runs = configs
        .into_iter()
        .map(|config| check(&job, config))
        .collect::<Result<Vec<_>, _>>()?;
    let target_triple = rustc
        .lines()
        .find_map(|l| l.strip_prefix("host: "))
        .unwrap_or_default()
        .to_string();
    Ok(FactsProduced {
        rustc,
        target_triple,
        driver_sha256: sha,
        cargo_lock_sha256: lock_sha256,
        members: members.dirs,
        runs,
    })
}

#[cfg(test)]
#[path = "rustc_facts_tests.rs"]
mod tests;
