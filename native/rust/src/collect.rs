// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one request: a module for each file of a module tree, an import record for each
//! path that names another crate, and an UNKNOWN record for each place that the scan cannot read.
//!
//! This is slice 5b-1 of AD-335. The records are the crate edges. A path inside one crate gives
//! no record yet, so no rule about the modules of a crate can be decided from this collector.

use std::collections::{BTreeMap, BTreeSet};

use crate::type_reach::{Announced, Reached};
use archkeel_facts::envelope::Provenance;
use archkeel_facts::request::RustRequest;
use archkeel_snapshot::Snapshot;
use serde_json::Value;

use crate::builder::Builder;
use crate::crates::{discover, unproven_members, Workspace};
use crate::manifest::ident;
use crate::modules::index;
use crate::registry::Registry;
use crate::reply::Collected;
use crate::source::{read_text, walk as list_files};
use crate::test_scope::NO_PRODUCTION_SOURCE;
use crate::toml;
use crate::tree::{walk, Module};
use archkeel_facts::identity::sha256_hex;
use archkeel_facts::type_reach::MEMBERS_ENV;
use archkeel_snapshot::paths::{dirname, join, within};

/// Collect the facts of one request, with the type-reach facts that the descriptor of the environment names.
pub(crate) fn collect(request: &RustRequest, provenance: Provenance) -> Collected {
    collect_with(request, provenance, |source, files| {
        crate::type_reach::announced(|| rust_hashes(source, files))
    })
}

/// Collect the facts of one request; `announce` gives the type-reach facts (AD-1047).
pub(crate) fn collect_with(
    request: &RustRequest,
    provenance: Provenance,
    announce: impl FnOnce(&mut Snapshot, &[String]) -> Announced,
) -> Collected {
    let mut source = Snapshot::new(&request.snapshot.root);
    let mut builder = Builder::with_exclude_tests(request.excludes_test_sources());
    let (scope, files) = list(&mut source, &request.scope.roots, &mut builder);
    let (unavailable, reached) = load_facts(announce(&mut source, &files), &mut builder);
    let (files, foreign) = workspace_files(files, &mut source, &mut builder);
    let overrides = crate::registry_overrides::configs(&mut source);
    let mut workspace = discover(&mut source, &files, &request.scope.namespace);
    for krate in &mut workspace.crates {
        Registry::withhold(&mut krate.registry, &overrides);
    }
    // AD-774: a proof that rests on the identity in `Cargo.lock` is stated with the verdict.
    builder.lock_premise = workspace
        .crates
        .iter()
        .any(|krate| !krate.registry.packages.is_empty());
    let mut walked = walk(&mut source, &workspace, request.excludes_test_sources());
    hold_foreign_edges(&workspace, &walked.modules, &foreign, &mut builder);
    let proven: Vec<Vec<String>> = {
        let index = index(&workspace, &walked.modules);
        walked
            .modules
            .iter()
            .map(|module| {
                if module.scan.helper_types.is_empty() {
                    return Vec::new();
                }
                let local = crate::derive_imports::Local::of(module);
                let prove = |concern| {
                    crate::derive_identity::proven(
                        &workspace,
                        &index,
                        &local,
                        concern,
                        &walked.modules,
                    )
                };
                module
                    .scan
                    .helper_types
                    .iter()
                    .filter(|(_, concerns)| concerns.iter().all(&prove))
                    .map(|(name, _)| name.clone())
                    .collect()
            })
            .collect()
    };
    for (module, names) in walked.modules.iter_mut().zip(proven) {
        module.scan.exact_types.extend(names);
    }
    let modules: BTreeMap<&str, &str> = walked
        .modules
        .iter()
        .map(|module| (module.rel.as_str(), module.module.as_str()))
        .collect();
    for problem in source.problems.clone() {
        builder.gap(&problem, None, "");
    }
    for problem in workspace.problems.iter().chain(&walked.problems) {
        builder.problem(problem, &modules);
    }
    let modules_index = index(&workspace, &walked.modules);
    let builder_ref: &mut Builder = &mut builder;
    for module in &walked.modules {
        builder_ref.module(&workspace, &modules_index, module, &walked.modules);
    }
    builder_ref.macro_calls(&workspace, &modules_index, &walked.modules);
    builder_ref.impl_members(&workspace, &modules_index, &walked.modules);
    builder_ref.check_extracted(&walked.modules);
    builder_ref.calls(&walked.modules);
    let taken: BTreeSet<&str> = modules.values().copied().collect();
    builder_ref.declare_dependencies(&workspace, &request.scope.namespace, &taken, &mut source);
    let mut selected: Vec<String> = files
        .iter()
        .filter(|f| f.ends_with(".rs"))
        .cloned()
        .collect();
    let listed_rust = !selected.is_empty();
    selected.retain(|rel| !walked.is_excluded(rel));
    if listed_rust && selected.is_empty() {
        builder.gap(NO_PRODUCTION_SOURCE, None, "");
    }
    for rel in selected.iter().filter(|rel| !walked.claimed.contains(*rel)) {
        let reason = format!("Source file is in no module tree: {rel}");
        builder.gap(&reason, None, "");
    }
    selected.extend(builder.manifests.iter().cloned());
    selected.sort();
    // Free index maps and workspace before `finish` drops `walked` and materializes gaps (#1942).
    drop(modules_index);
    drop(taken);
    drop(modules);
    drop(workspace);
    if let Some(why) = unavailable {
        let reason = format!("The compiler type-reach facts are unavailable: {why}. Each trait-impl, destructor and receiver gap stays (AD-1047).");
        builder.gap(&reason, None, "");
    }
    let used = builder.reach_used;
    let mut collected = builder.finish(request, provenance, scope, selected, walked, source);
    collected.reached = reached.filter(|_| used);
    collected
}

/// AD-1047: the type-reach facts of the producer, or the cause why a scan that asked for them has none.
/// A failed check keeps every gap and says why; it never falls back to the old reach in silence.
fn load_facts(announced: Announced, builder: &mut Builder) -> (Option<String>, Option<Reached>) {
    match announced {
        None => (None, None),
        Some(Ok((facts, reached))) => {
            builder.type_reach = facts;
            (None, Some(reached))
        }
        Some(Err(why)) => (Some(why), None),
    }
}

/// The SHA-256 of each Rust file below the roots, by path.
fn rust_hashes(source: &mut Snapshot, files: &[String]) -> BTreeMap<String, String> {
    let rust = files.iter().filter(|f| f.ends_with(".rs"));
    let read = rust.filter_map(|f| source.read(f).map(|bytes| (f.clone(), sha256_hex(&bytes))));
    read.collect()
}

/// The scope labels and all the files below the roots.
fn list(
    source: &mut Snapshot,
    roots: &[String],
    builder: &mut Builder,
) -> (Vec<String>, Vec<String>) {
    let mut scope = Vec::new();
    let mut files = Vec::new();
    for root in roots {
        let root = root.trim_end_matches('/');
        if source.is_dir(root) {
            scope.push(format!("{root}/**"));
            files.extend(list_files(source, root));
        } else {
            scope.push(root.to_owned());
            builder.gap(&format!("Scan root is not a directory: {root}"), None, "");
        }
    }
    files.sort();
    files.dedup();
    (scope, files)
}

// The files of crates that are no workspace member (#1989, AD-1097). The core runs `cargo metadata` and gives the
// answer in `ARCHKEEL_WORKSPACE_MEMBERS`; this worker starts no process (AD-316).
/// The answer of the core.
enum Answer {
    /// The environment variable is not set: a test of the worker, or an older core.
    Absent,
    Unavailable(String),
    Listed {
        roots: Vec<String>,
        members: BTreeSet<String>,
        names: Vec<String>,
        held: BTreeSet<String>,
    },
}

fn answer() -> Answer {
    let Some(text) = std::env::var_os(MEMBERS_ENV) else {
        return Answer::Absent;
    };
    let value: Option<Value> = text.to_str().and_then(|t| serde_json::from_str(t).ok());
    let Some(value) = value else {
        return Answer::Unavailable("the answer of the core is not readable".to_owned());
    };
    if let Some(why) = value.get("unavailable").and_then(Value::as_str) {
        return Answer::Unavailable(why.to_owned());
    }
    let list = |key: &str| -> Option<Vec<String>> {
        let all = value.get(key)?.as_array()?;
        all.iter().map(|v| v.as_str().map(str::to_owned)).collect()
    };
    match (list("roots"), list("members")) {
        (Some(roots), Some(members)) => Answer::Listed {
            roots,
            members: members.into_iter().collect(),
            names: list("names").unwrap_or_default(),
            held: list("held").unwrap_or_default().into_iter().collect(),
        },
        _ => Answer::Unavailable("the answer of the core is not readable".to_owned()),
    }
}

/// What the scan does not read: the package names of the crates that it dropped, and the member crates (by directory)
/// that Cargo says have a path dependency on a crate that is no member.
struct Foreign {
    names: BTreeSet<String>,
    held: BTreeSet<String>,
}

impl Foreign {
    fn none() -> Foreign {
        Foreign {
            names: BTreeSet::new(),
            held: BTreeSet::new(),
        }
    }
}

/// A member that depends on a foreign crate may reach other members through it: the files of the foreign crate are
/// not read, so the edges of that member are unknown (#1989).
fn hold_foreign_edges(
    workspace: &Workspace,
    modules: &[Module],
    foreign: &Foreign,
    builder: &mut Builder,
) {
    for (index, krate) in workspace.crates.iter().enumerate() {
        // `declared` keeps each entry: `dependencies` joins two keys that differ only by `-` and `_`.
        let named = krate
            .manifest
            .declared
            .iter()
            .map(|entry| ident(&entry.package))
            .find(|package| foreign.names.contains(package));
        // Cargo names a path dependency that is no member, also one outside every scan root.
        let outside = foreign
            .held
            .contains(&krate.dir)
            .then(|| "a path dependency".to_owned());
        let (Some(package), Some(root)) = (
            named.or(outside),
            krate.primary.as_ref().or(krate.roots.first()),
        ) else {
            continue;
        };
        let sources = modules
            .iter()
            .filter(|m| m.crate_index == index)
            .map(|m| m.module.as_str())
            .collect::<Vec<_>>();
        let reason = format!("The crate {} depends on {package}, a crate that is no workspace member: the edges that pass through it are not read", krate.ident);
        builder.edges_gap((&reason, &root.module), &sources, None);
    }
}

/// `files` without the files below a crate that is no workspace member. A crate whose membership is not decided
/// stays in the list and adds a gap.
fn workspace_files(
    files: Vec<String>,
    source: &mut Snapshot,
    builder: &mut Builder,
) -> (Vec<String>, Foreign) {
    let (roots, members, listed_names, held) = match answer() {
        Answer::Absent => return (files, Foreign::none()),
        Answer::Unavailable(why) => {
            // Without `cargo metadata` the manifests prove a membership only for the plain layouts.
            let dirs = package_dirs(&files, source);
            let unproven =
                unproven_members(source, &dirs.iter().map(String::as_str).collect::<Vec<_>>());
            if !unproven.is_empty() {
                let reason = format!("The Cargo workspace members are unavailable: {why}. The manifests do not prove that {} is a member: every crate below the scan roots is read as workspace code.", unproven.join(", "));
                builder.gap(&reason, None, "");
            }
            return (files, Foreign::none());
        }
        Answer::Listed {
            roots,
            members,
            names,
            held,
        } => (roots, members, names, held),
    };
    let mut foreign: BTreeMap<&str, String> = BTreeMap::new();
    // The member names come from Cargo: a path that the scan lists differently (a symlinked scan root) cannot hide one.
    let mut member_names: BTreeSet<String> = listed_names.iter().map(|n| ident(n)).collect();
    let mut kept: BTreeSet<&str> = BTreeSet::new();
    for file in files
        .iter()
        .filter(|f| *f == "Cargo.toml" || f.ends_with("/Cargo.toml"))
    {
        let Some(name) = package_name(source, file) else {
            continue;
        };
        let dir = dirname(file);
        if name.is_empty() {
            // The manifest cannot be read: `discover` names the reason, and the crate stays in the scan.
            kept.insert(dir);
            continue;
        }
        if !roots.iter().any(|root| within(root, dir)) {
            let reason = format!("Whether the crate {file} is a workspace member is not decided: its scan root has no Cargo.toml");
            builder.gap(&reason, None, "");
            kept.insert(dir);
        } else if members.contains(dir) {
            member_names.insert(ident(&name));
            kept.insert(dir);
        } else {
            foreign.insert(dir, name);
        }
    }
    // A dependency is read by its normalized package name, so a foreign crate with the name of a member would be
    // read as the member.
    for (dir, name) in foreign
        .iter()
        .filter(|(_, n)| member_names.contains(&ident(n)))
    {
        let reason = format!("The crate {dir} is no workspace member and has the package name {name} of a member: a dependency on that name is read as the member");
        builder.gap(&reason, None, "");
    }
    // A file belongs to its nearest crate: a member below a foreign crate stays. A foreign crate inside the directory
    // of a member loses only its manifest: Cargo can still build the member targets there, and the files that no module
    // tree claims add their own gap.
    let nested: BTreeSet<&str> = foreign
        .keys()
        .copied()
        .filter(|dir| inside_member(dir, &kept))
        .collect();
    let names: BTreeSet<String> = foreign.values().map(|name| ident(name)).collect();
    let kept_files = files
        .iter()
        .filter(|file| {
            let mut dir = dirname(file);
            loop {
                if foreign.contains_key(dir) {
                    return nested.contains(dir) && join(dir, "Cargo.toml") != **file;
                }
                if kept.contains(dir) || dir.is_empty() {
                    return true;
                }
                dir = dirname(dir);
            }
        })
        .cloned()
        .collect();
    (kept_files, Foreign { names, held })
}

/// Whether a directory above `dir` is a member crate.
fn inside_member(dir: &str, kept: &BTreeSet<&str>) -> bool {
    let mut up = dir;
    while !up.is_empty() {
        up = dirname(up);
        if kept.contains(up) {
            return true;
        }
    }
    false
}

/// The package name of a manifest. `None` for a virtual workspace manifest, which is no crate. A manifest that
/// cannot be read counts as a crate with no name: the discovery of the crates says why it cannot be read.
fn package_name(source: &mut Snapshot, file: &str) -> Option<String> {
    let table = read_text(source, file)
        .ok()
        .and_then(|text| toml::parse(&text).ok());
    let Some(table) = table else {
        return Some(String::new());
    };
    let package: &toml::Value = table.get("package")?;
    let fields: &toml::Table = package.table()?;
    let name: &toml::Value = fields.get("name")?;
    Some(name.text()?.to_owned())
}

/// The directory of each package manifest in `files`.
fn package_dirs(files: &[String], source: &mut Snapshot) -> Vec<String> {
    let manifests = files
        .iter()
        .filter(|f| *f == "Cargo.toml" || f.ends_with("/Cargo.toml"));
    manifests
        .filter(|file| package_name(source, file).is_some())
        .map(|file| dirname(file).to_owned())
        .collect()
}

#[cfg(test)]
#[path = "collect_tests.rs"]
pub(crate) mod tests;

#[cfg(test)]
#[path = "collect_reach_tests.rs"]
mod reach_tests;
