// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of the scan of one file: the facts that it finds and the walker that holds them. The
//! walk is in `scan.rs`; the files below it fill the facts and use only this state.

use std::collections::{BTreeMap, BTreeSet};

use proc_macro2::Span;

use super::extracted::Tally;
use super::receivers::Selves;
use crate::definitions::{Definition, Holder, ImplBlock, MethodCall, OnSelf};
use crate::plant;
use crate::site::Site;
use crate::tokens::Chain;

/// A qualified path, or a `use` leaf: its first segment and the path as written.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct Reference {
    pub root: String,
    pub path: String,
    pub site: Site,
    /// The path starts with `::`: its first segment is a crate, and no local name hides it.
    pub absolute: bool,
    /// The segments of the path. A `use a::b::{self}` leaf is `a::b`.
    pub names: Vec<String>,
    /// The inline modules of the file that enclose the path: its lexical module.
    pub scope: Vec<String>,
    pub via: Via,
    /// The name of the `macro_rules!` definition whose body holds the path.
    pub in_macro: Option<String>,
    /// The `MacroDef::id` of that definition, in the file of the path.
    pub macro_id: usize,
}

/// How a reference comes into the file.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) enum Via {
    /// A path in code, in an attribute or in the body of a macro call.
    #[default]
    Path,
    /// A validated derive-helper path, including a bare child-module name.
    Helper,
    /// A leaf of a `use` item: the local name that it binds.
    Use {
        binding: Option<String>,
        reexport: bool,
        block: bool,
    },
    /// `use path::*`.
    Glob { reexport: bool, block: bool },
}

/// A place that the scan cannot read.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Concern {
    pub reason: String,
    pub site: Site,
    /// Known source module, relative to the file. The expansion target is unseen.
    pub source: Option<Vec<String>>,
    pub proof: Option<crate::attrs::model::Proof>,
}

/// A `mod name;` declaration: its file is not in this file.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Child {
    pub name: String,
    pub path: Option<String>,
    /// The names of the inline modules that enclose the declaration.
    pub inline: Vec<String>,
    /// A `cfg(test)` on the declaration, or on an item that holds it, marks a test module.
    pub test: bool,
    /// The declaration, or an inline module that holds it, may be removed by a `cfg` (AD-383).
    pub gated: bool,
    pub site: Site,
}

#[derive(Debug, Default)]
pub(crate) struct Scan {
    pub references: Vec<Reference>,
    pub concerns: Vec<Concern>,
    pub children: Vec<Child>,
    /// Each name that the file declares or imports (any namespace, any depth): a root in it is UNKNOWN.
    pub names: BTreeSet<String>,
    /// The names of `names` that can hide a crate. A name is left out only when its single source
    /// is a `use` leaf of the crate of that name (`use anyhow::anyhow;`): `anyhow::x` is in it.
    pub shadows: BTreeSet<String>,
    /// How many times the file declares or imports each name, in any namespace and at any depth.
    pub counts: BTreeMap<String, usize>,
    /// The inline modules of the file, each as the names from the file down.
    pub inlines: Vec<Vec<String>>,
    pub macro_defs: Vec<MacroDef>,
    /// The calls of macros in the file, placed or not.
    pub macro_calls: Vec<MacroCall>,
    /// Every name that the file writes in any token, for the safety net of `collect.rs`.
    pub mentioned: BTreeSet<String>,
    /// The items, the members of the inherent `impl` blocks and the members of the traits.
    pub definitions: Vec<Definition>,
    /// The crate of each `extern crate name;` other than `self`, and its place.
    pub extern_crates: Vec<(String, Site)>,
    /// Each `extern crate self as name;` outside a function body: its inline modules and `name`.
    pub self_aliases: Vec<(Vec<String>, String)>,
    /// The inherent `impl` blocks at any depth, and the method calls (#953).
    pub impls: Vec<ImplBlock>,
    pub method_calls: Vec<MethodCall>,
    pub orphans: crate::definitions::OrphanFacts,
    /// The structs and enums at module level that are in every configuration (AD-383).
    pub exact_types: BTreeSet<String>,
    /// An inner attribute of the file may remove the module in some configuration.
    pub gated_file: bool,
    /// Expression paths whose first name can be hidden by a generic parameter in this file.
    pub generic_paths: BTreeSet<(i64, i64)>,
    /// A `use` may be removed or rewritten by an attribute.
    pub conditional_use: bool,
    /// Names that a conditional `use` may fail to bind.
    pub conditional_bindings: BTreeSet<String>,
    /// Conditional glob leaves, by their source position.
    pub conditional_globs: BTreeSet<(i64, i64)>,
    /// Names bound by a use that is not public outside the crate.
    pub restricted_bindings: BTreeSet<String>,
    /// The second count of the tree, for the invariant of the extraction.
    pub tally: Tally,
}

/// A `macro_rules!` definition: the macros that its body calls, and the reasons why the scan
/// cannot read all of its body. Each call of the macro takes these reasons as UNKNOWN.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct MacroDef {
    pub name: String,
    /// The place of the definition in the macro list of its file.
    pub id: usize,
    pub calls: BTreeSet<String>,
    /// The methods that the body calls: each call of the macro calls them too (#953).
    pub methods: BTreeSet<String>,
    /// The functions that the body defines: a call of the macro may add them as members of an
    /// `impl` block that the scan does not see (AD-383).
    pub members: BTreeSet<String>,
    pub unknowns: Vec<String>,
    /// A definition in a function body is visible only in the rest of that body.
    pub local: Option<Local>,
}

/// The text where a `macro_rules!` of a block is visible: from its definition to the end of the
/// block. A position is a line and a column.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Local {
    pub from: (i64, i64),
    pub until: (i64, i64),
}

impl Local {
    /// Whether the call at `site` is in the text of the block after the definition.
    pub(crate) fn sees(&self, site: &Site) -> bool {
        let at = (site.line, site.column);
        self.from < at && at <= self.until
    }
}

/// A call of a macro. A call is placed when the scan reads it in code, and the macro is named by
/// a plain or a `crate::`, `self::` or `super::` path. A call in the tokens of another macro, or
/// by the path of a module, is not placed: the scan does not know which macro it names.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct MacroCall {
    pub name: String,
    pub site: Site,
    pub placed: bool,
    /// The call is at module level: it may define a name of the module, which a glob `use` of
    /// the module then brings in, so such a glob is UNKNOWN (`modules/filled.rs`).
    pub fills: bool,
}

pub(super) struct Walker<'a> {
    pub(super) lines: Vec<&'a str>,
    pub(super) features: &'a BTreeSet<String>,
    pub(super) exclude_tests: bool,
    pub(super) inline: Vec<String>,
    /// The `use` item that the walk is in starts with `::`.
    pub(super) absolute_use: bool,
    /// The `use` item that the walk is in is `pub`: it re-exports.
    pub(super) public_use: bool,
    /// The depth of the blocks (function bodies) that enclose the walk.
    pub(super) blocks: usize,
    /// The name of the `macro_rules!` definition that the walk is in.
    pub(super) in_macro: Option<String>,
    /// The end of each block that encloses the walk, the inner block last.
    pub(super) block_ends: Vec<(i64, i64)>,
    /// What the next reference is: set by the `use` handling, `Path` otherwise.
    pub(super) via: Via,
    /// What the walk is inside: it decides which members are definitions.
    pub(super) holder: Holder,
    /// What a plain `self` is at the walk (AD-383).
    pub(super) selves: Selves,
    pub(super) helpers: crate::attrs::model::Context,
    pub(super) tools: bool,
    pub(super) derives: Vec<Concern>,
    pub(super) out: Scan,
}

impl Walker<'_> {
    pub(super) fn site(&self, span: Span) -> Site {
        let (start, end) = (span.start(), span.end());
        let line = self.lines.get(start.line.saturating_sub(1)).copied();
        let excerpt: String = line.unwrap_or("").trim().chars().take(200).collect();
        Site {
            line: to_i64(start.line),
            end_line: to_i64(end.line),
            column: to_i64(start.column),
            excerpt,
        }
    }

    /// A call `x.m(..)` (`path` false), or a path call that the scan cannot resolve (`path` true).
    pub(super) fn method_call(
        &mut self,
        name: String,
        span: Span,
        (path, arity): (bool, Option<usize>),
    ) {
        self.method_call_on(name, span, (path, arity), None);
    }

    pub(super) fn method_call_on(
        &mut self,
        name: String,
        span: Span,
        (path, arity): (bool, Option<usize>),
        on_self: Option<OnSelf>,
    ) {
        let (site, scope) = (self.site(span), self.inline.clone());
        if plant::lose("method") {
            return;
        }
        self.out.method_calls.push(MethodCall {
            name,
            site,
            scope,
            path,
            arity,
            on_self,
        });
    }

    pub(super) fn refer(&mut self, names: &[String], span: Span) {
        self.refer_as(names, span, false);
    }

    pub(super) fn refer_as(&mut self, names: &[String], span: Span, absolute: bool) {
        if let Some(first) = names.first() {
            if plant::lose("reference") {
                return;
            }
            let site = self.site(span);
            self.out.references.push(Reference {
                root: first.clone(),
                path: names.join("::"),
                site,
                absolute,
                names: names.to_vec(),
                scope: self.inline.clone(),
                via: self.via.clone(),
                in_macro: self.in_macro.clone(),
                macro_id: self.out.macro_defs.len(),
            });
        }
    }

    pub(super) fn refer_chains(&mut self, found: Vec<Chain>) {
        let before = self.out.references.len();
        for chain in found {
            self.refer_as(&chain.names, chain.span, chain.absolute);
        }
        self.out.tally.unseen += self.out.references.len() - before;
    }
}

pub(super) fn to_i64(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}
