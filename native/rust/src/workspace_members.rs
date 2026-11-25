// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The files of crates that are no workspace member (#1989, AD-1047).
//!
//! A crate below a scan root that `cargo metadata` does not name as a member is foreign code: it is no module of
//! the workspace, and its files are not scanned. The core runs `cargo metadata` and gives the answer in
//! `ARCHKEEL_WORKSPACE_MEMBERS`; this worker starts no process (AD-316). Without an answer the scan reads every
//! crate as before and says so in a gap: it never decides membership by the directory tree in silence.

use crate::builder::Builder;
use crate::crates::unproven_members;
use crate::manifest::ident;
use crate::source::read_text;
use crate::toml;
use archkeel_facts::type_reach::MEMBERS_ENV;
use archkeel_snapshot::paths::{dirname, within};
use archkeel_snapshot::Snapshot;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

/// The answer of the core.
enum Answer {
    /// The environment variable is not set: a test of the worker, or an older core.
    Absent,
    Unavailable(String),
    Listed {
        roots: Vec<String>,
        members: BTreeSet<String>,
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
        },
        _ => Answer::Unavailable("the answer of the core is not readable".to_owned()),
    }
}

/// `files` without the files below a crate that is no workspace member. A crate whose membership is not decided
/// stays in the list and adds a gap.
pub(crate) fn workspace_files(
    files: Vec<String>,
    source: &mut Snapshot,
    builder: &mut Builder,
) -> Vec<String> {
    let (roots, members) = match answer() {
        Answer::Absent => return files,
        Answer::Unavailable(why) => {
            // Without `cargo metadata` the manifests prove a membership only for the plain layouts.
            let dirs = package_dirs(&files, source);
            let unproven =
                unproven_members(source, &dirs.iter().map(String::as_str).collect::<Vec<_>>());
            if !unproven.is_empty() {
                let reason = format!("The Cargo workspace members are unavailable: {why}. The manifests do not prove that {} is a member: every crate below the scan roots is read as workspace code.", unproven.join(", "));
                builder.gap(&reason, None, "");
            }
            return files;
        }
        Answer::Listed { roots, members } => (roots, members),
    };
    let (mut foreign, mut member_names): (BTreeMap<&str, String>, BTreeSet<String>) =
        Default::default();
    let mut kept: BTreeSet<&str> = BTreeSet::new();
    for file in files
        .iter()
        .filter(|f| *f == "Cargo.toml" || f.ends_with("/Cargo.toml"))
    {
        let Some(name) = package_name(source, file) else {
            continue;
        };
        let dir = dirname(file);
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
    // A file belongs to its nearest crate: a member below a foreign crate stays.
    files
        .iter()
        .filter(|file| {
            let mut dir = dirname(file);
            loop {
                if foreign.contains_key(dir) {
                    return false;
                }
                if kept.contains(dir) || dir.is_empty() {
                    return true;
                }
                dir = dirname(dir);
            }
        })
        .cloned()
        .collect()
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
    let package = table.get("package")?;
    Some(package.table()?.get("name")?.text()?.to_owned())
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
