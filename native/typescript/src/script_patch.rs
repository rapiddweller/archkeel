// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The member patches of a global in a scanned file (#1674, AD-788 amendment): `Math.max = f`,
//! `JSON['parse'] = f`, `Object.assign(Math, { max: f })`, `Object.defineProperty(JSON, 'parse',
//! …)`, `console.__defineGetter__('log', …)`. After such a write a use of the member runs or reads
//! the value, which can be a function of another module. So the write withholds the native proof
//! of each use of that member, and of each use of the global as a whole value; a use of another
//! member keeps it. A literal value can be no function, so a write of a literal patches nothing.

use tree_sitter::Node;

use crate::kinds::F;
use crate::script_names::bound_scope;
use crate::script_scope::is_root;
use crate::script_syntax::Producer;
use crate::script_tree::Tree;
use crate::script_types::Patch;
use crate::tree::cx::Cx;

/// The members of `Object` and `Reflect` that write members of their first argument (AD-766).
const REFLECTIVE: [(&str, &str); 7] = [
    ("Object", "assign"),
    ("Object", "defineProperty"),
    ("Object", "defineProperties"),
    ("Object", "setPrototypeOf"),
    ("Reflect", "set"),
    ("Reflect", "defineProperty"),
    ("Reflect", "setPrototypeOf"),
];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// Each member patch of a free global in the file.
    pub(crate) fn member_patches(&self) -> Vec<Patch> {
        let tree = self.tree;
        let mut found = Vec::new();
        for (owner, target) in &self.targets {
            let value = Tree::field(tree, *owner, F::Right).map(|v| Cx::unwrapped(&tree.cx, v));
            if value.is_some_and(|v| crate::script_types::LITERAL_KINDS.contains(&Node::kind(&v))) {
                continue;
            }
            if let Some((global, path)) = self.patched_member(*target) {
                let names = self.target_names(*target);
                Vec::push(
                    &mut found,
                    Patch {
                        global,
                        path,
                        target: names,
                        span: Tree::span(tree, *owner),
                    },
                );
            }
        }
        let calls = tree
            .nodes
            .iter()
            .copied()
            .filter(|node| Node::kind(node) == "call_expression");
        for node in calls {
            for (global, member) in self.reflective_patch(node) {
                Vec::push(
                    &mut found,
                    Patch {
                        global,
                        path: member.into_iter().collect(),
                        target: Vec::new(),
                        span: Tree::span(tree, node),
                    },
                );
            }
        }
        found
    }

    /// The line and column of each name of a write target (`Math`, `max`).
    fn target_names(&self, target: Node<'t>) -> Vec<(i64, i64)> {
        let tree = self.tree;
        let names = Tree::subtree(tree, target)
            .iter()
            .filter(|n| matches!(Node::kind(n), "identifier" | "property_identifier"));
        names
            .map(|n| {
                let at = Tree::span(tree, *n);
                (at.line, at.column)
            })
            .collect()
    }

    /// `G.m = v`, `G['m'] = v` or deeper, with `G` a free name that is no window name: `G` and
    /// the written path after it, up to the first key that is no literal.
    fn patched_member(&self, target: Node<'t>) -> Option<(String, Vec<String>)> {
        let tree = self.tree;
        let mut chain = vec![Cx::unwrapped(&tree.cx, target)];
        loop {
            let at = *chain.last()?;
            if !matches!(
                Node::kind(&at),
                "member_expression" | "subscript_expression"
            ) {
                break;
            }
            let object = Tree::field(tree, at, F::Object)?;
            Vec::push(&mut chain, Cx::unwrapped(&tree.cx, object));
        }
        let root = Vec::pop(&mut chain)?;
        let global = self.free_global(root)?;
        let path = chain
            .iter()
            .rev()
            .map(|access| self.patched_key(*access))
            .take_while(Option::is_some)
            .flatten()
            .collect();
        Some((global, path))
    }

    /// The name of a member access: its property, or a literal key.
    fn patched_key(&self, access: Node<'t>) -> Option<String> {
        let tree = self.tree;
        match Node::kind(&access) {
            "member_expression" => {
                Tree::field(tree, access, F::Property).map(|p| Tree::text(tree, p))
            }
            _ => Tree::field(tree, access, F::Index).and_then(|i| self.text_of(i)),
        }
    }

    /// A free name of a global that is no window name (a window write is AD-460).
    fn free_global(&self, node: Node<'t>) -> Option<String> {
        let tree = self.tree;
        let name = Tree::text(tree, node);
        let free = Node::kind(&node) == "identifier"
            && !is_root(&name)
            && !crate::source_input::is_window_name(&name)
            && bound_scope(tree, node, &name).is_none()
            && !Tree::in_type(tree, node);
        free.then_some(name)
    }

    /// A reflective write whose target is a free global: `Object.assign(Math, …)` and the other
    /// members of `REFLECTIVE`, or `G.__defineGetter__(…)`: the global and each member it writes.
    fn reflective_patch(&self, call: Node<'t>) -> Vec<(String, Option<String>)> {
        let tree = self.tree;
        let Some(callee) = Tree::field(tree, call, F::Function).map(|c| Cx::unwrapped(&tree.cx, c))
        else {
            return Vec::new();
        };
        let (Some(property), Some(object)) = (
            Tree::field(tree, callee, F::Property),
            Tree::field(tree, callee, F::Object).map(|o| Cx::unwrapped(&tree.cx, o)),
        ) else {
            return Vec::new();
        };
        let method = Tree::text(tree, property);
        let argument = |at: usize| self.argument(call, at).map(|a| Cx::unwrapped(&tree.cx, a));
        let key = |at: usize| argument(at).and_then(|a| self.text_of(a));
        if matches!(
            String::as_str(&method),
            "__defineGetter__" | "__defineSetter__"
        ) {
            return self
                .free_global(object)
                .map(|global| (global, key(0)))
                .into_iter()
                .collect();
        }
        let reflective = self
            .free_global(object)
            .is_some_and(|owner| REFLECTIVE.iter().any(|(o, m)| *o == owner && *m == method));
        let Some(global) = argument(0)
            .filter(|_| reflective)
            .and_then(|a| self.free_global(a))
        else {
            return Vec::new();
        };
        let members = match String::as_str(&method) {
            "defineProperty" | "set" => vec![key(1)],
            "assign" | "defineProperties" => self.object_keys(argument(1)),
            _ => vec![None],
        };
        members.into_iter().map(|m| (global.clone(), m)).collect()
    }

    /// The plain keys of an object literal; one `None` for any other value or key.
    fn object_keys(&self, object: Option<Node<'t>>) -> Vec<Option<String>> {
        let tree = self.tree;
        let Some(object) = object.filter(|o| Node::kind(o) == "object") else {
            return vec![None];
        };
        crate::tree::nodes::named_children(object)
            .into_iter()
            .filter(|part| Node::kind(part) != "comment")
            .map(|part| match Node::kind(&part) {
                "shorthand_property_identifier" => Some(Tree::text(tree, part)),
                "pair" | "method_definition" => {
                    let key =
                        Tree::field(tree, part, F::Key).or(Tree::field(tree, part, F::Name))?;
                    match Node::kind(&key) {
                        "property_identifier" => Some(Tree::text(tree, key)),
                        _ => self.text_of(key),
                    }
                }
                _ => None,
            })
            .collect()
    }
}
