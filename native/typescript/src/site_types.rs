// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one site and the one constructor that lists all of them (`sites.rs` collects them).

use crate::ancestors::Shadow;
use crate::site_paths::Text;
use crate::site_syntax::{ReceiverKind, Target};
use crate::source::Span;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum SiteKind {
    Call,
    New,
    Reference,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SiteUse {
    Type,
    Value,
    Member,
}

/// The text of a site: a node, or a receiver and a name that a reference joins with a dot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Expression {
    Node(Text),
    Member(Text, Text),
}

/// A call, a `new` or a reference. The texts are ranges of the file and the paths and names are
/// shared (`site_paths.rs`, `site_names.rs`), so a site costs the same for any chain around it.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Site {
    pub kind: SiteKind,
    pub expression: Expression,
    pub span: Span,
    /// The definition that holds the site: its name, line and column are in `Scopes`.
    pub scope: Option<u32>,
    pub assigned_name: Option<Text>,
    pub name: Option<Text>,
    pub receiver: Option<Text>,
    pub computed: bool,
    pub shadow: Shadow,
    pub scope_ambiguous: bool,
    pub assignment_span: Option<Span>,
    pub assignment_annotation: Option<String>,
    pub initializer: Option<Text>,
    pub usage: SiteUse,
    pub receiver_kind: ReceiverKind,
    pub path: Option<u32>,
    pub script_free: bool,
    pub script_escape: bool,
    /// The frame and the first name of the path, when only the frames can still veto the site.
    pub free: Option<(u32, Text)>,
    /// A shorthand property counts as a reference in a script only.
    pub shorthand: bool,
}

/// What every site has. `Site::new` is the one place that lists all fields; a caller sets the
/// few that only its kind has.
pub struct Common {
    pub kind: SiteKind,
    pub expression: Expression,
    pub span: Span,
    pub scope: Option<u32>,
    pub shadow: Shadow,
    pub named: Target,
    pub path: Option<u32>,
    pub free: Option<(u32, Text)>,
}

impl Site {
    pub fn new(common: Common) -> Self {
        let Common {
            kind,
            expression,
            span,
            scope,
            shadow,
            named,
            path,
            free,
        } = common;
        Self {
            kind,
            expression,
            span,
            scope,
            assigned_name: None,
            name: named.name,
            receiver: named.receiver,
            computed: named.computed,
            shadow,
            scope_ambiguous: false,
            assignment_span: None,
            assignment_annotation: None,
            initializer: None,
            usage: SiteUse::Value,
            receiver_kind: named.receiver_kind,
            path,
            script_free: false,
            script_escape: false,
            free,
            shorthand: false,
        }
    }
}

/// A string that an equality or a `case` writes, and the definition that holds it.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Comparison {
    pub span: Span,
    pub scope: Option<u32>,
}
