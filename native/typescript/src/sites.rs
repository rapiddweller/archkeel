// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites of a file: calls, `new` expressions and references, and the written string
//! comparisons (`_sites`, `_call_site`, `_comparison_literal`).
//!
//! `parse.py` finds the scope of each site and the names that it shadows with one climb over the
//! ancestors for each node. The walk here carries both on its stack, so each node is placed in
//! constant time. What needs the whole file waits for `finish`: the frames of the names that a
//! site may not use free are known only when the walk has ended.

use std::collections::HashSet;

use tree_sitter::Node;

use crate::ancestors::{
    Entry, Shadow, CROSSED_FUNCTION, CROSSED_PLAIN_FUNCTION, ERROR_ABOVE, HARD_AMBIGUOUS,
    IN_PUBLICATION, IN_TYPE, IN_WITH,
};
use crate::kinds::{F, K};
use crate::members::Cx;
use crate::pytext::decode;
use crate::scope::Frames;
use crate::site_names::Names;
use crate::site_paths::{is_script_root, Paths, Text};
use crate::site_syntax::{
    class_member, declaration_name, holds_types, is_function_scope, is_member_name,
    is_reference_kind, is_wrapper, relatives, script_escape, subscript_receiver, target_name,
    written_string, ReceiverKind,
};
use crate::source::Span;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
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
    free: Option<(u32, Text)>,
    /// A shorthand property counts as a reference in a script only.
    shorthand: bool,
}

/// A string that an equality or a `case` writes, and the definition that holds it.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Comparison {
    pub span: Span,
    pub scope: Option<u32>,
}

/// The sites and the written string comparisons of one file.
#[derive(Default)]
pub struct Sites {
    pub sites: Vec<Site>,
    pub comparisons: Vec<Comparison>,
    pub paths: Paths,
    pub names: Names,
    /// The ids of the function expressions and arrow functions that wrap a script.
    wrappers: HashSet<usize>,
}

/// What the walk offers about the node that it enters.
pub struct Visit<'a, 't> {
    pub node: Node<'t>,
    pub kind: K,
    pub stack: &'a [Entry<'t>],
    /// The flags that the ancestors set.
    pub seen: u8,
    /// The definition that holds the node, or the definition that the node opens.
    pub scope: Option<u32>,
    pub opened: bool,
}

/// What a node adds to the entry that the walk pushes for it.
pub struct Extension {
    pub flags: u8,
    pub shadow: Shadow,
    pub callee: bool,
    pub wrapped_call: bool,
}

impl Sites {
    /// Read the node that the walk enters: record its sites, and give the entry its extension.
    pub fn enter(&mut self, cx: &Cx, visit: &Visit) -> Extension {
        let Visit {
            node, kind, stack, ..
        } = *visit;
        let near = relatives(stack);
        let parent = near.0;
        let late = parent.is_some_and(|parent| {
            matches!(parent.kind, K::AsExpression | K::SatisfiesExpression)
                && node.start_byte() > parent.node.start_byte()
        });
        let typed = visit.seen & IN_TYPE != 0 || late;
        let mut flags = 0;
        if typed || holds_types(kind) {
            flags |= IN_TYPE;
        }
        if kind == K::WithStatement {
            flags |= IN_WITH;
        }
        if self.publishes(cx, node, parent) {
            flags |= IN_PUBLICATION;
        }
        let callee = parent.is_some_and(|parent| match parent.kind {
            K::CallExpression | K::NewExpression => {
                cx.field(parent.node, F::Function) == Some(node)
                    || cx.field(parent.node, F::Constructor) == Some(node)
            }
            K::MemberExpression | K::SubscriptExpression => parent.callee,
            _ => false,
        });
        let wrapped_call =
            kind == K::Arguments && parent.is_some_and(|call| self.calls_wrapper(cx, call));
        let shadow = self.shadow(cx, visit, near);
        let declared = is_reference_kind(kind) && declaration_name(cx, node, parent);
        self.note_names(cx, visit, declared);
        let skipped = node.has_error() || visit.seen & ERROR_ABOVE != 0;
        if !skipped {
            self.comparison(cx, visit);
            self.call(cx, visit, near, typed);
            if is_reference_kind(kind) && !declared && !callee {
                self.reference(cx, visit, near, typed);
            }
        }
        Extension {
            flags,
            shadow,
            callee,
            wrapped_call,
        }
    }

    /// `_global_publication_target`, for the left side of an assignment that has two names and a
    /// root of the browser globals first.
    fn publishes(&mut self, cx: &Cx, node: Node, parent: Option<&Entry>) -> bool {
        let assigned = parent.is_some_and(|parent| {
            parent.kind == K::AssignmentExpression && cx.field(parent.node, F::Left) == Some(node)
        });
        if !assigned {
            return false;
        }
        let Some(path) = self.paths.of(cx, node) else {
            return false;
        };
        self.paths.length(path) == 2
            && self.paths.head(path).is_some_and(|head| {
                is_script_root(cx.source.data.get(head.start..head.end).unwrap_or(&[]))
            })
    }

    /// Whether the callee of the call that holds an `arguments` node wraps a script.
    fn calls_wrapper(&self, cx: &Cx, call: &Entry) -> bool {
        let mut callee = cx.field(call.node, F::Function);
        while let Some(inner) = callee.filter(|item| cx.k(*item) == K::ParenthesizedExpression) {
            callee = inner.named_child(0);
        }
        callee.is_some_and(|callee| self.wrappers.contains(&callee.id()))
    }

    /// The scopes between a node and its definition (`_active_scope_names`).
    fn shadow(&mut self, cx: &Cx, visit: &Visit, near: (Option<&Entry>, Option<&Entry>)) -> Shadow {
        let node = visit.node;
        let range = |field: F| {
            cx.field(node, field)
                .map(|item| (item.start_byte(), item.end_byte()))
        };
        if visit.opened {
            let chain = self.names.open(None, range(F::Parameters), range(F::Body));
            return Shadow {
                chain: Some(chain),
                ambiguous: 0,
            };
        }
        let mut shadow = near.0.map_or_else(Shadow::default, |parent| parent.shadow);
        match visit.kind {
            K::InternalModule | K::ClassExpression | K::Object => {
                shadow.ambiguous |= HARD_AMBIGUOUS
            }
            K::StatementBlock => {
                let modeled = near
                    .0
                    .is_some_and(|owner| cx.field(owner.node, F::Body) == Some(node));
                if !modeled {
                    shadow.ambiguous |= HARD_AMBIGUOUS;
                }
            }
            kind if is_function_scope(kind) => {
                let wraps = kind != K::GeneratorFunction && is_wrapper(cx, node, visit.stack);
                if wraps {
                    self.wrappers.insert(node.id());
                }
                shadow.chain = Some(self.names.open(
                    shadow.chain,
                    range(F::Parameters),
                    range(F::Body),
                ));
                shadow.ambiguous |= CROSSED_FUNCTION;
                if !wraps {
                    shadow.ambiguous |= CROSSED_PLAIN_FUNCTION;
                }
            }
            K::MethodDefinition if !class_member(near) => {
                shadow.chain = Some(self.names.open(
                    shadow.chain,
                    range(F::Parameters),
                    range(F::Body),
                ));
                shadow.ambiguous |= HARD_AMBIGUOUS;
            }
            _ => {}
        }
        shadow
    }

    /// The names that `_scope_names` collects: parameters, declarators and assignments.
    fn note_names(&mut self, cx: &Cx, visit: &Visit, declared: bool) {
        let node = visit.node;
        let start = node.start_byte();
        match visit.kind {
            K::Identifier if declared => self.names.declared(start, Text::of(node)),
            K::VariableDeclarator => {
                let name = cx
                    .field(node, F::Name)
                    .filter(|name| cx.k(*name) == K::Identifier);
                if let Some(name) = name {
                    self.names.written(start, Text::of(name));
                }
            }
            K::AssignmentExpression => {
                let left = cx
                    .field(node, F::Left)
                    .filter(|left| cx.k(*left) == K::Identifier);
                if let Some(left) = left {
                    self.names.written(start, Text::of(left));
                }
            }
            _ => {}
        }
    }

    /// `_comparison_literal`.
    fn comparison(&mut self, cx: &Cx, visit: &Visit) {
        let node = visit.node;
        let literal = match visit.kind {
            K::SwitchCase => written_string(cx, cx.field(node, F::Value)),
            K::BinaryExpression => {
                let operator = cx.field(node, F::Operator).map(|item| cx.k(item));
                let compares = matches!(
                    operator,
                    Some(K::Equal | K::NotEqual | K::StrictEqual | K::StrictNotEqual)
                );
                if !compares {
                    return;
                }
                written_string(cx, cx.field(node, F::Left))
                    .or_else(|| written_string(cx, cx.field(node, F::Right)))
            }
            _ => return,
        };
        if let Some(literal) = literal {
            self.comparisons.push(Comparison {
                span: cx.span(literal),
                scope: visit.scope,
            });
        }
    }

    /// `_dependency_receiver` and the path of its result.
    fn receiver_path(&mut self, cx: &Cx, target: Node) -> Option<u32> {
        let mut at = target;
        loop {
            if let Some(path) = self.paths.of(cx, at) {
                return Some(path);
            }
            let child = match cx.k(at) {
                K::ParenthesizedExpression => at.named_child(0),
                K::MemberExpression | K::SubscriptExpression => cx.field(at, F::Object),
                _ => None,
            };
            at = child?;
        }
    }

    /// `_call_site`.
    fn call(
        &mut self,
        cx: &Cx,
        visit: &Visit,
        near: (Option<&Entry>, Option<&Entry>),
        typed: bool,
    ) {
        let node = visit.node;
        if !matches!(visit.kind, K::CallExpression | K::NewExpression) {
            return;
        }
        let Some(target) = cx
            .field(node, F::Function)
            .or_else(|| cx.field(node, F::Constructor))
        else {
            return;
        };
        let path = self.receiver_path(cx, target);
        let declarator = near.0.filter(|parent| {
            parent.kind == K::VariableDeclarator && cx.field(parent.node, F::Value) == Some(node)
        });
        let declared = declarator.and_then(|parent| cx.field(parent.node, F::Name));
        let named = target_name(cx, target);
        let new = visit.kind == K::NewExpression;
        let free = path
            .filter(|_| !typed && visit.seen & IN_WITH == 0)
            .and_then(|path| self.paths.head(path))
            .zip(near.0.map(|parent| parent.frame));
        self.sites.push(Site {
            kind: if new { SiteKind::New } else { SiteKind::Call },
            expression: Expression::Node(Text::of(target)),
            span: cx.span(node),
            scope: visit.scope,
            assigned_name: declared
                .filter(|name| cx.k(*name) == K::Identifier)
                .map(Text::of),
            name: named.name,
            receiver: named.receiver,
            computed: named.computed,
            shadow: near.0.map_or_else(Shadow::default, |parent| parent.shadow),
            scope_ambiguous: false,
            assignment_span: declared.map(|name| cx.span(name)),
            assignment_annotation: declarator
                .and_then(|parent| cx.type_text(cx.field(parent.node, F::Type))),
            initializer: new.then(|| Text::of(node)),
            usage: SiteUse::Value,
            receiver_kind: named.receiver_kind,
            path,
            script_free: false,
            script_escape: false,
            free: free.map(|(head, frame)| (frame, head)),
            shorthand: false,
        });
    }

    /// The reference sites of `_sites`: an identifier that is no name, no callee and no member name.
    fn reference(
        &mut self,
        cx: &Cx,
        visit: &Visit,
        near: (Option<&Entry>, Option<&Entry>),
        typed: bool,
    ) {
        let node = visit.node;
        if is_member_name(cx, node, near) {
            return;
        }
        let member = near.0.filter(|parent| {
            parent.kind == K::MemberExpression && cx.field(parent.node, F::Property) == Some(node)
        });
        let named = match member {
            Some(parent) => target_name(cx, parent.node),
            None => crate::site_syntax::Target {
                name: Some(Text::of(node)),
                receiver: None,
                computed: false,
                receiver_kind: ReceiverKind::None,
            },
        };
        let receiver = named.receiver.filter(|text| !text.is_empty());
        let (target, above) = match (member, receiver) {
            (Some(parent), Some(_)) => (parent.node, near.1),
            _ => (node, near.0),
        };
        let path = self.paths.of(cx, target);
        let key = above.is_some_and(|above| {
            above.kind == K::Pair && cx.field(above.node, F::Key) == Some(target)
        });
        let free = path
            .filter(|_| !key && !typed && visit.seen & (IN_WITH | IN_PUBLICATION) == 0)
            .and_then(|path| self.paths.head(path))
            .zip(near.0.map(|parent| parent.frame));
        let joined = match (receiver, named.name) {
            (Some(receiver), Some(name)) if !name.is_empty() => Expression::Member(receiver, name),
            _ => Expression::Node(Text::of(node)),
        };
        self.sites.push(Site {
            kind: SiteKind::Reference,
            expression: joined,
            span: cx.span(node),
            scope: visit.scope,
            assigned_name: None,
            name: named.name,
            receiver: named.receiver,
            computed: named.computed || subscript_receiver(cx, node, near.0),
            shadow: near.0.map_or_else(Shadow::default, |parent| parent.shadow),
            scope_ambiguous: false,
            assignment_span: None,
            assignment_annotation: None,
            initializer: None,
            usage: if visit.kind == K::TypeIdentifier {
                SiteUse::Type
            } else if receiver.is_some() {
                SiteUse::Member
            } else {
                SiteUse::Value
            },
            receiver_kind: named.receiver_kind,
            path,
            script_free: false,
            script_escape: script_escape(cx, node, near),
            free: free.map(|(head, frame)| (frame, head)),
            shorthand: visit.kind == K::ShorthandPropertyIdentifier,
        });
    }

    /// Close the file: the frames and the mode of the script decide what the walk could not.
    pub fn finish(&mut self, frames: &Frames, data: &[u8], script_mode: bool) {
        self.sites.retain(|site| !site.shorthand || script_mode);
        let index = frames.free_index();
        for site in &mut self.sites {
            site.script_free = site.free.is_some_and(|(frame, head)| {
                let name = decode(data.get(head.start..head.end).unwrap_or(&[]));
                index.is_free(frame, &name)
            });
            let bits = site.shadow.ambiguous;
            let plain = if script_mode {
                CROSSED_PLAIN_FUNCTION
            } else {
                CROSSED_FUNCTION
            };
            site.scope_ambiguous = bits & (HARD_AMBIGUOUS | plain) != 0;
        }
        self.sites
            .sort_by_key(|site| (site.span.line, site.span.column, site.kind));
    }
}

#[cfg(test)]
#[path = "sites_tests.rs"]
mod tests;
