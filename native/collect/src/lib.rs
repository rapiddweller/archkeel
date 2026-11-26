// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-collect: the composition between the core and the collectors (AD-406, #1095).
//!
//! It is the only crate that names a language. The core gives it the scan identity: the
//! repository root, the location of the configuration, and the Git head and dirty state that the
//! shell read. It reads the configuration itself, derives the profile, the scan roots, the
//! namespace, the test scope and the resolver settings. It starts a sibling worker or
//! runs the linked collector for another profile. It gives the store the typed reply and returns the validated
//! reply and the contract bytes, or a `Refusal` that names the part it cannot run. No plugin, no
//! trait: one function selects the collector.
//!
//! Trust: the core trusts the reply because it ran the collector itself; no digest and no reply
//! bytes come from the caller. The caller still chooses the root and the configuration file, and
//! the shell still gives the dirty state as provenance (AD-406 names what stage 2 needs).

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]

mod config;
mod dart;
mod entry_points;
mod git;
mod outside_reach;
mod python;
mod refusal;
mod repository;
mod run;
mod rustc_facts;
mod rustc_facts_members;
mod rustc_facts_merge;
mod system;
mod worker;

pub use system::{System, SystemPart};

use std::path::{Path, PathBuf};
use std::time::Duration;

use archkeel_store::Ingested;
use serde_json::{json, Value};

use crate::refusal::refused;
pub use crate::refusal::{Refusal, RefusalKind};
pub use crate::repository::Over;
pub use crate::run::check;
#[cfg(test)]
pub(crate) use crate::run::reply_of;
use archkeel_facts::envelope::Profile;

/// What the caller gives: the scan identity, never facts.
pub struct Identity<'a> {
    /// The canonical absolute repository root.
    pub root: &'a str,
    /// The repository-relative path of the configuration file.
    pub config: &'a str,
    /// Discover the work tree from `root` only when the caller supplied no explicit root.
    pub discover_root: bool,
    /// An optional claim about `HEAD`; the core reads it and refuses a difference.
    pub git_head: Option<&'a str>,
    /// An optional claim about the work tree; the core reads it and refuses a difference.
    pub dirty: Option<bool>,
}

/// The result of one scan: what the core needs to decide the run.
pub struct Scanned {
    /// The profile whose collector made the reply; the core reads its name (`collector`).
    profile: Profile,
    /// The scan roots of the contract.
    pub roots: Vec<String>,
    /// The namespace of the scanned code.
    pub namespace: String,
    /// The repository path of the root contract and its bytes.
    pub contract: (String, Vec<u8>),
    /// The collection request that the core derived, as the wire writes it.
    pub request: Value,
    /// The reply of the linked collector, validated once by the store.
    pub reply: Ingested,
    /// The time of the configuration, the Git state and the survey, before the collector (#659).
    pub prepared: Duration,
    /// The time of the linked collector, on its own thread.
    pub collected: Duration,
    /// The time of the one validation of the reply by the store, with the checks of its profile.
    pub validated: Duration,
    /// The Explorer default left test sources out because the config states no scope (AD-1119).
    implicit_test_exclusion: bool,
    root: repository::Root,
}

impl Scanned {
    /// The entry points that the manifests and the files of the scan prove (#2040); `None` when no
    /// reader exists for the language of the scan.
    pub fn entry_points(&self) -> Option<archkeel_facts::data::entry_points::EntryPoints> {
        let files: Vec<(&str, &str)> = (self.reply.reply().facts.files.iter())
            .map(|file| (file.module.as_str(), file.rel_path.as_str()))
            .collect();
        entry_points::read(&self.root, self.profile, &files)
    }

    /// AD-1119: a scan that left test sources out because the config states no scope holds the verdict. A file
    /// that the naming rule took for a test can hold the only violation, so the run cannot read PASS.
    pub fn test_scope_hold(&self) -> Option<String> {
        let excluded = &self.reply.reply().facts.excluded_sources;
        let first: Vec<&str> = excluded.iter().take(3).map(String::as_str).collect();
        (self.implicit_test_exclusion && !excluded.is_empty()).then(|| {
            format!(
                "implicit test exclusion hides {} files ({}): the config states no exclude_test_sources, \
                 so the verdict is held; state it in archkeel.toml to decide the scope",
                excluded.len(),
                first.join(", ")
            )
        })
    }

    /// The name of the collector that made the reply: the adapter name that its reply must have.
    pub fn collector(&self) -> &'static str {
        self.profile.as_str()
    }

    /// An inside contract: its identity and bytes, `None` when the path is missing, not a file
    /// or outside the root, and `Over` above `budget` bytes (`read_inside` of the shell).
    pub fn read_inside(
        &self,
        reference: &str,
        budget: u64,
    ) -> Result<Option<(String, Vec<u8>)>, Over> {
        self.root.read(reference, budget)
    }
}

/// The system document that the configuration of `identity` names, or `None` for the
/// configuration of one scan (AD-616). It is read with the safe reader of the scan.
pub fn read_system(identity: &Identity<'_>) -> Result<Option<System>, Refusal> {
    if !identity.config.ends_with(".json") {
        return Ok(None);
    }
    repository::safe_config(identity.config)?;
    system::read(&root_of(identity)?, identity.config)
}

/// The test features of the linked collectors. A build with one cannot give an accepted reply.
pub(crate) fn test_features() -> &'static [&'static str] {
    [
        archkeel_python_collector::TEST_FEATURES,
        archkeel_dart_collector::TEST_FEATURES,
    ]
    .into_iter()
    .find(|features| !features.is_empty())
    .unwrap_or_default()
}

/// Scan the repository of `identity` with the collector of its profile. `contract_budget` bounds
/// the bytes of the root contract. The phase durations are zero without a clock.
pub fn scan(identity: &Identity<'_>, contract_budget: u64) -> Result<Scanned, Refusal> {
    scan_with_clock(identity, contract_budget, None)
}

/// Scan with an optional monotonic elapsed-time source from the caller. It must not decrease.
pub fn scan_with_clock(
    identity: &Identity<'_>,
    contract_budget: u64,
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<Scanned, Refusal> {
    scan_with_options(identity, contract_budget, clock, false)
}

/// Include navigation-only source candidates when the caller requests Explorer records.
pub fn scan_with_options(
    identity: &Identity<'_>,
    contract_budget: u64,
    clock: Option<&dyn Fn() -> Duration>,
    explorer: bool,
) -> Result<Scanned, Refusal> {
    let started = clock.map(|now| now());
    built(test_features())?;
    let root = root_of(identity)?;
    let root_text = root
        .path()
        .to_str()
        .ok_or_else(|| refused("root", "the root is not UTF-8"))?;
    let mut config = read_config(&root, identity.config)?;
    // AD-1119: the Explorer leaves test sources out unless the config states the scope. `validate` and `report` keep tests.
    let implicit = explorer
        && !config.test_scope_set
        && matches!(config.profile, Profile::Python | Profile::TypeScript);
    config.exclude_test_sources |= implicit;
    let head = git::head(root.path()).map_err(|why| refused("git head", why))?;
    if let Some(claimed) = identity.git_head {
        if head != claimed {
            return Err(refused(
                "git head",
                format!("the shell names the commit {claimed}, and HEAD is {head}"),
            ));
        }
    }
    repository::survey(&root).map_err(|why| refused("work budget", why))?;
    let dirty = git::dirty(root.path()).map_err(|why| refused("dirty", why))?;
    if identity.dirty.is_some_and(|claimed| claimed != dirty) {
        return Err(refused("dirty", "the request differs from the repository"));
    }
    let derived = Identity {
        root: root_text,
        config: identity.config,
        discover_root: false,
        git_head: Some(&head),
        dirty: Some(dirty),
    };
    let mut request = request(&derived, &config);
    if let Some(target) = &config.python {
        request["resolver"]["python"] = json!(target);
    }
    let bytes =
        serde_json::to_vec(&request).map_err(|error| refused("request", error.to_string()))?;
    let prepared = clock
        .zip(started)
        .map_or(Duration::ZERO, |(now, start)| now() - start);
    let descriptor = config
        .rust_type_reach
        .then(|| type_reach_descriptor(&root, &config))
        .transpose()?;
    let members = matches!(config.profile, Profile::Rust)
        .then(|| rustc_facts_members::for_worker(root.path(), &config.roots));
    let collected_reply = run::collect_timed(
        config.profile,
        &bytes,
        clock,
        (
            explorer,
            descriptor.as_ref().map(|(path, _)| path.as_path()),
            members.as_deref(),
        ),
    );
    if let Some((path, _)) = &descriptor {
        let _ = std::fs::remove_file(path);
    }
    let (reply, collected, validated) = collected_reply?;
    let bound = match config.profile {
        Profile::Python => python::bound(&root, reply.reply()),
        Profile::Dart => dart::bound(&root, reply.reply()),
        Profile::TypeScript | Profile::Rust => Ok(()),
    };
    bound.map_err(|why| refused("collector", why))?;
    let contract = match root.read(&config.contract, contract_budget) {
        Ok(Some((_, bytes))) => bytes,
        Ok(None) => return Err(refused("contract", "the core cannot read the contract")),
        Err(Over(path)) => {
            return Err(refused(
                "contract",
                format!("{path} holds more than {contract_budget} bytes"),
            ))
        }
    };
    Ok(Scanned {
        profile: config.profile,
        roots: config.roots,
        namespace: config.namespace,
        contract: (config.contract, contract),
        request,
        reply,
        prepared,
        collected,
        validated,
        implicit_test_exclusion: implicit,
        root,
    })
}

/// The descriptor of produced facts: what the Rust worker verifies (`ARCHKEEL_TYPE_REACH`).
fn descriptor_of(made: &rustc_facts::FactsProduced) -> Value {
    let configs: Vec<Value> = made
        .runs
        .iter()
        .map(|run| json!({"name": run.config.cfg_name(), "dir": run.dir, "units": run.units, "seconds": run.elapsed.as_secs_f64()}))
        .collect();
    json!({"rustc": made.rustc, "target_triple": made.target_triple, "driver_sha256": made.driver_sha256, "cargo_lock_sha256": made.cargo_lock_sha256, "members": made.members, "configs": configs})
}

/// AD-1047: produce the compiler facts of the Rust workspace and write the descriptor that the Rust worker
/// reads (`ARCHKEEL_TYPE_REACH`). A missing toolchain, a failed build or a failed check is written into the
/// descriptor as its cause: the worker keeps every gap and says why. Only a descriptor that cannot be
/// written refuses the scan, because the worker would then run without facts and without a reason.
/// The reason why the facts may not be used: the compiler type reach is a premise (AD-1047), and a
/// contract that does not declare it must not get a PASS that rests on it. `None` when it is declared.
fn premise_missing(root: &Path, contract: &str) -> Option<String> {
    let word = archkeel_facts::type_reach::PREMISE;
    let read = std::fs::read(root.join(contract)).ok();
    let parsed = read.and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());
    let premises = parsed
        .as_ref()
        .and_then(|c| c["declarations"]["premises"].as_array());
    let declared = premises.is_some_and(|all| all.iter().any(|p| p["name"] == word));
    (!declared).then(|| format!("the contract does not declare the premise {word}"))
}

/// AD-1130: the one operator permission to compile the scanned repository. Only the process
/// environment can grant it. No file of the repository can, and the sealed Cargo run does not inherit it.
pub(crate) const ALLOW_BUILD: &str = "ARCHKEEL_ALLOW_BUILD";

/// The typed gap when the repository asks for compilation and the operator did not allow it.
const NOT_ALLOWED: &str = "type reach not allowed by the operator";

fn build_allowed() -> bool {
    std::env::var_os(ALLOW_BUILD).is_some_and(|value| value == "1")
}

fn type_reach_descriptor(
    root: &repository::Root,
    config: &config::Config,
) -> Result<(PathBuf, std::fs::File), Refusal> {
    let base = std::env::var_os("ARCHKEEL_FACTS_CACHE")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("HOME")
                .map(|home| PathBuf::from(home).join(".cache/archkeel/rustc-facts"))
        })
        .ok_or_else(|| refused("type reach", "no cache directory: set ARCHKEEL_FACTS_CACHE"))?;
    std::fs::create_dir_all(&base)
        .map_err(|why| refused("type reach", format!("cannot create cache: {why}")))?;
    let lock = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(base.join("work.lock"))
        .map_err(|why| refused("type reach", format!("cannot open cache lock: {why}")))?;
    lock.lock()
        .map_err(|why| refused("type reach", format!("cannot lock cache: {why}")))?;
    let manifest = config
        .roots
        .iter()
        .map(|r| root.path().join(r).join("Cargo.toml"))
        .find(|m| m.is_file())
        .unwrap_or_else(|| root.path().join("Cargo.toml"));
    let text = match premise_missing(root.path(), &config.contract) {
        _ if !build_allowed() => json!({"unavailable": NOT_ALLOWED}),
        Some(why) => json!({"unavailable": why}),
        None => match rustc_facts::FactsTools::system().produce(root.path(), &manifest, &base) {
            Err(cause) => {
                json!({"unavailable": archkeel_facts::type_reach::Unavailable::describe(&cause)})
            }
            Ok(made) => descriptor_of(&made),
        },
    };
    static COUNT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let unique = COUNT.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    let dir = base.join("descriptors");
    let path = dir.join(format!("{}-{unique}.json", std::process::id()));
    std::fs::create_dir_all(&dir)
        .and_then(|()| std::fs::write(&path, text.to_string()))
        .map_err(|why| refused("type reach", format!("cannot write the descriptor: {why}")))?;
    Ok((path, lock))
}

/// A build of a collector with a test feature reads planted faults from the environment
/// (`plant.rs`), so it gives no reply that the core accepts (AD-406, #1099).
fn built(features: &[&str]) -> Result<(), Refusal> {
    match features.first() {
        None => Ok(()),
        Some(feature) => Err(refused(
            "build",
            format!("the linked collector has the test feature {feature}"),
        )),
    }
}

/// The repository root of `identity`: the supplied root, or its work tree when the shell supplied
/// no explicit root.
fn root_of(identity: &Identity<'_>) -> Result<repository::Root, Refusal> {
    let supplied = repository::Root::of(identity.root).map_err(|why| refused("root", why))?;
    if !identity.discover_root {
        return Ok(supplied);
    }
    let repository = git::root(supplied.path()).map_err(|why| refused("root", why))?;
    let text = repository
        .to_str()
        .ok_or_else(|| refused("root", "the root is not UTF-8"))?;
    repository::Root::of(text).map_err(|why| refused("root", why))
}

/// The configuration at `path`, with the checks of `load_config` against the repository.
fn read_config(root: &repository::Root, path: &str) -> Result<config::Config, Refusal> {
    repository::safe_config(path)?;
    let payload = match root.read(path, repository::MAX_CONFIG_BYTES) {
        Ok(Some((_, payload))) => payload,
        Ok(None) => return Err(refused("config", format!("cannot read {path}"))),
        Err(Over(_)) => return Err(refused("config", format!("{path} is too large"))),
    };
    let config = config::parse(&payload, path).map_err(|refusal| match refusal {
        config::Refused::Invalid(why) => refused("config", why),
        config::Refused::Unsupported(part, why) => refused(part, why),
    })?;
    for relative in &config.roots {
        if !root.is_dir_or_file(relative, true) {
            return Err(refused(
                "config",
                format!("scan root is not a directory or file: {relative}"),
            ));
        }
    }
    if !root.is_file(&config.contract) {
        let reason = format!("scan contract is not a file: {}", config.contract);
        return Err(refused("config", reason));
    }
    if config.profile == Profile::TypeScript && !root.is_file(&config.tsconfig) {
        let reason = format!("scan TypeScript config is not a file: {}", config.tsconfig);
        return Err(refused("config", reason));
    }
    Ok(config)
}

/// The request that the shell sends to a bundled collector (`observer_for`,
/// `collection_request`, `ProcessCollector`): 8.0.0, or 9.0.0 with the test scope. A Python
/// request is 10.0.0 and always states its test scope (AD-450).
fn request(identity: &Identity<'_>, config: &config::Config) -> Value {
    let mut scope = json!({"roots": config.roots, "namespace": config.namespace});
    let version = if config.profile == Profile::Python {
        scope["exclude_test_sources"] = Value::Bool(config.exclude_test_sources);
        "10.0.0"
    } else if config.exclude_test_sources {
        scope["exclude_test_sources"] = Value::Bool(true);
        "9.0.0"
    } else {
        "8.0.0"
    };
    let mut resolver = match config.profile {
        Profile::Rust => json!({"language": "rust"}),
        Profile::Python => python::resolver(),
        Profile::Dart => dart::resolver(),
        _ => json!({"language": "typescript", "tsconfig": config.tsconfig}),
    };
    if config.bundler {
        resolver["bundler"] = Value::Bool(true);
    }
    if config.import_roots_ambiguous {
        resolver["import_roots_ambiguous"] = Value::Bool(true);
    }
    json!({
        "protocol_version": version,
        "snapshot": {"root": identity.root, "git_head": identity.git_head, "dirty": identity.dirty},
        "scope": scope,
        "resolver": resolver,
    })
}

#[cfg(test)]
#[path = "lib_tests.rs"]
mod tests;

#[cfg(test)]
mod rust_tests;

#[cfg(test)]
#[path = "work_tests.rs"]
mod work_tests;
