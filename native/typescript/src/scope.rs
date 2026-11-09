// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Scope frames: the names that a scope binds (`_script_bindings`).
//!
//! A frame belongs to a scope node of `_SCRIPT_SCOPES`. It counts the bindings of each name. A
//! pattern that binds no plain name makes the frame ambiguous, and an ambiguous frame blocks every
//! name. The frames are in a `Vec`, and a frame knows its parent frame, so a lookup climbs the
//! chain without a tree node.

use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::kinds::{F, K};
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

/// A frame that binds a name, and the widest end of the ranges of the binding frames up to this
/// one: the frames are numbered in document order, so a frame lies below a binding frame exactly
/// when a range that starts at or before its number reaches it.
struct Range {
    start: u32,
    widest: u32,
}

/// `Frames::free_index`.
pub struct FreeIndex<'a> {
    bound: HashMap<&'a str, Vec<Range>>,
    blocked: Vec<bool>,
}

impl FreeIndex<'_> {
    /// A frame is free of `name` when it and the frames above it bind no `name` and are not
    /// ambiguous (`_script_free` over the frames of the ancestors).
    pub fn is_free(&self, frame: u32, name: &str) -> bool {
        if self.blocked.get(frame as usize).copied().unwrap_or(true) {
            return false;
        }
        let Some(ranges) = self.bound.get(name) else {
            return true;
        };
        let before = ranges.partition_point(|range| range.start <= frame);
        before
            .checked_sub(1)
            .and_then(|at| ranges.get(at))
            .is_none_or(|range| range.widest < frame)
    }
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

    /// The names that the root frame binds and that another frame binds too. A write of any other
    /// name of the root has the root as its nearest binding, whatever the depth, and needs no climb.
    pub fn shadowed_root_names(&self) -> HashSet<&str> {
        let root = &self.list[ROOT as usize];
        self.list[1..]
            .iter()
            .flat_map(|frame| frame.names.keys())
            .filter(|name| root.names.contains_key(name.as_str()))
            .map(String::as_str)
            .collect()
    }

    /// `_script_bound_scope`: the nearest frame, from `from` up, that binds `name`. The walk uses
    /// the memo; the tests compare the two.
    #[cfg(test)]
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

    /// `bound_scope` with a memo. Every frame that the climb passes has the same answer, so a
    /// chain of n frames costs n steps for each name, not n steps for each write.
    pub fn bound_scope_memo(
        &self,
        memo: &mut HashMap<String, HashMap<u32, Option<u32>>>,
        from: u32,
        name: &str,
    ) -> Option<u32> {
        let known = memo.entry(name.to_owned()).or_default();
        let mut passed = Vec::new();
        let mut at = from;
        let found = loop {
            if let Some(answer) = known.get(&at) {
                break *answer;
            }
            passed.push(at);
            if self.count(at, name) > 0 {
                break Some(at);
            }
            if at == ROOT {
                break None;
            }
            match self.list.get(at as usize) {
                Some(frame) => at = frame.parent,
                None => break None,
            }
        };
        for frame in passed {
            known.insert(frame, found);
        }
        found
    }

    /// The answer to "does a frame at or above this one bind the name, or is one ambiguous", for
    /// any frame and name, without a climb. The frames are numbered in document order, so the
    /// frames below a frame are the numbers up to its last descendant. A name keeps the ranges of
    /// the frames that bind it, and a frame is below a binding frame when its number is in a range.
    pub fn free_index(&self) -> FreeIndex<'_> {
        let count = self.list.len();
        let mut last: Vec<u32> = (0..count).map(|at| at as u32).collect();
        for at in (1..count).rev() {
            let parent = self.list.get(at).map_or(0, |frame| frame.parent) as usize;
            let own = last.get(at).copied().unwrap_or(0);
            if let Some(slot) = last.get_mut(parent) {
                *slot = (*slot).max(own);
            }
        }
        let mut blocked = Vec::with_capacity(count);
        let mut bound: HashMap<&str, Vec<Range>> = HashMap::new();
        for (at, frame) in self.list.iter().enumerate() {
            let above = at > 0 && blocked.get(frame.parent as usize).copied().unwrap_or(false);
            blocked.push(frame.ambiguous || above);
            let end = last.get(at).copied().unwrap_or(0);
            for name in frame.names.keys() {
                let ranges = bound.entry(name.as_str()).or_default();
                let widest = ranges.last().map_or(end, |range| range.widest.max(end));
                ranges.push(Range {
                    start: at as u32,
                    widest,
                });
            }
        }
        FreeIndex { bound, blocked }
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
                    K::PairPattern => F::Value,
                    K::RequiredParameter | K::OptionalParameter => F::Pattern,
                    _ => F::Left,
                };
                match cx.field(node, field) {
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
