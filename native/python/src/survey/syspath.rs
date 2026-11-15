// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A `sys.path.append` of a directory of the snapshot that adds no name the scan imports (AD-522).
//!
//! A write to `sys.path` is an `import_system_change` gap of the whole run (AD-450). One write is
//! no gap: `sys.path.append(str(Path(__file__).resolve().parents[k]))`, an expression statement
//! of the module body, when the directory `P` that it names lies in the snapshot and holds no
//! module-like entry named like a first segment that the scan imports. An entry that is not
//! imported cannot change what an import finds. Every other form keeps the gap.
//!
//! The refusals, each proven by a plant (`tests/python_syspath_trees.py`):
//!
//! - R1 `append` only: `insert` at any index puts `P` before the standard library and the project.
//! - R2 the conflict set holds the first segment of each import target, of the scan namespace and
//!   of each literal import call, also when no absolute import names it (a relative import
//!   through a namespace portion).
//! - R3 the entry of the namespace is exempt only when `P/n` is itself a scan root, the namespace
//!   is `n`, `P/n/__init__.py` exists and no other entry of `P` is named `n`.
//! - R4 a module-like entry is any directory or link, and each file `n.py`, `n.pyc`, `n.pyw`,
//!   `n.so`, `n.pyd`, `n.<tag>.so`, `n.<tag>.pyd`, compared without case. A listing that has a
//!   problem or a hidden entry refuses.
//! - R5 the expression, the binders of `sys`, `pathlib`, `Path`, `str` and `__file__`, a file path
//!   without a link and a directory inside the snapshot.

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use archkeel_snapshot::Snapshot;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ModModule, Number, Stmt};

use super::binders::Binders;
use super::hazards::{Site, IMPORT_SYSTEM};
use crate::module::Module;

/// The kind of a site that is a candidate: the write form that the module body proves. It never
/// reaches a gap: `settle` drops it or turns it into `import_system_change`.
pub(super) const PATH_WRITE: &str = "path_write";

/// The directory that `sys.path.append` of a statement names, as the number of path components to
/// strip from the module file: `Path(__file__).resolve().parents[k]` is `k + 1`, `.parent` is 1.
pub(super) fn levels(stmt: &Stmt, tree: &ModModule, binders: &Binders) -> Option<usize> {
    let Stmt::Expr(node) = stmt else {
        return None;
    };
    let Expr::Call(call) = &*node.value else {
        return None;
    };
    let Expr::Attribute(method) = &*call.func else {
        return None;
    };
    let target = dotted(&method.value)?;
    // R1: `append` only.
    if target != "sys.path"
        || method.attr.as_str() != "append"
        || !call.arguments.keywords.is_empty()
    {
        return None;
    }
    let [argument] = &*call.arguments.args else {
        return None;
    };
    let facts = Facts::of(tree);
    let (inner, wrapped) = match argument {
        Expr::Call(wrap) if is_name(&wrap.func, "str") => match &*wrap.arguments.args {
            [only] if wrap.arguments.keywords.is_empty() => (only, true),
            _ => return None,
        },
        other => (other, false),
    };
    let (count, path_form) = parent_chain(inner)?;
    let one = |name: &str| binders.count(name) == Some(1);
    let none = |name: &str| binders.count(name) == Some(0);
    let sys = facts.plain_sys == 1 && one("sys");
    let pathlib = match path_form {
        Form::Module => facts.plain_pathlib == 1 && one("pathlib"),
        Form::Name => facts.from_path == 1 && one("Path"),
    };
    // R5: no other binder of `str` (a Path object in `sys.path` is ignored, so `str` is needed)
    // or of `__file__`; a star import makes each count unknown.
    (sys && pathlib && wrapped && none("str") && none("__file__")).then_some(count)
}

/// How the `Path` class is named in the expression.
#[derive(Clone, Copy)]
enum Form {
    Module,
    Name,
}

/// `X.parent`..., `X.parents[k]` over `Path(__file__).resolve()`: the levels and the form.
fn parent_chain(expr: &Expr) -> Option<(usize, Form)> {
    match expr {
        Expr::Subscript(node) => {
            let Expr::Attribute(parents) = &*node.value else {
                return None;
            };
            let Expr::NumberLiteral(number) = &*node.slice else {
                return None;
            };
            let Number::Int(int) = &number.value else {
                return None;
            };
            let k: usize = int.to_string().parse().ok()?;
            if parents.attr.as_str() != "parents" {
                return None;
            }
            Some((k + 1, resolved(&parents.value)?))
        }
        Expr::Attribute(node) if node.attr.as_str() == "parent" => match resolved(&node.value) {
            Some(form) => Some((1, form)),
            None => {
                let (count, form) = parent_chain(&node.value)?;
                Some((count + 1, form))
            }
        },
        _ => None,
    }
}

/// `Path(__file__).resolve()` or `pathlib.Path(__file__).resolve()`.
fn resolved(expr: &Expr) -> Option<Form> {
    let Expr::Call(resolve) = expr else {
        return None;
    };
    let Expr::Attribute(method) = &*resolve.func else {
        return None;
    };
    if method.attr.as_str() != "resolve" || !resolve.arguments.is_empty() {
        return None;
    }
    let Expr::Call(path) = &*method.value else {
        return None;
    };
    let form = path_class(path)?;
    match &*path.arguments.args {
        [only] if is_name(only, "__file__") && path.arguments.keywords.is_empty() => Some(form),
        _ => None,
    }
}

fn path_class(call: &ExprCall) -> Option<Form> {
    match &*call.func {
        Expr::Name(node) if node.id.as_str() == "Path" => Some(Form::Name),
        other if dotted(other).as_deref() == Some("pathlib.Path") => Some(Form::Module),
        _ => None,
    }
}

fn is_name(expr: &Expr, name: &str) -> bool {
    matches!(expr, Expr::Name(node) if node.id.as_str() == name)
}

fn dotted(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(node) => Some(node.id.to_string()),
        Expr::Attribute(node) => Some(format!("{}.{}", dotted(&node.value)?, node.attr.as_str())),
        _ => None,
    }
}

/// The plain imports of the names that the expression reads.
#[derive(Default)]
struct Facts {
    plain_sys: usize,
    plain_pathlib: usize,
    from_path: usize,
}

impl Facts {
    fn of(tree: &ModModule) -> Self {
        let mut facts = Facts::default();
        facts.visit_body(&tree.body);
        facts
    }
}

impl<'a> Visitor<'a> for Facts {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => {
                for alias in node.names.iter().filter(|alias| alias.asname.is_none()) {
                    self.plain_sys += usize::from(alias.name.as_str() == "sys");
                    self.plain_pathlib += usize::from(alias.name.as_str() == "pathlib");
                }
            }
            Stmt::ImportFrom(node) if node.level == 0 => {
                let module = node
                    .module
                    .as_ref()
                    .is_some_and(|name| name.as_str() == "pathlib");
                let plain = node
                    .names
                    .iter()
                    .filter(|alias| alias.name.as_str() == "Path" && alias.asname.is_none());
                self.from_path += usize::from(module) * plain.count();
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }
}

/// The listing of a directory that a verdict depends on: the path and the sorted names.
pub(crate) struct Listing {
    pub path: String,
    pub text: String,
}

/// What the survey knows for the decision of every write.
pub(super) struct Scan<'s> {
    pub modules: &'s [Module],
    pub imports: &'s [Record<ImportFact>],
    pub roots: &'s [String],
    pub namespace: &'s str,
}

/// Drop each candidate write that adds no imported name; turn each other into the gap of the
/// whole run. The listing of each directory that a dropped write depends on is returned.
pub(super) fn settle(
    found: Vec<(usize, Site)>,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> (Vec<(usize, Site)>, Vec<Listing>) {
    let conflicts = conflict_set(scan);
    let (mut kept, mut listings) = (Vec::new(), BTreeSet::new());
    for (index, site) in found {
        if site.kind != PATH_WRITE {
            kept.push((index, site));
            continue;
        }
        let levels = site.detail.parse::<usize>().unwrap_or(usize::MAX);
        match harmless(&scan.modules[index].rel, levels, &conflicts, scan, snapshot) {
            Some(listing) => {
                listings.insert((listing.path, listing.text));
            }
            None => kept.push((
                index,
                Site {
                    kind: IMPORT_SYSTEM,
                    detail: "sys.path".to_owned(),
                    range: site.range,
                },
            )),
        }
    }
    let listings = listings
        .into_iter()
        .map(|(path, text)| Listing { path, text })
        .collect();
    (kept, listings)
}

/// R2: the first segment of each import target, of the namespace and of each literal call, folded.
fn conflict_set(scan: &Scan<'_>) -> HashSet<String> {
    let first = |name: &str| name.split('.').next().unwrap_or(name).to_lowercase();
    let mut names: HashSet<String> = scan
        .imports
        .iter()
        .map(|record| first(record.data.data().target_module.as_str()))
        .collect();
    names.insert(first(scan.namespace));
    names
}

/// The listing of the directory when the write adds no imported name, else `None`.
fn harmless(
    rel: &str,
    levels: usize,
    conflicts: &HashSet<String>,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> Option<Listing> {
    let parts: Vec<&str> = rel.split('/').collect();
    if levels == 0 || levels > parts.len() {
        return None;
    }
    // R5: no link on the path of the file, and the directory is inside the snapshot.
    for end in 1..=parts.len() {
        let prefix = parts[..end].join("/");
        if snapshot.real(&prefix).as_deref() != Some(prefix.as_str()) {
            return None;
        }
    }
    let directory = parts[..parts.len() - levels].join("/");
    let place = if directory.is_empty() {
        "."
    } else {
        directory.as_str()
    };
    let (files, directories) = listed(snapshot, place)?;
    let mut count: HashMap<String, usize> = HashMap::new();
    for name in &directories {
        *count.entry(name.to_lowercase()).or_default() += 1;
    }
    for name in &files {
        if let Some(module) = module_name(name) {
            *count.entry(module).or_default() += 1;
        }
    }
    for (name, entries) in &count {
        if !conflicts.contains(name) {
            continue;
        }
        if !(entries == &1 && exempt(name, &directories, &directory, scan, snapshot)) {
            return None;
        }
    }
    let mut names: Vec<&String> = files.iter().chain(&directories).collect();
    names.sort();
    let text = names
        .iter()
        .map(|name| name.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    Some(Listing {
        path: format!("{place}/"),
        text,
    })
}

/// R3: the one entry of the namespace is no new module when it is the scan root itself.
fn exempt(
    name: &str,
    directories: &[String],
    directory: &str,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> bool {
    let namespace = scan.namespace;
    if name != namespace.to_lowercase() || namespace.contains('.') {
        return false;
    }
    let place = if directory.is_empty() {
        namespace.to_owned()
    } else {
        format!("{directory}/{namespace}")
    };
    let root = scan
        .roots
        .iter()
        .any(|root| root.trim_start_matches("./") == place);
    root && directories.iter().any(|entry| entry == namespace)
        && snapshot.real(&place).as_deref() == Some(place.as_str())
        && snapshot.is_file(&format!("{place}/__init__.py"))
}

/// The files and directories of `place`, or `None` for a listing with a problem or a hidden entry.
fn listed(snapshot: &mut Snapshot, place: &str) -> Option<(Vec<String>, Vec<String>)> {
    let before = std::mem::take(&mut snapshot.problems);
    let listing = snapshot.entries(place);
    let hidden = snapshot.hidden_entries(place);
    let clean = snapshot.problems.is_empty() && hidden.is_empty();
    snapshot.problems.extend(before);
    clean.then_some(listing)
}

/// R4: the module that a file can be, without case: `n.py`, `n.pyc`, `n.pyw`, `n.so`, `n.pyd`,
/// `n.<tag>.so` and `n.<tag>.pyd`.
fn module_name(file: &str) -> Option<String> {
    let lower = file.to_lowercase();
    let suffixes = [".py", ".pyc", ".pyw", ".so", ".pyd"];
    suffixes
        .iter()
        .any(|suffix| lower.ends_with(suffix))
        .then(|| lower.split('.').next().unwrap_or(&lower).to_owned())
        .filter(|name| !name.is_empty())
}

#[cfg(test)]
#[path = "syspath_tests.rs"]
mod tests;
