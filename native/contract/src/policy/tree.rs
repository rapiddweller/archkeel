// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Assemble the tree of a root contract and its inside contracts, as Python
//! `load_inside_contract_tree` (`ir/codec_inside.py`) does with a reader of Git blobs: the identity
//! of a mount is its normalized reference. The walk is depth first in the order of the components.

use std::collections::{BTreeMap, BTreeSet};

use crate::canonical::canonical_digest;
use crate::contract::{digest_of, parse_file};
use crate::document::{Contract, ParsedContract};
use crate::model::{Component, ContractDigest};
use crate::policy::issue::{IssueKind, Place, SourceProblem, TreeError, TreeIssue};
use crate::policy::reference::{identity, python_repr, safe};
use crate::policy::scope::{
    provenance_paths, record_ids, scope_key, scoped_contract, unsupported_fields,
};

record!(
    pub(crate),
    /// One mounted inside contract. Its IDs are in the scope of the component that names it.
    InsideMount {
        parent: Component,
        owner_id: String,
        parent_id: String,
        pointer: String,
        path: String,
        identity: String,
        contract: Contract,
        digest: ContractDigest,
        canonical_digest: ContractDigest,
    }
);

record!(
    pub(crate),
    /// A root contract and every inside contract that it mounts, checked as one value.
    ContractTree {
        root: Contract,
        mounts: Vec<InsideMount>,
        paths: Vec<String>,
        digest: ContractDigest,
        comparison_digest: ContractDigest,
        comparison: Contract,
    }
);

/// The state of one walk. `sources` holds the root too, so that a mount of the root is a cycle.
struct Walk<'a> {
    sources: BTreeMap<String, (String, &'a [u8])>,
    root_labels: BTreeSet<String>,
    seen: BTreeSet<String>,
    parent_ids: BTreeMap<String, String>,
    record_ids: BTreeSet<String>,
    paths: BTreeSet<String>,
    mounts: Vec<InsideMount>,
    issues: Vec<TreeIssue>,
}

/// The deepest mount: the bound of the Dart collector (lead decision L-24). Python stops near
/// depth 984 with a `RecursionError` and gives no verdict.
pub const MAX_DEPTH: usize = 900;

/// One level of the walk: the mount whose components it visits (the root when `None`), its scope
/// key, pointer, depth and identity, and the next component to visit.
struct Frame {
    mount: Option<usize>,
    id: String,
    pointer: String,
    depth: usize,
    identity: Option<String>,
    next: usize,
}

/// Assemble and check the tree of the root contract at `root_path`. The root is the result of
/// `parse`. For each inside contract the shell sends `(reference, identity, bytes)`: the
/// reference as the mount writes it, the repository-relative path that the shell resolved it to,
/// and the bytes. The shell resolves each path, refuses a path outside the repository and never
/// leaves out the identity; this crate reads no file. An identity that differs from the
/// normalized reference is a symbolic link: the issue `Linked`. `NeedsTree::mounts` names the
/// first paths to send; `TreeError::missing_paths` names deeper paths that the shell must add.
/// This is the only way from `NeedsTree` to a contract that can be used:
///
/// ```compile_fail
/// use archkeel_contract::{Contract, ParsedContract};
/// fn complete(parsed: ParsedContract) -> Contract {
///     match parsed {
///         ParsedContract::Complete(contract) => contract,
///         ParsedContract::NeedsTree(tree) => tree.contract,
///     }
/// }
/// ```
///
/// ```
/// use archkeel_contract::{parse, policy::assemble_tree};
/// let root = br#"{"schema_version": "3.14.0", "rules": [], "components": [{"id": "C-a",
///   "label": "a", "role": "component", "packages": ["p.a"], "responsibilities": ["Own a."],
///   "forbidden_responsibilities": [], "provenance": ["d.md"], "inside": "a.json"}]}"#;
/// let inside = br#"{"schema_version": "3.14.0", "components": [], "rules": []}"#;
/// let parsed = parse(root).unwrap();
/// let tree = assemble_tree("architecture-contract.json", parsed, &[("a.json", "a.json", inside)])
///     .unwrap();
/// assert_eq!(tree.mounts().len(), 1);
/// ```
pub fn assemble_tree(
    root_path: &str,
    root: ParsedContract,
    insides: &[(&str, &str, &[u8])],
) -> Result<ContractTree, TreeError> {
    let root = match root {
        ParsedContract::Complete(contract) => contract,
        ParsedContract::NeedsTree(tree) => tree.contract,
    };
    let root_identity = identity(root_path).ok_or(TreeError::UnsafeRootPath)?;
    let sources = sources(&root_identity, insides)?;
    let mut walk = Walk {
        sources,
        root_labels: root.components.iter().map(|c| c.label.0.clone()).collect(),
        // Python also puts the root in `seen`; `active` always holds it, so a mount of the root is a
        // cycle first.
        seen: BTreeSet::new(),
        parent_ids: BTreeMap::new(),
        record_ids: record_ids(&root),
        paths: provenance_paths(&root),
        mounts: Vec::new(),
        issues: Vec::new(),
    };
    walk.paths.insert(root_identity.clone());
    walk.children(&root, &root_identity);
    walk.module_targets(&root_identity, &root);
    if !walk.issues.is_empty() {
        return Err(TreeError::Issues(walk.issues));
    }
    let mut unmounted: BTreeSet<&String> = walk.sources.keys().collect();
    unmounted.remove(&root_identity);
    for mount in &walk.mounts {
        unmounted.remove(&mount.identity);
    }
    if !unmounted.is_empty() {
        let paths = unmounted.into_iter().cloned().collect();
        return Err(TreeError::Source(SourceProblem::Unmounted, paths));
    }
    Ok(finish(root, walk.mounts, walk.paths))
}

/// The inputs by their repository path, with the resolved path that the shell sends. Each path
/// is safe and unique. The root path is in the map without bytes: a mount of the root is a cycle,
/// so its bytes are never read.
fn sources<'a>(
    root: &str,
    insides: &[(&str, &str, &'a [u8])],
) -> Result<BTreeMap<String, (String, &'a [u8])>, TreeError> {
    let mut map = BTreeMap::from([(root.to_owned(), (root.to_owned(), &[][..]))]);
    let (mut unsafe_paths, mut repeated) = (BTreeSet::new(), BTreeSet::new());
    for (path, resolved, bytes) in insides {
        match (identity(path), identity(resolved)) {
            (None, _) => {
                unsafe_paths.insert((*path).to_owned());
            }
            (_, None) => {
                unsafe_paths.insert((*resolved).to_owned());
            }
            (Some(key), Some(resolved)) => {
                if map.insert(key.clone(), (resolved, bytes)).is_some() {
                    repeated.insert(key);
                }
            }
        }
    }
    if !unsafe_paths.is_empty() {
        let paths = unsafe_paths.into_iter().collect();
        return Err(TreeError::Source(SourceProblem::Unsafe, paths));
    }
    if !repeated.is_empty() {
        let paths = repeated.into_iter().collect();
        return Err(TreeError::Source(SourceProblem::Duplicate, paths));
    }
    Ok(map)
}

/// The SHA-256 of the joined hex digests, or the one digest of a tree without mounts.
fn joined(first: ContractDigest, rest: impl Iterator<Item = ContractDigest>) -> ContractDigest {
    let mut text = first.0.clone();
    let mut any = false;
    for digest in rest {
        text.push_str(&digest.0);
        any = true;
    }
    if any {
        digest_of(text.as_bytes())
    } else {
        first
    }
}

fn finish(root: Contract, mounts: Vec<InsideMount>, paths: BTreeSet<String>) -> ContractTree {
    let digest = joined(root.digest.clone(), mounts.iter().map(|m| m.digest.clone()));
    let canonical = mounts.iter().map(|m| m.canonical_digest.clone());
    let comparison_digest = joined(canonical_digest(&root), canonical);
    let mut comparison = root.clone();
    for mount in &mounts {
        comparison
            .components
            .extend(mount.contract.components.iter().cloned());
        comparison
            .rules
            .extend(mount.contract.rules.iter().cloned());
    }
    ContractTree {
        root,
        mounts,
        paths: paths.into_iter().collect(),
        digest,
        comparison_digest,
        comparison,
    }
}

impl Walk<'_> {
    /// Python `_load_inside_children`, with an explicit stack in place of the recursion: depth
    /// first in the order of the components, a mount before its own mounts.
    fn children(&mut self, root: &Contract, root_identity: &str) {
        let mut active = BTreeSet::from([root_identity.to_owned()]);
        let mut stack = vec![Frame {
            mount: None,
            id: String::new(),
            pointer: String::new(),
            depth: 0,
            identity: None,
            next: 0,
        }];
        while let Some(frame) = stack.last_mut() {
            let owner = frame.mount.and_then(|index| self.mounts.get(index));
            let contract = owner.map_or(root, |mount| &mount.contract);
            let Some(parent) = contract.components.get(frame.next).cloned() else {
                let done = stack.pop().and_then(|item| item.identity);
                done.map(|identity| active.remove(&identity));
                continue;
            };
            let index = frame.next;
            frame.next += 1;
            let Some(reference) = &parent.inside else {
                continue;
            };
            let place = Place {
                pointer: format!("{}/components/{index}/inside", frame.pointer),
                parent_id: scope_key(&frame.id, &parent.label.0),
                path: reference.0.clone(),
            };
            let (owner_id, depth) = (frame.id.clone(), frame.depth + 1);
            if let Some(mount) = self.mount(&owner_id, &parent, place, depth, &active) {
                active.insert(mount.identity.clone());
                stack.push(Frame {
                    mount: Some(self.mounts.len()),
                    id: mount.parent_id.clone(),
                    pointer: mount.pointer.clone(),
                    depth,
                    identity: Some(mount.identity.clone()),
                    next: 0,
                });
                self.mounts.push(mount);
            }
        }
    }

    /// Python `_inside_mount`: the checks of the reference before it is read.
    fn mount(
        &mut self,
        owner_id: &str,
        parent: &Component,
        place: Place,
        depth: usize,
        active: &BTreeSet<String>,
    ) -> Option<InsideMount> {
        self.paths.insert(place.path.clone());
        if depth > MAX_DEPTH {
            let reason = format!("the mount is deeper than {MAX_DEPTH} levels");
            self.issues
                .push(TreeIssue::new(IssueKind::TooDeep, &place, reason));
            return None;
        }
        let previous = self.parent_ids.get(&place.parent_id);
        let root_label = !owner_id.is_empty() && self.root_labels.contains(&place.parent_id);
        let elsewhere = previous.is_some_and(|location| *location != place.pointer);
        let kind = if root_label || elsewhere {
            Some((
                IssueKind::ParentIdCollision,
                "generated inside parent ID collision",
            ))
        } else if !safe(&place.path) {
            Some((IssueKind::UnsafePath, "unsafe repository path"))
        } else {
            None
        };
        if let Some((kind, reason)) = kind {
            self.issues.push(TreeIssue::new(kind, &place, reason));
            return None;
        }
        self.parent_ids
            .insert(place.parent_id.clone(), place.pointer.clone());
        self.read(owner_id, parent, place, active)
    }

    /// Python `_read_inside_mount`: read, parse, scope and record one inside contract.
    fn read(
        &mut self,
        owner_id: &str,
        parent: &Component,
        place: Place,
        active: &BTreeSet<String>,
    ) -> Option<InsideMount> {
        let key = identity(&place.path)?;
        let Some((resolved, bytes)) = self.sources.get(&key).cloned() else {
            let reason = format!("no bytes for {key}");
            self.issues
                .push(TreeIssue::new(IssueKind::Missing, &place, reason));
            return None;
        };
        if resolved != key {
            let reason = format!("the path is a link to {resolved}");
            self.issues
                .push(TreeIssue::new(IssueKind::Linked, &place, reason));
            return None;
        }
        if active.contains(&key) || self.seen.contains(&key) {
            let (kind, reason) = if active.contains(&key) {
                (IssueKind::Cycle, "reference cycle")
            } else {
                (IssueKind::DuplicateMount, "duplicate mount")
            };
            self.issues.push(TreeIssue::new(kind, &place, reason));
            return None;
        }
        let contract = match parse_file(bytes) {
            Ok(contract) => contract,
            Err(error) => {
                let kind = IssueKind::Contract(error.kind);
                self.issues
                    .push(TreeIssue::new(kind, &place, error.message));
                return None;
            }
        };
        self.seen.insert(key.clone());
        self.record_policy(&place, &contract);
        let scoped = scoped_contract(&place.parent_id, &contract);
        let ids = record_ids(&scoped);
        if let Some(collision) = ids.iter().find(|id| self.record_ids.contains(*id)) {
            let reason = format!("generated declaration ID collision: {collision}");
            self.issues.push(TreeIssue::new(
                IssueKind::DeclarationIdCollision,
                &place,
                reason,
            ));
            return None;
        }
        self.record_ids.extend(ids);
        Some(InsideMount {
            parent: parent.clone(),
            owner_id: owner_id.to_owned(),
            parent_id: place.parent_id,
            pointer: place.pointer,
            path: place.path,
            identity: key,
            contract: scoped,
            digest: digest_of(bytes),
            canonical_digest: canonical_digest(&contract),
        })
    }

    /// Python `_record_inside_policy`: an issue for root-only declarations; the mount stays.
    fn record_policy(&mut self, place: &Place, contract: &Contract) {
        let unsupported = unsupported_fields(contract);
        if !unsupported.is_empty() {
            let reason = format!(
                "unsupported non-empty declarations: {}",
                unsupported.join(", ")
            );
            let kind = IssueKind::UnsupportedDeclarations;
            self.issues.push(TreeIssue::new(kind, place, reason));
        }
        self.paths.extend(provenance_paths(contract));
    }

    /// Python `_duplicate_module_target_issues`: one module target path in one contract only. A
    /// path that the root declares two times is a parse error of the root, not an issue here.
    fn module_targets(&mut self, root_path: &str, root: &Contract) {
        let mut owners: BTreeMap<String, String> = BTreeMap::new();
        for target in module_paths(root) {
            owners
                .entry(target.to_owned())
                .or_insert_with(|| root_path.to_owned());
        }
        let mut issues = Vec::new();
        let declared = self
            .mounts
            .iter()
            .flat_map(|mount| module_paths(&mount.contract).map(move |target| (mount, target)));
        for (mount, target) in declared {
            match owners.get(target) {
                None => {
                    owners.insert(target.to_owned(), mount.path.clone());
                }
                Some(previous) => issues.push(module_issue(mount, target, previous)),
            }
        }
        self.issues.extend(issues);
    }
}

fn module_paths(contract: &Contract) -> impl Iterator<Item = &str> {
    let targets = contract
        .declarations
        .as_ref()
        .and_then(|d| d.modules.as_ref());
    targets
        .into_iter()
        .flatten()
        .map(|target| target.path.0.as_str())
}

fn module_issue(mount: &InsideMount, target: &str, previous: &str) -> TreeIssue {
    let reason = format!(
        "duplicate module target path {} in {}; already declared in {}",
        python_repr(target),
        python_repr(&mount.path),
        python_repr(previous)
    );
    let place = Place {
        pointer: mount.pointer.clone(),
        parent_id: mount.parent_id.clone(),
        path: mount.path.clone(),
    };
    TreeIssue::new(IssueKind::DuplicateModuleTarget, &place, reason)
}
