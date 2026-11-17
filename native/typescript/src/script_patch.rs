// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The member patches of a global in a scanned file (#1674, AD-788 amendment): `Math.max = f`,
//! `JSON['parse'] = f`, `Object.assign(Math, …)`, `Object.defineProperty(JSON, 'parse', …)`,
//! `console.__defineGetter__('log', …)`. After such a write a call of the member runs the value,
//! which can be a function of another module, so the write withholds the native proof of the
//! global. A literal value can be no function, so a write of a literal patches nothing a call can
//! reach.

use tree_sitter::Node;

use crate::kinds::F;
use crate::script_names::bound_scope;
use crate::script_scope::is_root;
use crate::script_syntax::Producer;
use crate::script_types::Write;

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

/// The kinds of a literal value: it is no function.
const LITERALS: [&str; 7] = [
    "string",
    "number",
    "true",
    "false",
    "null",
    "undefined",
    "template_string",
];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// Each member patch of a free global in the file: the global and the place of the write.
    pub(crate) fn member_patches(&self) -> Vec<Write> {
        let tree = self.tree;
        let mut found = Vec::new();
        for (owner, target) in &self.targets {
            let value = crate::script_tree::Tree::field(tree, *owner, F::Right)
                .map(|v| crate::tree::cx::Cx::unwrapped(&tree.cx, v));
            let literal = value.is_some_and(|v| LITERALS.contains(&Node::kind(&v)));
            if let Some(name) = self.patched_global(*target).filter(|_| !literal) {
                Vec::push(&mut found, (Some(name), tree.span(*owner)));
            }
        }
        let calls = tree
            .nodes
            .iter()
            .copied()
            .filter(|node| Node::kind(node) == "call_expression");
        for node in calls {
            if let Some(name) = self.reflective_patch(node) {
                Vec::push(&mut found, (Some(name), tree.span(node)));
            }
        }
        found
    }

    /// `G.m = v` or `G[k] = v` (also deeper) with `G` a free name that is no window name: `G`.
    fn patched_global(&self, target: Node<'t>) -> Option<String> {
        let tree = self.tree;
        let mut at = crate::tree::cx::Cx::unwrapped(&tree.cx, target);
        let mut depth = 0;
        while matches!(
            Node::kind(&at),
            "member_expression" | "subscript_expression"
        ) {
            let object = crate::script_tree::Tree::field(tree, at, F::Object)?;
            at = crate::tree::cx::Cx::unwrapped(&tree.cx, object);
            depth += 1;
        }
        (depth > 0).then(|| self.free_global(at)).flatten()
    }

    /// A free name of a global that is no window name (a window write is AD-460).
    fn free_global(&self, node: Node<'t>) -> Option<String> {
        let tree = self.tree;
        let name = crate::script_tree::Tree::text(tree, node);
        let free = Node::kind(&node) == "identifier"
            && !is_root(&name)
            && !crate::source_input::is_window_name(&name)
            && bound_scope(tree, node, &name).is_none()
            && !tree.in_type(node);
        free.then_some(name)
    }

    /// A reflective write whose target is a free global: `Object.assign(Math, …)` and the other
    /// members of `REFLECTIVE`, or `G.__defineGetter__(…)`.
    fn reflective_patch(&self, call: Node<'t>) -> Option<String> {
        let tree = self.tree;
        let callee = crate::tree::cx::Cx::unwrapped(
            &tree.cx,
            crate::script_tree::Tree::field(tree, call, F::Function)?,
        );
        let property = crate::script_tree::Tree::field(tree, callee, F::Property)?;
        let method = crate::script_tree::Tree::text(tree, property);
        let object = crate::tree::cx::Cx::unwrapped(
            &tree.cx,
            crate::script_tree::Tree::field(tree, callee, F::Object)?,
        );
        if matches!(
            String::as_str(&method),
            "__defineGetter__" | "__defineSetter__"
        ) {
            return self.free_global(object);
        }
        let owner = self.free_global(object)?;
        let reflective = REFLECTIVE.iter().any(|(o, m)| *o == owner && *m == method);
        let first = self.argument(call, 0)?;
        reflective
            .then(|| self.free_global(crate::tree::cx::Cx::unwrapped(&tree.cx, first)))
            .flatten()
    }
}
