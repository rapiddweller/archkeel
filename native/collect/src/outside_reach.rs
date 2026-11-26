// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members that reach another member through code that the scan does not read (#2028, #2060, #2105, AD-1097).
//!
//! The scan reads the workspace members only. A member can still run a crate that lies elsewhere, and that crate can
//! run a member. The evidence is Cargo's, not a text search of source:
//!
//! 1. The resolve graph of `cargo metadata`, run from the real workspace root with its `.cargo/config.toml`. A patch (in
//!    the manifest, the config or a workspace above the scan roots), a git source or a path dependency is an edge of the
//!    graph. A chain from a member through a crate that is no member back to a member holds the first member.
//! 2. A local crate outside the members on the way can still read a member through `include!`, `#[path]`, a symlink, a
//!    build script or a procedural macro. A build script or a procedural macro holds always (dep-info lists no
//!    `std::fs` read). For the others the dep-info that `rustc` writes lists each source file that it read: with the
//!    operator's permission to build (AD-1130) the core checks that list; without it the crate is not proven and holds.
//! 3. When Cargo cannot resolve the workspace, only the direct facts of `cargo metadata --no-deps` are left, and each
//!    path, patched or git dependency outside the members holds.

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// `cargo check` of package ids into a target directory: its JSON output.
pub(crate) type Check = dyn Fn(&Path, &[String], &Path) -> Option<String>;

/// The Cargo runs that the analysis needs: the core starts them with a sealed environment.
pub(crate) struct Runs<'a> {
    /// `cargo metadata` with the resolve graph, run from the workspace root.
    pub(crate) resolve: &'a dyn Fn(&Path) -> Option<Value>,
    /// `cargo check --message-format=json` of the given package ids into a target directory.
    pub(crate) check: &'a Check,
    /// The operator allowed the build (AD-1130).
    pub(crate) build: bool,
}

/// The canonical directory of each member (a key of `dirs`) and the package name of each member.
struct Cx<'a> {
    dirs: &'a BTreeMap<String, BTreeSet<String>>,
    names: &'a BTreeSet<String>,
    runs: &'a Runs<'a>,
}

/// The canonical directory of each member whose edges pass through code that the scan does not read.
pub(crate) fn dependents(
    meta: &Value,
    ids: &BTreeSet<&str>,
    dirs: &BTreeMap<String, BTreeSet<String>>,
    names: &BTreeSet<String>,
    runs: &Runs,
) -> BTreeSet<String> {
    let cx = Cx { dirs, names, runs };
    let root = meta.get("workspace_root").and_then(Value::as_str);
    let resolved = root.and_then(|r| (runs.resolve)(Path::new(r)));
    match (resolved, root) {
        (Some(full), Some(root)) => by_graph(&full, Path::new(root), &cx),
        _ => by_direct_facts(meta, ids, &cx),
    }
}

fn real_dir(path: &str) -> Option<String> {
    let canonical = std::fs::canonicalize(path).ok()?;
    Some(canonical.to_string_lossy().replace('\\', "/"))
}

fn text<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(Value::as_str)
}

fn array<'a>(value: &'a Value, key: &str) -> impl Iterator<Item = &'a Value> {
    value
        .get(key)
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
}

/// One package of the resolve graph.
struct Pkg {
    dir: Option<String>,
    /// A path package: its source is no registry and no git repository.
    local: bool,
    /// A procedural macro or a build script: it runs code that no source list shows.
    runs_code: bool,
    /// A git package that has the name of a member: it can be a copy of the member.
    git_copy: bool,
    /// The dependencies as declared: each name, and whether it names a path.
    declared: Vec<(String, bool)>,
}

fn packages(full: &Value, names: &BTreeSet<String>) -> BTreeMap<String, Pkg> {
    let mut found = BTreeMap::new();
    for package in array(full, "packages") {
        let Some(id) = text(package, "id") else {
            continue;
        };
        let dir =
            text(package, "manifest_path").and_then(|m| real_dir(Path::new(m).parent()?.to_str()?));
        let kinds = array(package, "targets")
            .flat_map(|t| array(t, "kind"))
            .filter_map(Value::as_str);
        let runs_code = kinds
            .into_iter()
            .any(|k| k == "proc-macro" || k == "custom-build");
        let declared = array(package, "dependencies")
            .filter_map(|d| Some((text(d, "name")?.to_owned(), d.get("path").is_some())))
            .collect();
        let source = text(package, "source");
        let named = text(package, "name").is_some_and(|n| names.contains(n));
        let git_copy = named && source.is_some_and(|s| s.starts_with("git+"));
        let local = source.is_none();
        let pkg = Pkg {
            dir,
            local,
            runs_code,
            git_copy,
            declared,
        };
        found.insert(id.to_owned(), pkg);
    }
    found
}

fn edges(full: &Value) -> BTreeMap<&str, Vec<&str>> {
    let nodes = full.pointer("/resolve/nodes").and_then(Value::as_array);
    let mut found = BTreeMap::new();
    for node in nodes.into_iter().flatten() {
        let deps = array(node, "deps").filter_map(|d| text(d, "pkg")).collect();
        found.insert(text(node, "id").unwrap_or_default(), deps);
    }
    found
}

/// The graph analysis (point 1 and 2 above).
fn by_graph(full: &Value, root: &Path, cx: &Cx) -> BTreeSet<String> {
    let pkgs = packages(full, cx.names);
    let graph = edges(full);
    // A workspace member that no scan root holds is code outside the scan: it is no member here.
    let scanned = |id: &&str| {
        let dir = pkgs.get(*id).and_then(|p| p.dir.as_ref());
        dir.is_some_and(|d| cx.dirs.contains_key(d))
    };
    let members: BTreeSet<&str> = array(full, "workspace_members")
        .filter_map(Value::as_str)
        .filter(scanned)
        .collect();
    let mut held = BTreeSet::new();
    let mut outside: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
    for &member in &members {
        let Some(dir) = pkgs.get(member).and_then(|p| p.dir.clone()) else {
            continue;
        };
        let (route, local) = walk(member, &members, &graph, &pkgs);
        // A dependency that names a member but is no path (a patch) is an edge that the scan does not read.
        let patched = pkgs[member]
            .declared
            .iter()
            .any(|(name, path)| !path && cx.names.contains(name));
        if route || patched {
            held.insert(dir.clone());
        }
        outside.insert(member, local);
        // The packages of `local` are decided below, together.
        let _ = dir;
    }
    let local: BTreeSet<&str> = outside.values().flatten().copied().collect();
    let proven = proven_harmless(&local, &pkgs, root, cx);
    for (&member, needs) in &outside {
        let unproven = needs.iter().any(|id| !proven.contains(id));
        if let (true, Some(dir)) = (unproven, pkgs.get(member).and_then(|p| p.dir.clone())) {
            held.insert(dir);
        }
    }
    held
}

/// Walk the graph from `member` through the packages that are no member. `route`: a member is reached through one.
/// The second value holds the local packages outside the members that the walk passes.
fn walk<'a>(
    member: &'a str,
    members: &BTreeSet<&str>,
    graph: &BTreeMap<&'a str, Vec<&'a str>>,
    pkgs: &'a BTreeMap<String, Pkg>,
) -> (bool, BTreeSet<&'a str>) {
    let (mut route, mut local) = (false, BTreeSet::new());
    let mut seen = BTreeSet::from([member]);
    let mut stack: Vec<(&str, bool)> = graph
        .get(member)
        .into_iter()
        .flatten()
        .map(|d| (*d, false))
        .collect();
    while let Some((id, through)) = stack.pop() {
        if members.contains(id) {
            route |= through;
            continue;
        }
        if !seen.insert(id) {
            continue;
        }
        if pkgs.get(id).is_some_and(|p| p.local) {
            local.insert(id);
        }
        // A git package with the name of a member can be a copy of it: the scan reads the member, not the copy.
        route |= pkgs.get(id).is_some_and(|p| p.git_copy);
        stack.extend(graph.get(id).into_iter().flatten().map(|d| (*d, true)));
    }
    (route, local)
}

/// The local packages outside the members that are proven to read no member: no build script, no procedural macro, and
/// with the permission to build, a dep-info that lists only files of the package itself.
fn proven_harmless<'a>(
    local: &BTreeSet<&'a str>,
    pkgs: &BTreeMap<String, Pkg>,
    root: &Path,
    cx: &Cx,
) -> BTreeSet<&'a str> {
    let plain: Vec<&str> = local
        .iter()
        .copied()
        .filter(|id| pkgs.get(*id).is_some_and(|p| !p.runs_code))
        .collect();
    if !cx.runs.build || plain.is_empty() {
        return BTreeSet::new();
    }
    let target = std::env::temp_dir().join(format!("archkeel-outside-{}", std::process::id()));
    let specs: Vec<String> = plain.iter().map(|id| (*id).to_owned()).collect();
    let output = (cx.runs.check)(root, &specs, &target);
    let proven = output
        .map(|out| {
            plain
                .iter()
                .copied()
                .filter(|id| reads_only_itself(id, &out, pkgs, root, cx))
                .collect()
        })
        .unwrap_or_default();
    let _ = std::fs::remove_dir_all(&target);
    proven
}

/// Whether the dep-info of the package in the `cargo check` output lists only files of the package.
fn reads_only_itself(
    id: &str,
    output: &str,
    pkgs: &BTreeMap<String, Pkg>,
    root: &Path,
    cx: &Cx,
) -> bool {
    let Some(own) = pkgs.get(id).and_then(|p| p.dir.as_deref()) else {
        return false;
    };
    let inside = |file: &str, dir: &str| file == dir || file.starts_with(&format!("{dir}/"));
    let mut seen = false;
    for line in output
        .lines()
        .filter_map(|l| serde_json::from_str::<Value>(l).ok())
    {
        if text(&line, "reason") != Some("compiler-artifact")
            || text(&line, "package_id") != Some(id)
        {
            continue;
        }
        for file in dep_info(&line, root) {
            seen = true;
            let owned = real_dir(file.to_str().unwrap_or_default())
                .is_some_and(|f| inside(&f, own) && !cx.dirs.keys().any(|m| inside(&f, m)));
            if !owned {
                return false;
            }
        }
    }
    seen
}

/// The files that the dep-info of one compiler artifact lists, as paths from the workspace root.
fn dep_info(artifact: &Value, root: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    for name in array(artifact, "filenames").filter_map(Value::as_str) {
        let Some(stem) = Path::new(name).file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        let info = Path::new(name).with_file_name(format!("{}.d", stem.trim_start_matches("lib")));
        let Ok(body) = std::fs::read_to_string(info) else {
            return vec![PathBuf::from("\0unreadable")];
        };
        files.extend(listed_files(&body).map(|f| root.join(f)));
    }
    files
}

/// The files that a rustc dep-info lists: each token of a line that is no comment, minus the outputs.
fn listed_files(body: &str) -> impl Iterator<Item = String> + '_ {
    let lines = body.lines().filter(|l| !l.starts_with('#'));
    let tokens = lines.flat_map(|l| {
        l.replace("\\ ", "\u{1}")
            .split_whitespace()
            .map(str::to_owned)
            .collect::<Vec<_>>()
    });
    let tokens = tokens.map(|t| t.replace('\u{1}', " ").trim_end_matches(':').to_owned());
    tokens.filter(|t| {
        !t.is_empty()
            && ![".rmeta", ".rlib", ".d", ".so", ".dylib"]
                .iter()
                .any(|e| t.ends_with(e))
    })
}

/// The direct facts of `cargo metadata --no-deps` (point 3): each dependency that leads outside the members holds the
/// member that declares it. A patch cannot be ruled out without the resolve graph, so a registry or git dependency
/// whose name occurs in a manifest or config that has a patch holds as well.
fn by_direct_facts(meta: &Value, ids: &BTreeSet<&str>, cx: &Cx) -> BTreeSet<String> {
    let patched = patch_text(meta);
    let mut found = BTreeSet::new();
    for package in array(meta, "packages") {
        let id = text(package, "id").unwrap_or_default();
        let dir =
            text(package, "manifest_path").and_then(|m| real_dir(Path::new(m).parent()?.to_str()?));
        let (true, Some(dir)) = (ids.contains(id), dir) else {
            continue;
        };
        if !cx.dirs.contains_key(&dir) {
            continue;
        }
        if array(package, "dependencies").any(|d| leads_outside(d, patched.as_deref(), cx)) {
            found.insert(dir);
        }
    }
    found
}

fn leads_outside(dependency: &Value, patched: Option<&str>, cx: &Cx) -> bool {
    let name = text(dependency, "name");
    if let Some(path) = text(dependency, "path") {
        return real_dir(path).is_none_or(|dir| !cx.dirs.contains_key(&dir));
    }
    // A backslash can write a name in an escape, so the text cannot rule a patch out.
    let named = |t: &str| t.contains('\\') || name.is_some_and(|n| t.contains(n));
    let git_member = text(dependency, "source").is_some_and(|s| s.starts_with("git+"))
        && name.is_some_and(|n| cx.names.contains(n));
    git_member || (text(dependency, "source").is_some() && patched.is_some_and(named))
}

/// The text of the manifests and configs that can hold a `[patch]` or `[replace]`: the workspace manifest and each
/// `.cargo/config(.toml)` from the workspace root upwards. `None` when none of them can.
fn patch_text(meta: &Value) -> Option<String> {
    let root = Path::new(text(meta, "workspace_root")?);
    let mut files = vec![root.join("Cargo.toml")];
    for dir in root.ancestors() {
        files.extend([dir.join(".cargo/config.toml"), dir.join(".cargo/config")]);
    }
    let all: String = files
        .iter()
        .filter_map(|f| std::fs::read_to_string(f).ok())
        .collect();
    // A backslash can write the table name in an escape (`patch`), so such a text is kept too.
    ["patch", "replace", "\\"]
        .iter()
        .any(|k| all.contains(k))
        .then_some(all)
}
