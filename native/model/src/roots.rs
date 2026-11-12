// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether the scan roots hold a domain of the reply (slice S7, AD-384).
//!
//! Reference engine: `ir/coverage.py` `under_roots`, `_package_paths` (the branch of a suffix
//! other than `.py`), `scan_covers_packages`, `scan_covers_exact_modules` and
//! `scan_domains_complete`. A path is a list of parts without `.` and empty parts; `..` stays a
//! part, as in `PurePosixPath`. An absolute root holds nothing, and an absolute file lies under
//! no relative root. The roots come only from the settings that `Graph::derive` bound to the
//! scope labels of the reply.

use crate::ownership::in_scope;

/// The parts of a path, or `None` for an absolute path.
fn parts(path: &str) -> Option<Vec<&str>> {
    if path.starts_with('/') {
        return None;
    }
    Some(
        path.split('/')
            .filter(|part| !part.is_empty() && *part != ".")
            .collect(),
    )
}

/// The path without its last `steps` parts; an empty path stays empty (`PurePosixPath.parent`).
fn up(mut path: Vec<&str>, steps: usize) -> Vec<&str> {
    path.truncate(path.len().saturating_sub(steps));
    path
}

/// The scan roots of a run and the module files of its reply.
#[derive(Debug)]
pub(crate) struct Roots<'m> {
    roots: Vec<Vec<&'m str>>,
    files: Vec<(&'m str, &'m str)>,
}

impl<'m> Roots<'m> {
    /// The relative roots (an absolute root holds nothing) and the `(module, file)` pairs.
    pub(crate) fn new(roots: &'m [String], files: Vec<(&'m str, &'m str)>) -> Self {
        Roots {
            roots: roots.iter().filter_map(|root| parts(root)).collect(),
            files,
        }
    }

    /// True when a root holds the path (`_under`). An absolute path lies under no root.
    fn holds(&self, path: Option<&[&str]>) -> bool {
        path.is_some_and(|path| self.roots.iter().any(|root| path.starts_with(root)))
    }

    /// True when a root holds a repository-relative file (`under_roots`).
    pub(crate) fn under(&self, file: &str) -> bool {
        self.holds(parts(file).as_deref())
    }

    /// The module files of the reply.
    pub(crate) fn files(&self) -> &[(&'m str, &'m str)] {
        &self.files
    }

    /// The directories of a package: for each module below it, the parent directory of its
    /// file, one more step up for each module part after the first below the package.
    fn package_paths(&self, package: &str) -> Vec<Option<Vec<&'m str>>> {
        let depth = package.split('.').count();
        self.files
            .iter()
            .filter(|(name, _)| in_scope(name, package))
            .map(|(name, file)| {
                let extra = name.split('.').count().saturating_sub(depth);
                parts(file).map(|path| up(path, extra.saturating_sub(1) + 1))
            })
            .collect()
    }

    /// `scan_covers_packages`: each package has a directory, and a root holds each one.
    fn covers_packages(&self, packages: &[&str]) -> bool {
        !packages.is_empty()
            && !self.roots.is_empty()
            && packages.iter().all(|package| {
                let paths = self.package_paths(package);
                !paths.is_empty() && paths.iter().all(|path| self.holds(path.as_deref()))
            })
    }

    /// `scan_covers_exact_modules`: each exact module has a file under a root.
    fn covers_exact(&self, exact: &[&str]) -> bool {
        !self.roots.is_empty()
            && exact.iter().all(|wanted| {
                self.files
                    .iter()
                    .any(|(name, file)| name == wanted && self.under(file))
            })
    }

    /// `scan_domains_complete`: the packages (when there are any) and the exact modules.
    pub(crate) fn covers(&self, packages: &[&str], exact: &[&str]) -> bool {
        (packages.is_empty() || self.covers_packages(packages)) && self.covers_exact(exact)
    }
}

#[cfg(test)]
#[path = "roots_tests.rs"]
mod tests;
