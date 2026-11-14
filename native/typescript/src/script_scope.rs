// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree of one file as the script facts read it (AD-340, PR 4.3a-4): the named nodes in
//! document order, the bindings of each scope (`_script_bindings`), the immediately called
//! wrappers of a script (`_script_wrapper`) and the questions that the producers of
//! `script_syntax.rs`, `script_writes.rs` and `script_alias.rs` ask again and again.
//!
//! Python answers these by climbing the parents and by walking a subtree for each question. Here
//! a subtree is a range of the document order, and a name is looked up in an index.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::hash::BuildHasherDefault;
use std::rc::Rc;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::scope::assignment_targets;
use crate::source::Span;
use crate::tree::cx::Cx;
use crate::tree::nodes::children;

/// `_SCRIPT_ROOTS`: the names of the browser global object.
pub(crate) fn is_root(name: &str) -> bool {
    crate::source_input::is_script_root(name.as_bytes())
}

/// `_SCRIPT_FUNCTIONS`.
pub(crate) fn is_function(kind: K) -> bool {
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

/// `_SCRIPT_VAR_SCOPES`.
pub(crate) fn is_var_scope(kind: K) -> bool {
    is_function(kind) || matches!(kind, K::Program | K::ClassStaticBlock)
}

/// `_SCRIPT_SCOPES`.
pub(crate) fn is_scope(kind: K) -> bool {
    is_var_scope(kind)
        || matches!(
            kind,
            K::StatementBlock
                | K::CatchClause
                | K::ForInStatement
                | K::ForStatement
                | K::SwitchBody
                | K::Class
                | K::ClassDeclaration
                | K::ClassBody
        )
}

/// `_SCRIPT_RECEIVER_SCOPES`.
pub(crate) fn is_receiver_scope(kind: K) -> bool {
    (is_function(kind) && kind != K::ArrowFunction) || kind == K::ClassStaticBlock
}

/// `_SCRIPT_CALLABLE_VALUES`.
pub(crate) fn is_callable_value(kind: K) -> bool {
    is_function(kind) || matches!(kind, K::Class | K::ClassDeclaration)
}

pub(crate) use crate::layout::{
    is_function_like, IdHasher, IdMap, Layout, IN_AMBIGUOUS, IN_ERROR, IN_FUNCTION, IN_TYPE, NONE,
};

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

impl<'a, 't> Tree<'a, 't> {
    /// The tree of a file from the layout that the walk recorded.
    pub(crate) fn from_layout(cx: Cx<'a>, root: Node<'t>, layout: Layout<'t>) -> Self {
        Self {
            cx,
            root,
            nodes: Rc::new(layout.nodes),
            position: layout.position,
            subtree_end: layout.ends,
            parents: layout.parents,
            bindings: IdMap::default(),
            ambiguous: HashSet::default(),
            flags: layout.flags,
            memo: RefCell::new(Memo::default()),
            names_index: HashMap::new(),
        }
    }

    pub(crate) fn k(&self, node: Node) -> K {
        self.cx.k(node)
    }

    pub(crate) fn text(&self, node: Node) -> String {
        self.cx.text(node)
    }

    pub(crate) fn field(&self, node: Node<'t>, field: F) -> Option<Node<'t>> {
        self.cx.field(node, field)
    }

    pub(crate) fn span(&self, node: Node) -> Span {
        self.cx.span(node)
    }

    /// Whether `node` is the field `field` of its parent.
    pub(crate) fn is_field_of_parent(&self, node: Node<'t>, field: F) -> bool {
        self.parent(node)
            .and_then(|parent| self.field(parent, field))
            .is_some_and(|found| found.id() == node.id())
    }

    /// `node.parent`, from the table of the file.
    pub(crate) fn parent(&self, node: Node<'t>) -> Option<Node<'t>> {
        let Some(at) = self.pos(node) else {
            return node.parent();
        };
        let above = self
            .parents
            .get(at)
            .copied()
            .filter(|above| *above != NONE)?;
        self.nodes.get(above as usize).copied()
    }

    /// `_ancestors`.
    pub(crate) fn ancestors(&self, node: Node<'t>) -> impl Iterator<Item = Node<'t>> + '_ {
        std::iter::successors(self.parent(node), |parent| self.parent(*parent))
    }

    /// The position of a node in the document order.
    pub(crate) fn pos(&self, node: Node) -> Option<usize> {
        self.position.get(&node.id()).copied()
    }

    /// `parse._in_error`: the node holds a repair, or lies inside one.
    pub(crate) fn in_error(&self, node: Node<'t>) -> bool {
        node.has_error() || self.flag(node, IN_ERROR)
    }

    /// `parse._in_type`.
    pub(crate) fn in_type(&self, node: Node<'t>) -> bool {
        self.flag(node, IN_TYPE)
    }

    /// The node lies inside a function declaration, a function expression, an arrow function or a
    /// method.
    pub(crate) fn inside_function(&self, node: Node<'t>) -> bool {
        self.flag(node, IN_FUNCTION)
    }

    /// The nodes of the subtree of `node` in document order, the node first (`_walk`).
    pub(crate) fn subtree(&self, node: Node) -> &[Node<'t>] {
        match self.position.get(&node.id()) {
            Some(&at) => self.nodes.get(at..self.end_of(at)).unwrap_or(&[]),
            None => &[],
        }
    }

    /// The end of the subtree of the node at a position.
    pub(crate) fn end_of(&self, at: usize) -> usize {
        self.subtree_end.get(at).map_or(at, |end| *end as usize)
    }

    /// The document-order range of the subtree of `node`.
    pub(crate) fn range(&self, node: Node) -> (usize, usize) {
        match self.position.get(&node.id()) {
            Some(&at) => (at, self.end_of(at)),
            None => (0, 0),
        }
    }

    pub(crate) fn at(&self, node: Node) -> usize {
        self.position.get(&node.id()).copied().unwrap_or(0)
    }

    /// The child that is not wrapped in parentheses.
    pub(crate) fn unparenthesized(&self, node: Node<'t>) -> Node<'t> {
        let mut node = node;
        while self.k(node) == K::ParenthesizedExpression {
            match node.named_child(0) {
                Some(child) => node = child,
                None => break,
            }
        }
        node
    }

    /// `while value is not None and kind is PARENTHESIZED: value = first named child`: ends with
    /// `None` for an empty pair of parentheses.
    pub(crate) fn strip_parentheses(&self, node: Option<Node<'t>>) -> Option<Node<'t>> {
        let mut value = node;
        while let Some(current) = value {
            if self.k(current) != K::ParenthesizedExpression {
                break;
            }
            value = current.named_child(0);
        }
        value
    }

    pub(crate) fn has_child_kind(&self, node: Node, kind: K) -> bool {
        children(node)
            .into_iter()
            .any(|child| self.k(child) == kind)
    }

    /// `_static_path`: the names of `a`, `a.b` and `a.b.c`; empty for any other node.
    pub(crate) fn static_path(&self, node: Node<'t>) -> Vec<String> {
        // The members of the chain, outermost first; the base decides the rest.
        let mut names: Vec<String> = Vec::new();
        let mut at = node;
        loop {
            match self.k(at) {
                K::Identifier
                | K::PropertyIdentifier
                | K::ShorthandPropertyIdentifier
                | K::ShorthandPropertyIdentifierPattern => return self.base(names, at),
                K::MemberExpression => match self.member(at, &mut names) {
                    Some(receiver) => at = receiver,
                    None => return Vec::new(),
                },
                _ => return Vec::new(),
            }
        }
    }

    /// The path of a chain that ends at the name `at`.
    fn base(&self, mut names: Vec<String>, at: Node<'t>) -> Vec<String> {
        names.push(self.text(at));
        names.reverse();
        names
    }

    /// One member of a chain: its name is kept, and its receiver is the next node to read.
    fn member(&self, at: Node<'t>, names: &mut Vec<String>) -> Option<Node<'t>> {
        let receiver = self.field(at, F::Object)?;
        let name = self.field(at, F::Property)?;
        if self.k(name) != K::PropertyIdentifier {
            return None;
        }
        names.push(self.text(name));
        Some(receiver)
    }

    pub(crate) fn in_ambiguous_scope(&self, node: Node<'t>) -> bool {
        self.parent(node)
            .is_some_and(|parent| self.flag(parent, IN_AMBIGUOUS))
    }

    /// The scope that binds `name` at `node`: the readers of a write ask the scope module.
    pub(crate) fn binding_scope(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        self.bound_scope(node, name)
    }

    /// The scope that binds `name` at `node` exactly once.
    pub(crate) fn sole_binding_scope(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        self.bound_scope(node, name)
            .filter(|scope| self.count(*scope, name) == 1)
    }

    /// `_script_free`: the root of the path of `target` is not bound by a scope above `node`.
    pub(crate) fn script_free(&self, target: Node<'t>, node: Node<'t>) -> bool {
        self.script_free_in(target, node, true)
    }

    /// `_script_free`, with or without the scopes that are not statically known (`ambiguous`).
    pub(crate) fn script_free_in(&self, target: Node<'t>, node: Node<'t>, ambiguous: bool) -> bool {
        if self.in_type(node) {
            return false;
        }
        let path = self.static_path(target);
        if let Some(parent) = self.parent(target) {
            if self.k(parent) == K::Pair && self.is_field_of_parent(target, F::Key) {
                return false;
            }
        }
        let Some(first) = path.first() else {
            return false;
        };
        let blocked_here = ambiguous && self.in_ambiguous_scope(node);
        !blocked_here && self.bound_scope(node, first).is_none()
    }

    /// `_declaration_name`.
    pub(crate) fn declaration_name(&self, node: Node<'t>) -> bool {
        let Some(parent) = self.parent(node) else {
            return false;
        };
        [F::Name, F::Pattern, F::Alias].into_iter().any(|field| {
            self.field(parent, field)
                .is_some_and(|found| found.id() == node.id())
        }) || self.k(parent) == K::NamespaceExport
            || (self.k(parent) == K::PairPattern
                && self
                    .field(parent, F::Key)
                    .is_some_and(|key| key.id() == node.id()))
    }

    /// `_script_assignment_targets`.
    pub(crate) fn script_targets(&self, node: Node<'t>) -> Vec<Node<'t>> {
        let kind = self.k(node);
        let left = match kind {
            K::AssignmentExpression | K::AugmentedAssignmentExpression | K::ForInStatement => {
                self.field(node, F::Left)
            }
            K::UpdateExpression => self.field(node, F::Argument),
            K::UnaryExpression if self.has_child_kind(node, K::Delete) => {
                self.field(node, F::Argument)
            }
            _ => None,
        };
        left.map_or_else(Vec::new, |pattern| assignment_targets(&self.cx, pattern))
    }
}
