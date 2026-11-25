// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The string table of one facts file: each distinct text has one integer id (AD-1047).

use rustc_hir::def_id::DefId;
use rustc_middle::ty::TyCtxt;
use std::collections::{HashMap, HashSet};

/// Texts with their ids. An id is the index in the table that the file writes first.
pub(crate) struct Names {
    ids: HashMap<String, u32>,
    list: Vec<String>,
    defs: HashMap<DefId, u32>,
    /// The ADTs of other crates that a type walk met: the facts need their fields too, because a
    /// foreign ADT can hold a `dyn` value without any type argument (`io::Error`).
    pub(crate) foreign: HashSet<DefId>,
    /// The `dyn` traits (principal and auto) that a type walk met.
    pub(crate) dyn_traits: HashSet<DefId>,
}

/// The canonical `crate::module::Item` text of a definition. Local and foreign items read alike.
pub(crate) fn path(tcx: TyCtxt<'_>, d: DefId) -> String {
    format!(
        "{}{}",
        tcx.crate_name(d.krate),
        tcx.def_path(d).to_string_no_crate_verbose()
    )
}

impl Names {
    pub(crate) fn new() -> Self {
        Names {
            ids: HashMap::new(),
            list: Vec::new(),
            defs: HashMap::new(),
            foreign: HashSet::new(),
            dyn_traits: HashSet::new(),
        }
    }

    /// The id of a text. A new text gets the next id.
    pub(crate) fn text(&mut self, s: &str) -> u32 {
        if let Some(id) = self.ids.get(s) {
            return *id;
        }
        let id = self.list.len() as u32;
        self.list.push(s.to_string());
        self.ids.insert(s.to_string(), id);
        id
    }

    /// The id of the canonical path of a definition. A cache saves the repeated formatting.
    pub(crate) fn def(&mut self, tcx: TyCtxt<'_>, d: DefId) -> u32 {
        if let Some(id) = self.defs.get(&d) {
            return *id;
        }
        let id = self.text(&path(tcx, d));
        self.defs.insert(d, id);
        id
    }

    pub(crate) fn list(&self) -> &[String] {
        &self.list
    }
}
