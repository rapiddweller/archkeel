// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The models of an inside-contract tree (AD-385).
//!
//! The reference engine evaluates each inside contract with the facts of the one scan, clipped
//! to its mount (`check/evaluation/evaluate.py` `_inside_rule_results`). For each mount, in the
//! order of the walk:
//!
//! 1. the owner is the root, or the mount whose parent key is the owner key of this mount;
//! 2. the parent is the component of that id in the clipped contract of the owner
//!    (`_inside_parent_component`);
//! 3. the source domain is each module of the domain of the owner that the parent owns
//!    (`_inside_source_domain`), and the claims of the inside contract are clipped to the parent
//!    (`archkeel_contract::policy::clip_inside`).
//!
//! Each contract of the tree has a model of its own, with its own brand and serial: a PASS of a
//! rule needs the scope proof of the model whose contract holds the rule. The models share the
//! reply part and one scope state: a coverage failure of any mount (a cut claim, a profile limit,
//! a rule without subjects) is a failure of the whole run in the reference engine.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use archkeel_contract::policy::{clip_inside, ContractTree, InsideMount};
use archkeel_contract::{Component, Contract, Package};

use crate::causes::Part;
use crate::domain::Domain;
use crate::graph::Graph;
use crate::ids::ModuleId;
use crate::model::Model;
use crate::ownership::in_scope;
use crate::proof::{self, MountFacts, State};
use crate::reason::Reason;

/// The models of one run: the model of the root contract, and the model of each inside contract
/// in the order of the walk of the tree. Only this module makes one.
#[derive(Debug)]
pub struct ModelTree {
    root: Model,
    mounts: Vec<Model>,
}

/// One mount after its clip: the clipped contract, whether the clip cut a claim, and its domain.
struct Clip {
    contract: Contract,
    outside: bool,
    domain: Domain,
}

impl ModelTree {
    /// The models of a contract without mounts: the root model alone.
    pub fn of(contract: &Contract, graph: Graph) -> Result<ModelTree, Box<(Graph, Reason)>> {
        Model::of(contract, graph).map(|root| ModelTree {
            root,
            mounts: Vec::new(),
        })
    }

    /// The models of an assembled tree over the reply part of the run. A contract with too many
    /// components gives the reply part back.
    pub fn tree(tree: &ContractTree, graph: Graph) -> Result<ModelTree, Box<(Graph, Reason)>> {
        let root = tree.root();
        let (clips, missing) = clips(root, tree.mounts(), &graph);
        let mut tables = Vec::with_capacity(clips.len() + 1);
        for contract in std::iter::once(root).chain(clips.iter().map(|clip| &clip.contract)) {
            match Model::components_of(contract) {
                Ok(table) => tables.push(table),
                Err(reason) => return Err(Box::new((graph, reason))),
            }
        }
        let mut tables = tables.into_iter();
        let Some(root_table) = tables.next() else {
            return Err(Box::new((graph, Reason::TooManyRows("components"))));
        };
        let state = {
            let facts: Vec<MountFacts<'_>> = clips
                .iter()
                .zip(tree.mounts())
                .map(|(clip, mount)| MountFacts {
                    contract: &clip.contract,
                    outside: clip.outside,
                    parent_id: mount.parent_id(),
                    domain: clip.domain.names().map(String::as_str).collect(),
                })
                .collect();
            let state = proof::state(root, &graph, Some(&facts));
            match (state, missing) {
                (State::Complete, Some(parent)) => State::Unread(Part::MountParent(parent)),
                (state, _) => state,
            }
        };
        let graph = Arc::new(graph);
        let mounts = clips
            .into_iter()
            .zip(tables)
            .map(|(clip, table)| {
                let shared = Arc::clone(&graph);
                Model::made(
                    clip.contract,
                    table,
                    shared,
                    state.clone(),
                    Some(clip.domain),
                )
            })
            .collect();
        let root = Model::made(root.clone(), root_table, graph, state, None);
        Ok(ModelTree { root, mounts })
    }

    /// The model of the root contract.
    pub fn root(&self) -> &Model {
        &self.root
    }

    /// The model of each inside contract, in the order of the walk.
    pub fn mounts(&self) -> &[Model] {
        &self.mounts
    }

    /// The model of each contract of the tree: the root first.
    pub fn models(&self) -> impl Iterator<Item = &Model> {
        std::iter::once(&self.root).chain(&self.mounts)
    }
}

/// The clip of each mount in the order of the walk, and the parent key of the first mount whose
/// parent is not in the clipped contract of its owner.
fn clips(root: &Contract, mounts: &[InsideMount], graph: &Graph) -> (Vec<Clip>, Option<String>) {
    let modules = graph.modules();
    let every: Vec<ModuleId> = modules.iter().map(|(id, _)| id).collect();
    let mut by_parent: HashMap<&str, usize> = HashMap::new();
    let mut clips: Vec<Clip> = Vec::with_capacity(mounts.len());
    let mut missing = None;
    for mount in mounts {
        let owner = mount.owner_id().as_str();
        // `available_by_owner`: every module for the root, else the domain of the owner mount.
        let (owner_contract, available) = if owner.is_empty() {
            (Some(root), every.as_slice())
        } else {
            match by_parent.get(owner).and_then(|index| clips.get(*index)) {
                Some(clip) => (Some(&clip.contract), clip.domain.held()),
                None => (None, &[][..]),
            }
        };
        let parent_id = mount.parent().id();
        let found = owner_contract
            .and_then(|contract| contract.components().iter().find(|c| c.id() == parent_id));
        if found.is_none() {
            missing.get_or_insert_with(|| mount.parent_id().clone());
        }
        // `_inside_parent_component`: a nested parent outside its owner keeps no package.
        let parent: &Component = found.unwrap_or(mount.parent());
        let packages: &[Package] = match found {
            None if !owner.is_empty() => &[],
            _ => parent.packages(),
        };
        let exact = parent.exact_modules();
        let owns = |name: &str| {
            exact.iter().any(|item| item.as_text() == name)
                || packages.iter().any(|item| in_scope(name, item.as_text()))
        };
        let rows = available
            .iter()
            .filter_map(|id| modules.get(*id).map(|row| (*id, row.name())));
        let (held, names): (Vec<ModuleId>, HashSet<String>) = rows
            .filter(|(_, name)| owns(name))
            .map(|(id, name)| (id, name.to_owned()))
            .unzip();
        let clipped = clip_inside(packages, exact, mount.contract());
        let roots = packages.iter().map(|p| p.as_text().to_owned()).collect();
        let domain = Domain::new(held, names, roots);
        by_parent.insert(mount.parent_id().as_str(), clips.len());
        clips.push(Clip {
            contract: clipped.contract().clone(),
            outside: !clipped.outside().is_empty(),
            domain,
        });
    }
    (clips, missing)
}
