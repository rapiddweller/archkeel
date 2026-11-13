// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-collect: the composition between the core and the collectors (AD-406, #1095).
//!
//! It is the only crate that names a language. The core gives it the scan identity: the
//! repository root, the location of the configuration, and the Git head and dirty state that the
//! shell read. It reads the configuration itself, derives the profile, the scan roots, the
//! namespace, the test scope and the resolver settings, runs the linked collector of the profile
//! in the process of the core, and gives the store the typed reply. It returns the validated
//! reply and the contract bytes, or a `Refusal` that names the part it cannot run. No plugin, no
//! trait: one function for the linked TypeScript and Rust profiles.
//!
//! Trust: the core trusts the reply because it ran the collector itself; no digest and no reply
//! bytes come from the caller. The caller still chooses the root and the configuration file, and
//! the shell still gives the dirty state as provenance (AD-406 names what stage 2 needs).

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]

mod config;
mod git;
mod repository;
mod run;

use archkeel_store::Ingested;
use serde_json::{json, Value};

pub use crate::repository::Over;
pub use crate::run::reply_of;
pub use archkeel_facts::envelope::Profile;

/// The first words of each refusal; the shell counts them.
pub const REFUSED: &str = "collect";

/// What the caller gives: the scan identity, never facts.
pub struct Identity<'a> {
    /// The canonical absolute repository root.
    pub root: &'a str,
    /// The repository-relative path of the configuration file.
    pub config: &'a str,
    /// The commit of `HEAD` as the shell read it; the core reads it too and refuses a difference.
    pub git_head: &'a str,
    /// The dirty state of the work tree as the shell read it (provenance, AD-406).
    pub dirty: bool,
}

/// A part that the in-process path cannot run, by name. The shell keeps its stage 1 path.
#[derive(Debug, PartialEq, Eq)]
pub struct Refusal {
    pub part: &'static str,
    pub reason: String,
}

impl std::fmt::Display for Refusal {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            out,
            "{REFUSED}: unsupported: {}: {}",
            self.part, self.reason
        )
    }
}

fn refused(part: &'static str, reason: impl Into<String>) -> Refusal {
    Refusal {
        part,
        reason: reason.into(),
    }
}

/// The result of one scan: what the core needs to decide the run.
pub struct Scanned {
    /// The profile whose collector made the reply.
    pub profile: Profile,
    pub roots: Vec<String>,
    pub namespace: String,
    /// The repository path of the root contract and its bytes.
    pub contract: (String, Vec<u8>),
    /// The collection request that the core derived, as the wire writes it.
    pub request: Value,
    /// The reply of the linked collector, validated once by the store.
    pub reply: Ingested,
    root: repository::Root,
}

impl Scanned {
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

/// The test features of the linked collectors. A build with one cannot give an accepted reply.
pub fn test_features() -> &'static [&'static str] {
    if archkeel_rust_collector::TEST_FEATURES.is_empty() {
        archkeel_typescript_collector::TEST_FEATURES
    } else {
        archkeel_rust_collector::TEST_FEATURES
    }
}

/// Scan the repository of `identity` with the collector of its profile. `contract_budget` bounds
/// the bytes of the root contract.
pub fn scan(identity: &Identity<'_>, contract_budget: u64) -> Result<Scanned, Refusal> {
    built(test_features())?;
    let root = repository::Root::of(identity.root).map_err(|why| refused("root", why))?;
    let config = read_config(&root, identity.config)?;
    let head = git::head(root.path()).map_err(|why| refused("git head", why))?;
    if head != identity.git_head {
        return Err(refused(
            "git head",
            format!(
                "the shell names the commit {}, and HEAD is {head}",
                identity.git_head
            ),
        ));
    }
    let request = request(identity, &config);
    repository::survey(&root).map_err(|why| refused("work budget", why))?;
    let bytes =
        serde_json::to_vec(&request).map_err(|error| refused("request", error.to_string()))?;
    let reply = run::collect(&bytes).map_err(|why| refused("collector", why))?;
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
        root,
    })
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

/// The configuration at `path`, with the checks of `load_config` against the repository.
fn read_config(root: &repository::Root, path: &str) -> Result<config::Config, Refusal> {
    let safe = !path.is_empty()
        && path != "."
        && !path.starts_with('/')
        && !path.split('/').any(|part| part == "..")
        && !path.contains(['\0', '\\', ':', '*', '?', '[', ']', '{', '}', '!']);
    if !safe {
        return Err(refused(
            "config",
            "--config must be a safe POSIX relative path",
        ));
    }
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
/// `collection_request`, `ProcessCollector`): 8.0.0, or 9.0.0 with the test scope.
fn request(identity: &Identity<'_>, config: &config::Config) -> Value {
    let mut scope = json!({"roots": config.roots, "namespace": config.namespace});
    let version = if config.exclude_test_sources {
        scope["exclude_test_sources"] = Value::Bool(true);
        "9.0.0"
    } else {
        "8.0.0"
    };
    let mut resolver = match config.profile {
        Profile::Rust => json!({"language": "rust"}),
        _ => json!({"language": "typescript", "tsconfig": config.tsconfig}),
    };
    if config.bundler {
        resolver["bundler"] = Value::Bool(true);
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
