// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Select and read the Dart sources of a request, as `snapshot.read_snapshot` of the Python Dart
//! collector does. Each read goes through `archkeel-snapshot`. No symbolic link is followed: a
//! link is a problem, and each problem becomes a gap of the reply.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::vocab::ExceptionName;
use archkeel_snapshot::paths::normpath;
use archkeel_snapshot::{Entry, RootCheck, Snapshot};

use crate::module::dart_module_name;
use crate::pubspec::{self, Pubspec, SdkState};

/// The files that can change the package of a URI. The import survey names each one that the
/// walk sees, because it resolves URIs from the root `pubspec.yaml` alone (AD-454).
pub(crate) const PACKAGE_FILES: [&str; 4] = [
    "pubspec.yaml",
    "pubspec_overrides.yaml",
    "package_config.json",
    ".packages",
];

/// One file or directory that the collector cannot read as a Dart source.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Problem {
    pub(crate) path: String,
    /// The `SnapshotProblemKind` of the Python collector, which the gap writes as its kind.
    pub(crate) kind: ExceptionName,
    pub(crate) message: String,
}

/// One selected Dart source.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Source {
    pub(crate) rel_path: String,
    pub(crate) module: String,
    pub(crate) content: Vec<u8>,
    /// The SHA-256 of `content`, which `Snapshot::read` computed.
    pub(crate) digest: String,
}

/// The sources, the package identity and the problems of one request.
#[derive(Debug)]
pub(crate) struct Discovery {
    /// The recognized test paths that the request leaves out.
    pub(crate) excluded: Vec<String>,
    /// Each package file of `PACKAGE_FILES` that the walk saw below a scan root (AD-454).
    pub(crate) package_files: Vec<String>,
    /// Sorted by path.
    pub(crate) sources: Vec<Source>,
    /// Empty when the package directory has no `pubspec.yaml`.
    pub(crate) package_name: String,
    /// The directory of the package of the scan below the snapshot root, empty for the root: the
    /// nearest directory at or above each scan root with a `pubspec.yaml` (#1539).
    pub(crate) package_dir: String,
    pub(crate) sdk: Option<String>,
    pub(crate) sdk_state: SdkState,
    /// The SHA-256 of `pubspec.yaml`, when it exists.
    pub(crate) pubspec_digest: Option<String>,
    pub(crate) problems: Vec<Problem>,
}

// `.dart_tool`, `pubcache` and `.pub-cache` hold generated and cached files, never project code.
const EXCLUDED: [&str; 3] = [".dart_tool", "pubcache", ".pub-cache"];
const NOT_REGULAR: &str = "input is outside snapshot or not a regular file";

struct Walk<'a> {
    snapshot: &'a mut Snapshot,
    seen: BTreeSet<String>,
    sources: Vec<Pending>,
    problems: Vec<Problem>,
    package_files: Vec<String>,
}

struct Pending {
    root: String,
    rel_path: String,
    content: Vec<u8>,
}

/// Read each selected `.dart` file once. An error is a failure of the whole collection, as a
/// `SnapshotError` of the Python collector is: a `pubspec.yaml` that is a link or has no name.
pub(crate) fn discover(
    snapshot: &mut Snapshot,
    namespace: &str,
    roots: &[String],
    exclude_tests: bool,
) -> Result<Discovery, String> {
    let mut walk = Walk {
        snapshot,
        seen: BTreeSet::new(),
        sources: Vec::new(),
        problems: Vec::new(),
        package_files: Vec::new(),
    };
    for root in roots {
        walk.root(root);
    }
    let package_dir = package_dir(walk.snapshot, roots);
    let (pubspec, pubspec_digest) = read_pubspec(walk.snapshot, &package_dir)?;
    let Walk {
        snapshot,
        sources: pending,
        mut problems,
        package_files,
        ..
    } = walk;
    let mut sources = Vec::new();
    let mut excluded = Vec::new();
    for source in pending {
        if exclude_tests
            && test_source(&source.rel_path, &source.root, &package_dir, &package_files)
        {
            excluded.push(source.rel_path);
            continue;
        }
        let relative = if source.root == "." {
            String::as_str(&source.rel_path)
        } else {
            source
                .rel_path
                .strip_prefix(&source.root)
                .and_then(|rest| rest.strip_prefix('/'))
                .unwrap_or(&source.rel_path)
        };
        let Some(short) = dart_module_name(relative) else {
            problems.push(problem(
                &source.rel_path,
                ExceptionName::DartModuleError,
                "path is not a Dart module identifier",
            ));
            continue;
        };
        sources.push(Source {
            rel_path: source.rel_path,
            module: format!("{namespace}.{short}"),
            content: source.content,
            digest: String::new(),
        });
    }
    if pubspec_digest.is_none() {
        problems.push(problem(
            "pubspec.yaml",
            ExceptionName::PubspecMissing,
            "no pubspec.yaml at the snapshot root; own-package imports are not resolved",
        ));
    }
    collisions(&sources, &mut problems);
    problems.extend(snapshot_problems(snapshot));
    sources.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
    excluded.sort();
    let digests: BTreeMap<String, String> = snapshot
        .inputs(|path, digest, _| (path.to_owned(), digest.to_owned()))
        .into_iter()
        .collect();
    for source in &mut sources {
        if let Some(digest) = digests.get(&source.rel_path) {
            source.digest.clone_from(digest);
        }
    }
    Ok(Discovery {
        excluded,
        sources,
        package_name: pubspec.name.unwrap_or_default(),
        package_dir,
        sdk: pubspec.sdk,
        sdk_state: pubspec.state,
        pubspec_digest,
        problems,
        package_files,
    })
}

/// The normalized scan roots without a repeat, in their first order, as `snapshot._roots`.
pub(crate) fn scan_roots(roots: &[String]) -> Vec<String> {
    let mut result: Vec<String> = Vec::new();
    for root in roots.iter().map(|root| normpath(root)) {
        if !result.contains(&root) {
            result.push(root);
        }
    }
    result
}

/// Each problem that `archkeel-snapshot` recorded, such as a name that is not UTF-8 or a
/// directory that cannot be read, as a `SnapshotError` at the path that the text names. Nothing
/// that the walk could not see stays silent.
fn snapshot_problems(snapshot: &mut Snapshot) -> Vec<Problem> {
    std::mem::take(&mut snapshot.problems)
        .into_iter()
        .map(|text| {
            let path = text
                .split_once(": ")
                .map_or(".", |(_, path)| path)
                .to_owned();
            Problem {
                path,
                kind: ExceptionName::SnapshotError,
                message: text,
            }
        })
        .collect()
}

fn problem(path: &str, kind: ExceptionName, message: &str) -> Problem {
    Problem {
        path: path.to_owned(),
        kind,
        message: message.to_owned(),
    }
}

impl Walk<'_> {
    fn root(&mut self, root: &str) {
        let (kind, message) = match self.snapshot.check_root(root) {
            RootCheck::Contained => return self.directory(root, root),
            RootCheck::Link => (ExceptionName::DartSourceLink, "source root is a symlink"),
            RootCheck::NotDirectory => (
                ExceptionName::SelectedRootError,
                "selected root is missing or not a directory",
            ),
            RootCheck::Escapes => (
                ExceptionName::ContainmentError,
                "source root escapes snapshot",
            ),
        };
        self.problems.push(problem(root, kind, message));
    }

    fn directory(&mut self, root: &str, directory: &str) {
        // A directory that cannot be read is a problem of the snapshot, which becomes a gap.
        let Some(entries) = self.snapshot.listing(directory) else {
            return;
        };
        let mut subdirectories = Vec::new();
        for (name, entry) in entries {
            let rel = child(directory, &name);
            if let Some(subdirectory) = self.entry(root, rel, &name, entry) {
                subdirectories.push(subdirectory);
            }
        }
        for subdirectory in subdirectories {
            self.directory(root, &subdirectory);
        }
    }

    /// Handle one entry of a directory; give the path of a subdirectory that the walk enters.
    fn entry(&mut self, root: &str, rel: String, name: &str, entry: Entry) -> Option<String> {
        match entry {
            // `os.walk` lists a link to a directory with the directories.
            Entry::Directory | Entry::Link { to_directory: true } => {
                match excluded_or_link(&rel, name, entry) {
                    Some(found) => self.problems.push(found),
                    None => return Some(rel),
                }
            }
            _ if name.ends_with(".dart") && self.seen.insert(rel.clone()) => {
                self.file(root, &rel, entry);
            }
            _ if PACKAGE_FILES.contains(&name) => self.package_files.push(rel),
            _ => {}
        }
        None
    }

    fn file(&mut self, root: &str, rel: &str, entry: Entry) {
        if matches!(entry, Entry::Link { .. }) {
            let found = problem(
                rel,
                ExceptionName::DartSourceLink,
                "source file is a symlink",
            );
            self.problems.push(found);
            return;
        }
        if entry == Entry::Other {
            self.problems
                .push(problem(rel, ExceptionName::SnapshotError, NOT_REGULAR));
            return;
        }
        // Any other refusal of the read is a problem of the snapshot, which becomes a gap.
        let Some(content) = self.snapshot.read_walked(rel) else {
            if self.snapshot.size_gap(rel).is_some() {
                let message = format!(
                    "source file is over the size limit of {} bytes",
                    archkeel_snapshot::MAX_FILE_BYTES
                );
                self.problems.push(Problem {
                    path: rel.to_owned(),
                    kind: ExceptionName::SnapshotError,
                    message,
                });
            }
            return;
        };
        self.sources.push(Pending {
            root: root.to_owned(),
            rel_path: rel.to_owned(),
            content,
        });
    }
}

fn child(directory: &str, name: &str) -> String {
    if directory == "." {
        name.to_owned()
    } else {
        format!("{directory}/{name}")
    }
}

fn test_source(path: &str, root: &str, package_dir: &str, package_files: &[String]) -> bool {
    let relative = if root == "." {
        Some(path)
    } else {
        path.strip_prefix(root).and_then(|s| s.strip_prefix('/'))
    };
    let Some(relative) = relative else {
        return false;
    };
    relative.ends_with("_test.dart")
        || relative
            .rsplit_once('/')
            .is_some_and(|(parent, _)| test_directory(parent, root, package_files))
        || root != package_dir
            && root
                .rsplit('/')
                .next()
                .is_some_and(|part| matches!(part, "test" | "tests"))
            && !package_files.contains(&format!("{root}/pubspec.yaml"))
}

fn test_directory(parent: &str, root: &str, package_files: &[String]) -> bool {
    let mut directory: String = if root == "." {
        String::new()
    } else {
        root.to_owned()
    };
    parent.split('/').any(|part| {
        if !directory.is_empty() {
            directory.push('/');
        }
        directory.push_str(part);
        matches!(part, "test" | "tests")
            && !package_files.contains(&format!("{directory}/pubspec.yaml"))
    })
}

fn excluded_or_link(rel: &str, name: &str, entry: Entry) -> Option<Problem> {
    if EXCLUDED.contains(&name) {
        let message = "selected source tree contains excluded generated/cache files";
        Some(problem(rel, ExceptionName::ExcludedTreeError, message))
    } else if matches!(entry, Entry::Link { .. }) {
        Some(problem(
            rel,
            ExceptionName::DartSourceLink,
            "source directory is a symlink",
        ))
    } else {
        None
    }
}

/// The `pubspec.yaml` of the package directory `dir` (empty for the snapshot root).
pub(crate) fn pubspec_path(dir: &str) -> String {
    if str::is_empty(dir) {
        "pubspec.yaml".to_owned()
    } else {
        format!("{dir}/pubspec.yaml")
    }
}

/// The package directory of the scan (#1539): the nearest directory at or above a scan root that
/// holds a regular `pubspec.yaml`, when every scan root has the same one. Else the snapshot root,
/// whose `pubspec.yaml` the survey reads as before; a package file between it and a scan root
/// stays a gap.
fn package_dir(snapshot: &mut Snapshot, roots: &[String]) -> String {
    let mut found: Option<String> = None;
    for root in roots {
        let parts: Vec<&str> = if root == "." {
            Vec::new()
        } else {
            root.split('/').collect()
        };
        let nearest = (0..=Vec::len(&parts))
            .rev()
            .map(|end| parts[..end].join("/"))
            .find(|dir| {
                let path = pubspec_path(dir);
                snapshot.is_file(&path) && !Snapshot::is_link(snapshot, &path)
            });
        let Some(nearest) = nearest else {
            return String::new();
        };
        match &found {
            Some(dir) if *dir != nearest => return String::new(),
            _ => found = Some(nearest),
        }
    }
    found.unwrap_or_default()
}

/// The metadata and the digest of the `pubspec.yaml` of the package directory. A missing file
/// gives an empty name that no import matches; a link, an unreadable file or a missing name stops
/// the collection.
fn read_pubspec(snapshot: &mut Snapshot, dir: &str) -> Result<(Pubspec, Option<String>), String> {
    let path = pubspec_path(dir);
    let path = String::as_str(&path);
    if Snapshot::is_link(snapshot, path) {
        return Err("regular pubspec.yaml is required inside the snapshot".to_owned());
    }
    if !snapshot.is_file(path) && !snapshot.is_dir(path) {
        let missing = Pubspec {
            name: None,
            sdk: None,
            state: SdkState::Missing,
        };
        return Ok((missing, None));
    }
    let raw = snapshot
        .read(path)
        .ok_or_else(|| format!("cannot read regular pubspec.yaml: {NOT_REGULAR}"))?;
    let metadata = pubspec::read(&raw);
    if metadata.name.is_none() {
        return Err("pubspec.yaml must declare a valid package name".to_owned());
    }
    Ok((metadata, Some(archkeel_facts::identity::sha256_hex(&raw))))
}

fn collisions(sources: &[Source], problems: &mut Vec<Problem>) {
    let mut paths: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for source in sources {
        paths
            .entry(source.module.as_str())
            .or_default()
            .push(source.rel_path.as_str());
    }
    for (module, mut group) in paths.into_iter().filter(|(_, group)| group.len() > 1) {
        group.sort_unstable();
        let message = format!("{module} maps from {}", group.join(", "));
        for rel in &group {
            problems.push(problem(rel, ExceptionName::DartModuleCollision, &message));
        }
    }
}

#[cfg(test)]
#[path = "discover_tests.rs"]
mod tests;
