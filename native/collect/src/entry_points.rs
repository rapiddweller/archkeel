// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The entry points that the manifests of a scan declare and the file layout shows (#2040,
//! AD-1140). The core reads them for the Explorer only. A manifest that cannot be read is named in
//! `unread`; the list is then unknown, never empty. A language without a reader has no list.

use std::collections::BTreeSet;

use archkeel_facts::data::entry_points::{
    EntryBasis, EntryEvidence, EntryKind, EntryPoint, EntryPoints,
};
use archkeel_facts::envelope::Profile;
use archkeel_python_collector::{Script, ScriptTable};
use serde_json::Value;
use toml::Table;

use crate::repository::Root;

/// The largest manifest that the scan reads.
const MAX_MANIFEST_BYTES: u64 = 1 << 20;
/// The most manifests that the scan reads in one tree.
const MAX_MANIFESTS: usize = 500;

/// The entry points of the scan, or `None` when no reader exists for its language.
/// `files` holds the module and the path of each scanned file.
pub(crate) fn read(root: &Root, profile: Profile, files: &[(&str, &str)]) -> Option<EntryPoints> {
    let mut found = EntryPoints::default();
    match profile {
        Profile::Python => python(root, files, &mut found),
        Profile::Rust => each_manifest(root, files, "Cargo.toml", &mut found, cargo),
        Profile::TypeScript => each_manifest(root, files, "package.json", &mut found, package),
        Profile::Dart => return None,
    }
    Some(found)
}

fn declared(
    kind: EntryKind,
    name: &str,
    target: Option<&str>,
    path: &str,
    key: String,
) -> EntryPoint {
    EntryPoint {
        kind,
        basis: EntryBasis::Declared,
        name: name.to_owned(),
        target: target.map(str::to_owned),
        evidence: EntryEvidence {
            path: path.to_owned(),
            key: Some(key),
        },
    }
}

fn observed(kind: EntryKind, name: &str, path: &str) -> EntryPoint {
    EntryPoint {
        kind,
        basis: EntryBasis::Observed,
        name: name.to_owned(),
        target: Some(path.to_owned()),
        evidence: EntryEvidence {
            path: path.to_owned(),
            key: None,
        },
    }
}

fn script_entry(script: &Script) -> EntryPoint {
    let (kind, table) = match script.table {
        ScriptTable::Console => (EntryKind::PythonScript, "project.scripts"),
        ScriptTable::Gui => (EntryKind::PythonGuiScript, "project.gui-scripts"),
    };
    let key = format!("{table}.{}", script.name);
    declared(
        kind,
        &script.name,
        Some(&script.target),
        "pyproject.toml",
        key,
    )
}

fn python(root: &Root, files: &[(&str, &str)], found: &mut EntryPoints) {
    match root.path().to_str() {
        Some(text) => match archkeel_python_collector::scripts(text) {
            Ok(scripts) => found.entries.extend(scripts.iter().map(script_entry)),
            Err(why) => found.unread.push(format!("pyproject.toml: {why}")),
        },
        None => found
            .unread
            .push("pyproject.toml: the root is not UTF-8".to_owned()),
    }
    for (module, path) in files {
        if path.rsplit('/').next() == Some("__main__.py") {
            found
                .entries
                .push(observed(EntryKind::PythonMainModule, module, path));
        }
    }
}

/// Run `read` on the manifest `name` of each directory above a scanned file, the root included.
fn each_manifest(
    root: &Root,
    files: &[(&str, &str)],
    name: &str,
    found: &mut EntryPoints,
    read: fn(&str, &str, &[(&str, &str)], &mut EntryPoints),
) {
    let mut dirs = BTreeSet::from([String::new()]);
    for (_, file) in files {
        let mut dir = *file;
        while let Some((above, _)) = dir.rsplit_once('/') {
            dirs.insert(above.to_owned());
            dir = above;
        }
    }
    let mut manifests = 0;
    for dir in dirs {
        let path = if dir.is_empty() {
            name.to_owned()
        } else {
            format!("{dir}/{name}")
        };
        if !root.is_file(&path) {
            continue;
        }
        manifests += 1;
        if manifests > MAX_MANIFESTS {
            found
                .unread
                .push(format!("{path}: more than {MAX_MANIFESTS} manifests"));
            break;
        }
        match root.read(&path, MAX_MANIFEST_BYTES) {
            Ok(Some((_, bytes))) => match String::from_utf8(bytes) {
                Ok(text) => read(&path, &text, files, found),
                Err(_) => found.unread.push(format!("{path}: not UTF-8")),
            },
            Ok(None) => found.unread.push(format!("{path}: cannot be read")),
            Err(_) => found
                .unread
                .push(format!("{path}: more than {MAX_MANIFEST_BYTES} bytes")),
        }
    }
}

/// `[[bin]]` targets, and the binary files below `src` that Cargo finds itself.
fn cargo(path: &str, text: &str, files: &[(&str, &str)], found: &mut EntryPoints) {
    let Ok(table) = text.parse::<Table>() else {
        found.unread.push(format!("{path}: cannot be parsed"));
        return;
    };
    let dir = path.trim_end_matches("Cargo.toml");
    let package = table.get("package").and_then(|value| value.as_table());
    let mut named = BTreeSet::new();
    let mut paths = BTreeSet::new();
    for entry in table
        .get("bin")
        .and_then(|value| value.as_array())
        .into_iter()
        .flatten()
    {
        let bin = entry.as_table();
        let Some(name) = bin.and_then(|bin| bin.get("name")).and_then(|v| v.as_str()) else {
            found
                .unread
                .push(format!("{path}: a [[bin]] entry has no name"));
            continue;
        };
        let target = bin
            .and_then(|bin| bin.get("path"))
            .and_then(|value| value.as_str())
            .map(|declared| format!("{dir}{}", declared.trim_start_matches("./")));
        named.insert(name.to_owned());
        paths.extend(target.clone());
        found.entries.push(declared(
            EntryKind::CargoBin,
            name,
            target.as_deref(),
            path,
            format!("bin.name={name}"),
        ));
    }
    let Some(package_name) = package
        .and_then(|package| package.get("name"))
        .and_then(|value| value.as_str())
    else {
        return;
    };
    if !discovers_bins(path, package, !named.is_empty(), found) {
        return;
    }
    for (_, file) in files {
        let Some(below) = file
            .strip_prefix(dir)
            .and_then(|rest| rest.strip_prefix("src/"))
        else {
            continue;
        };
        let name = match below.split('/').collect::<Vec<_>>().as_slice() {
            ["main.rs"] => package_name,
            ["bin", leaf] => leaf.strip_suffix(".rs").unwrap_or_default(),
            ["bin", leaf, "main.rs"] => leaf,
            _ => continue,
        };
        // Cargo skips a dot-prefixed file or directory in automatic discovery.
        let hidden = name.starts_with('.');
        if !name.is_empty() && !hidden && !paths.contains(*file) && named.insert(name.to_owned()) {
            found
                .entries
                .push(observed(EntryKind::CargoBin, name, file));
        }
    }
}

/// Whether Cargo finds the default binary files itself. `autobins` decides when it is set.
/// Else an edition 2015 package turns it off once it declares a `[[bin]]`. An edition that the
/// manifest inherits from the workspace is not read, so that case is unknown.
fn discovers_bins(
    path: &str,
    package: Option<&Table>,
    declares_bins: bool,
    found: &mut EntryPoints,
) -> bool {
    if let Some(set) = package.and_then(|package| package.get("autobins")) {
        return set.as_bool().unwrap_or(false);
    }
    let edition = package.and_then(|package| package.get("edition"));
    match edition.map(|edition| edition.as_str()) {
        None => !declares_bins,
        Some(Some(year)) => year != "2015" || !declares_bins,
        Some(None) if !declares_bins => true,
        Some(None) => {
            found.unread.push(format!(
                "{path}: the edition is not a string, so binary discovery is unknown"
            ));
            false
        }
    }
}

/// The command that npm installs for a name: the part after the last `/`, so `@acme/tool` is `tool`.
fn command(name: &str) -> &str {
    name.rsplit('/').next().unwrap_or(name)
}

/// The `bin` and `main` keys of a `package.json`.
fn package(path: &str, text: &str, _files: &[(&str, &str)], found: &mut EntryPoints) {
    let Ok(Value::Object(manifest)) = serde_json::from_str::<Value>(text) else {
        found.unread.push(format!("{path}: cannot be parsed"));
        return;
    };
    let package = manifest.get("name").and_then(Value::as_str);
    match manifest.get("bin") {
        None => {}
        Some(Value::String(file)) => {
            let name = command(package.unwrap_or(file));
            found.entries.push(declared(
                EntryKind::PackageBin,
                name,
                Some(file),
                path,
                "bin".to_owned(),
            ));
        }
        Some(Value::Object(bins)) => {
            for (name, file) in bins {
                match file.as_str() {
                    Some(file) => found.entries.push(declared(
                        EntryKind::PackageBin,
                        command(name),
                        Some(file),
                        path,
                        format!("bin.{name}"),
                    )),
                    None => found
                        .unread
                        .push(format!("{path}: bin.{name} is not a string")),
                }
            }
        }
        Some(_) => found
            .unread
            .push(format!("{path}: bin is not a string or an object")),
    }
    match manifest.get("main") {
        None => {}
        Some(Value::String(file)) => found.entries.push(declared(
            EntryKind::PackageMain,
            package.unwrap_or(file),
            Some(file),
            path,
            "main".to_owned(),
        )),
        Some(_) => found.unread.push(format!("{path}: main is not a string")),
    }
}

#[cfg(test)]
#[path = "entry_points_tests.rs"]
mod tests;
