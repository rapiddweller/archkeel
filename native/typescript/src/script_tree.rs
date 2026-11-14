// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the tree of one file: the named nodes in document order, the scopes that bind each
//! name and the answers that the tree keeps. The questions on it live in `script_scope.rs`,
//! `script_flags.rs` and `script_names.rs`.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::hash::BuildHasherDefault;
use std::rc::Rc;

use tree_sitter::Node;

use crate::layout::{IdHasher, IdMap};
use crate::tree::cx::Cx;

pub(crate) type Names = HashMap<String, u32>;

/// A scope that binds a name, with the range of its subtree and the nearest scope that binds the
/// same name and holds it (`up`, or `NONE`).
pub(crate) struct ScopeEntry {
    pub(crate) start: u32,
    pub(crate) end: u32,
    pub(crate) scope: u32,
    pub(crate) up: u32,
}

/// An immediately called function of a script: its call and the names that it gives the roots.
#[derive(Clone)]
pub(crate) struct Wrapper<'t> {
    pub call: Node<'t>,
    pub aliases: Vec<String>,
    /// The same names as a set, for the question "is this name an alias".
    pub names: HashSet<String>,
}

pub(crate) struct Tree<'a, 't> {
    pub cx: Cx<'a>,
    pub root: Node<'t>,
    /// The named nodes in document order (`_walk`).
    pub nodes: Rc<Vec<Node<'t>>>,
    /// The position of a node in `nodes`, by its id, and the end of its subtree.
    pub(crate) position: IdMap<usize>,
    pub(crate) subtree_end: Vec<u32>,
    /// The parent of each node of `nodes`. `Node::parent` of the parser climbs from the root and
    /// costs the depth times the width, so the climb of a question reads this table.
    pub(crate) parents: Vec<u32>,
    pub bindings: IdMap<Names>,
    pub ambiguous: HashSet<usize, BuildHasherDefault<IdHasher>>,
    /// Per position: the flags `IN_ERROR`, `IN_TYPE` and `IN_FUNCTION` of the node.
    pub(crate) flags: Vec<u8>,
    /// The answers of the climbs over the scopes, by name and by the node where the climb starts.
    pub(crate) memo: RefCell<Memo<'t>>,
    /// The scopes that bind each name, in document order (`index_scopes`).
    pub(crate) names_index: HashMap<String, Vec<ScopeEntry>>,
}

/// What `Tree` answers once and keeps: the wrapper of a node and the call chains.
#[derive(Default)]
pub(crate) struct Memo<'t> {
    /// `wrapper` of each node that was asked for: the call of a wrapper has the arguments read once.
    pub(crate) wrappers: IdMap<Option<Wrapper<'t>>>,
    /// `leads_to_call` by position: 0 not known, 1 no, 2 yes.
    pub(crate) calls: Vec<u8>,
}
