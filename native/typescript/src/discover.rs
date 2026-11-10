// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `config._discover`: the files that `files` and `include` name, minus `exclude`.

use std::collections::BTreeSet;

use crate::glob::{Pattern, Usage};
use crate::layer::Layer;
use crate::source_input::{classify_file, shadowed, SourceKind, Suffix};
use archkeel_snapshot::paths::{basename, dirname, is_outside, join, within};
use archkeel_snapshot::Snapshot;

/// The listed files first, then the found files in sorted order, as the compiler lists them.
pub fn discover(
    snapshot: &mut Snapshot,
    layer: &Layer,
    own: &str,
    problems: &mut Vec<String>,
) -> Vec<String> {
    let listed = layer.specs.get("files");
    let include: Vec<String> = match layer.specs.get("include") {
        None if listed.is_none() => vec![join(own, "**/*")],
        None => Vec::new(),
        Some(specs) => specs.clone(),
    };
    // An exclusion outside the snapshot excludes nothing in it.
    let exclude: Vec<String> = match layer.specs.get("exclude") {
        None => layer.outputs.values().flatten().cloned().collect(),
        Some(specs) => specs.clone(),
    };
    for spec in &include {
        if spec.trim_end_matches('/').ends_with("**") {
            problems.push(format!(
                "Compiler option 5010: '{spec}' cannot end in a recursive wildcard."
            ));
        }
    }
    // A pattern that climbs out of the snapshot can select nothing the collector may read.
    let inside: Vec<&String> = include.iter().filter(|spec| !is_outside(spec)).collect();
    let compile = |specs: &[&String], usage| -> Vec<Pattern> {
        specs
            .iter()
            .filter_map(|spec| Pattern::new(spec, usage))
            .collect()
    };
    let files = compile(&inside, Usage::Files);
    let directories = compile(&inside, Usage::Directories);
    let outside_free: Vec<&String> = exclude.iter().filter(|spec| !is_outside(spec)).collect();
    let excluded = compile(&outside_free, Usage::Exclude);
    let found = walk(
        snapshot,
        layer,
        own,
        &inside,
        &files,
        &directories,
        &excluded,
    );
    let literal: Vec<String> = listed.cloned().unwrap_or_default();
    let known: BTreeSet<&str> = literal.iter().chain(&found).map(String::as_str).collect();
    let mut result = literal.clone();
    result.extend(
        found
            .iter()
            .filter(|rel| !shadowed(rel, &|path| known.contains(path)))
            .cloned(),
    );
    result
}

// The config's own directory is walked first; a spec elsewhere adds its own start.
fn walk(
    snapshot: &mut Snapshot,
    layer: &Layer,
    own: &str,
    inside: &[&String],
    files: &[Pattern],
    directories: &[Pattern],
    excluded: &[Pattern],
) -> BTreeSet<String> {
    let mut starts = vec![join("/", own)];
    let mut bases: Vec<String> = inside.iter().map(|spec| base_path(spec)).collect();
    bases.sort();
    for start in bases {
        if !starts.iter().any(|known| within(known, &start)) {
            starts.push(start);
        }
    }
    let mut pending: Vec<(String, String)> = starts
        .into_iter()
        .map(|start| match start.trim_start_matches('/') {
            "" => (".".to_owned(), start.clone()),
            rel => (rel.to_owned(), start.clone()),
        })
        .collect();
    let mut found = BTreeSet::new();
    let mut seen = BTreeSet::new();
    let is_excluded = |path: &str| excluded.iter().any(|pattern| pattern.matches(path));
    while !files.is_empty() {
        let Some((rel, absolute)) = pending.pop() else {
            break;
        };
        if !snapshot.real(&rel).is_some_and(|real| seen.insert(real)) {
            continue;
        }
        let (names, children) = snapshot.entries(&rel);
        for name in names {
            let path = join(&absolute, &name);
            if files.iter().any(|pattern| pattern.matches(&path))
                && supported(&name, layer.allow_js())
                && !is_excluded(&path)
            {
                found.insert(join(&rel, &name));
            }
        }
        for name in children {
            let path = join(&absolute, &name);
            if directories.iter().any(|pattern| pattern.matches(&path)) && !is_excluded(&path) {
                pending.push((join(&rel, &name), path));
            }
        }
    }
    found
}

fn supported(name: &str, allow_js: bool) -> bool {
    match classify_file(name).and_then(Suffix::source_kind) {
        Some(SourceKind::TypeScript | SourceKind::Declaration) => true,
        Some(SourceKind::JavaScript) => allow_js,
        _ => false,
    }
}

/// `config._base_path`: the directory a walk starts from, before the first wildcard.
fn base_path(spec: &str) -> String {
    let path = if spec.starts_with('/') {
        spec.to_owned()
    } else {
        format!("/{spec}")
    };
    match path.find(['*', '?']) {
        None if !basename(&path).contains('.') => path,
        None => match dirname(&path) {
            "" => "/".to_owned(),
            directory => directory.to_owned(),
        },
        Some(wildcard) => match path[..wildcard].rfind('/') {
            Some(0) | None => "/".to_owned(),
            Some(slash) => path[..slash].to_owned(),
        },
    }
}
