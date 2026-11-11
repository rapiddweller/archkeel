// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules of a collection request that a type cannot hold: the messages name the first field
//! that is not valid, as `facts_codec.decode_request` does.

use crate::identity::{inside, is_identifier};
use crate::request::{Interpreter, Request, Resolver, Scope, Snapshot};

impl<R> Request<R> {
    /// Check the snapshot and the scope. The settings of a language check themselves.
    pub fn check(&self) -> Result<(), String> {
        self.snapshot.check()?;
        self.scope.check(self.protocol_version.has_test_scope())
    }
}

impl Snapshot {
    fn check(&self) -> Result<(), String> {
        text(&self.root, "snapshot.root")?;
        if !is_absolute(&self.root) {
            return Err("snapshot.root must be an absolute path".to_owned());
        }
        text(&self.git_head, "snapshot.git_head")
    }
}

impl Scope {
    fn check(&self, test_scope: bool) -> Result<(), String> {
        if self.exclude_test_sources.is_some() != test_scope {
            return Err("scope fields mismatch".to_owned());
        }
        text(&self.namespace, "scope.namespace")?;
        if !self.namespace.split('.').all(is_identifier) {
            return Err("scope.namespace must be a dotted namespace".to_owned());
        }
        if self.roots.is_empty() {
            return Err("scope.roots must be a nonempty array".to_owned());
        }
        check_roots(&self.roots)?;
        Ok(())
    }
}

fn check_roots(roots: &[String]) -> Result<(), String> {
    for root in roots {
        relative(root, "scope.roots")?;
    }
    let parts: Vec<Vec<&str>> = roots.iter().map(|root| path_parts(root)).collect();
    for (index, root) in parts.iter().enumerate() {
        if roots[index + 1..].contains(&roots[index]) {
            return Err("scope.roots must not repeat".to_owned());
        }
        if parts[index + 1..].iter().any(|other| nested(root, other)) {
            return Err("scope.roots must not overlap".to_owned());
        }
    }
    Ok(())
}

/// Whether one path is a proper prefix of the other.
fn nested(left: &[&str], right: &[&str]) -> bool {
    let (short, long) = if left.len() <= right.len() {
        (left, right)
    } else {
        (right, left)
    };
    short.len() < long.len() && long.starts_with(short)
}

impl Resolver {
    pub(crate) fn check(&self) -> Result<(), String> {
        match self {
            Resolver::TypeScript(settings) => relative(&settings.tsconfig, "resolver.tsconfig"),
            Resolver::Rust(_) | Resolver::Dart(_) => Ok(()),
            Resolver::Python(settings) => settings.interpreter.check(),
        }
    }
}

/// The minor versions of Python that the native collector parses (`CPYTHON_NATIVE_RUNTIMES`).
const PYTHON_MINORS: std::ops::RangeInclusive<u32> = 11..=14;

impl Interpreter {
    fn check(&self) -> Result<(), String> {
        let label = "resolver.interpreter.version";
        let Some((3, minor)) = version_parts(&self.version) else {
            return Err(format!(
                "{label} must be a full Python version, such as 3.11.12"
            ));
        };
        if !PYTHON_MINORS.contains(&minor) {
            return Err(format!("{label} must be Python 3.11 to 3.14"));
        }
        module_names(&self.stdlib_module_names, "stdlib_module_names")?;
        module_names(&self.builtin_module_names, "builtin_module_names")
    }
}

/// The major and minor number of `platform.python_version()`: `major.minor.patch`, each a
/// number without a sign or a leading zero. The patch can end with one release tag (`a`, `b` or
/// `rc` and a number) and then one `+`, as a build from a development tree has.
fn version_parts(version: &str) -> Option<(u32, u32)> {
    let mut parts = version.split('.');
    let (major, minor, patch) = (parts.next()?, parts.next()?, parts.next()?);
    if parts.next().is_some() {
        return None;
    }
    let patch = patch.strip_suffix('+').unwrap_or(patch);
    let digits = patch.len() - patch.trim_start_matches(|c: char| c.is_ascii_digit()).len();
    let (number, tag) = patch.split_at(digits);
    let tag_ok = tag.is_empty()
        || ["a", "b", "rc"]
            .iter()
            .any(|kind| tag.strip_prefix(kind).is_some_and(is_number));
    if !(is_number(major) && is_number(minor) && is_number(number) && tag_ok) {
        return None;
    }
    Some((major.parse().ok()?, minor.parse().ok()?))
}

/// Plain ASCII digits without a leading zero; `0` alone is a number.
fn is_number(text: &str) -> bool {
    !text.is_empty()
        && text.bytes().all(|byte| byte.is_ascii_digit())
        && (text == "0" || !text.starts_with('0'))
}

fn module_names(names: &[String], field: &str) -> Result<(), String> {
    let label = format!("resolver.interpreter.{field}");
    if !names.iter().all(|name| is_identifier(name)) {
        return Err(format!("{label} must hold module names"));
    }
    if names.windows(2).any(|pair| pair[0] >= pair[1]) {
        return Err(format!("{label} must be sorted and unique"));
    }
    Ok(())
}

fn text(value: &str, label: &str) -> Result<(), String> {
    if value.is_empty() || value.contains('\0') {
        return Err(format!("{label} must be a nonempty string"));
    }
    Ok(())
}

fn relative(path: &str, label: &str) -> Result<(), String> {
    text(path, label)?;
    if !inside(path) {
        return Err(format!("{label} must stay inside the snapshot"));
    }
    Ok(())
}

// The parts PurePosixPath keeps: no empty part and no "." part.
fn path_parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect()
}

fn is_absolute(root: &str) -> bool {
    let bytes = root.as_bytes();
    let posix = root.starts_with('/') && !root.contains('\\');
    let drive = bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'/' | b'\\');
    let unc = root.starts_with("\\\\") || root.starts_with("//");
    let windows = (drive || unc) && !(root.contains('/') && root.contains('\\'));
    posix || windows
}
