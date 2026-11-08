// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Scope frames: the names that a scope binds (`_script_bindings`).
//!
//! A frame belongs to a scope node of `_SCRIPT_SCOPES`. It counts the bindings of each name. A
//! pattern that binds no plain name makes the frame ambiguous, and an ambiguous frame blocks every
//! name. The frames are in a `Vec`, and a frame knows its parent frame, so a lookup climbs the
//! chain without a tree node.

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::K;
use crate::members::{has_backslash, named_children, Cx};

/// The frame of the root node. Every other frame has a parent.
pub const ROOT: u32 = 0;

#[derive(Default)]
pub struct Frame {
    parent: u32,
    names: HashMap<String, u32>,
    ambiguous: bool,
}

pub struct Frames {
    list: Vec<Frame>,
}

/// Whether a kind opens a scope that binds names (`_SCRIPT_SCOPES`), and whether it is a `var` scope
/// (`_SCRIPT_VAR_SCOPES`).
pub fn scope_kind(kind: K) -> Option<bool> {
    match kind {
        K::FunctionDeclaration
        | K::FunctionExpression
        | K::GeneratorFunctionDeclaration
        | K::GeneratorFunction
        | K::ArrowFunction
        | K::MethodDefinition
        | K::ClassStaticBlock => Some(true),
        K::StatementBlock
        | K::CatchClause
        | K::ForInStatement
        | K::ForStatement
        | K::SwitchBody
        | K::Class
        | K::ClassDeclaration
        | K::ClassBody => Some(false),
        _ => None,
    }
}

/// `_SCRIPT_FUNCTIONS`.
pub fn is_function(kind: K) -> bool {
    matches!(
        kind,
        K::FunctionDeclaration
            | K::FunctionExpression
            | K::GeneratorFunctionDeclaration
            | K::GeneratorFunction
            | K::ArrowFunction
            | K::MethodDefinition
    )
}

impl Frames {
    pub fn new() -> Self {
        Self {
            list: vec![Frame::default()],
        }
    }

    pub fn push(&mut self, parent: u32) -> u32 {
        self.list.push(Frame {
            parent,
            ..Frame::default()
        });
        (self.list.len() - 1) as u32
    }

    pub fn blur(&mut self, frame: u32) {
        if let Some(frame) = self.list.get_mut(frame as usize) {
            frame.ambiguous = true;
        }
    }

    pub fn is_ambiguous(&self, frame: u32) -> bool {
        self.list
            .get(frame as usize)
            .is_some_and(|frame| frame.ambiguous)
    }

    pub fn bind(&mut self, frame: u32, name: String) {
        if let Some(frame) = self.list.get_mut(frame as usize) {
            *frame.names.entry(name).or_default() += 1;
        }
    }

    /// How many bindings of `name` the frame holds.
    pub fn count(&self, frame: u32, name: &str) -> u32 {
        self.list
            .get(frame as usize)
            .and_then(|frame| frame.names.get(name))
            .copied()
            .unwrap_or(0)
    }

    /// The names of one frame, sorted as `sorted(bindings.get(scope))` does.
    pub fn sorted_names(&self, frame: u32) -> Vec<String> {
        let mut names: Vec<String> = self
            .list
            .get(frame as usize)
            .map(|frame| frame.names.keys().cloned().collect())
            .unwrap_or_default();
        names.sort();
        names
    }

    /// `_script_bound_scope`: the nearest frame, from `from` up, that binds `name`.
    pub fn bound_scope(&self, from: u32, name: &str) -> Option<u32> {
        let mut at = from;
        loop {
            if self.count(at, name) > 0 {
                return Some(at);
            }
            if at == ROOT {
                return None;
            }
            at = self.list.get(at as usize)?.parent;
        }
    }

    /// Bind each name that `pattern` assigns; a target that is no plain name blurs the frame.
    pub fn bind_pattern(&mut self, cx: &Cx, frame: u32, pattern: Node) {
        for target in assignment_targets(cx, pattern) {
            let plain = matches!(
                cx.k(target),
                K::Identifier | K::TypeIdentifier | K::ShorthandPropertyIdentifierPattern
            );
            let name = cx.text(target);
            if plain && !has_backslash(&name) {
                self.bind(frame, name);
            } else {
                self.blur(frame);
            }
        }
    }
}

/// `_assignment_targets`: the nodes that a pattern assigns, in document order. An explicit stack
/// replaces the recursion, so a pattern nested 30 000 levels deep gives its targets.
pub fn assignment_targets<'t>(cx: &Cx, pattern: Node<'t>) -> Vec<Node<'t>> {
    let mut found = Vec::new();
    let mut pending = vec![pattern];
    while let Some(node) = pending.pop() {
        let kind = cx.k(node);
        match kind {
            K::ArrayPattern | K::ObjectPattern => {
                pending.extend(named_children(node).into_iter().rev());
            }
            K::AssignmentPattern
            | K::ObjectAssignmentPattern
            | K::PairPattern
            | K::RequiredParameter
            | K::OptionalParameter => {
                let field = match kind {
                    K::PairPattern => "value",
                    K::RequiredParameter | K::OptionalParameter => "pattern",
                    _ => "left",
                };
                match node.child_by_field_name(field) {
                    Some(target) => pending.push(target),
                    None => found.push(node),
                }
            }
            K::RestPattern | K::ParenthesizedExpression if node.named_child_count() == 1 => {
                pending.extend(node.named_child(0));
            }
            K::Comment => {}
            _ => found.push(node),
        }
    }
    found
}

#[cfg(test)]
#[path = "scope_tests.rs"]
mod tests;
