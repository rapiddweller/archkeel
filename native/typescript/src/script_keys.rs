// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The readers of keys and arguments that the open-form check shares (AD-508).
//!
//! The run-time key call has no exemption for data that the file makes: a literal can carry an
//! event, take a prototype from a method that returns it, or be written from another file. Only a
//! plain namespace of the platform is exempt, because it holds no function that reaches `Function`.

use tree_sitter::Node;

use crate::kinds::F;
use crate::script_syntax::Producer;

/// The global objects that are no function and give no reflection (`Reflect` does): a computed
/// call on them reaches no `Function`.
const NAMESPACES: [&str; 5] = ["Math", "JSON", "Atomics", "Intl", "console"];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The text of a string literal or a template without a substitution.
    pub(crate) fn text_of(&self, node: Node<'t>) -> Option<String> {
        crate::script_window::string_text(self, node)
    }

    /// A free name of a platform namespace.
    pub(crate) fn namespace(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        let name = tree.text(object);
        object.kind() == "identifier"
            && tree.binding_scope(object, &name).is_none()
            && NAMESPACES.contains(&name.as_str())
    }

    /// The object of `o[k]` when the key is no literal and no number.
    pub(crate) fn runtime_object(&self, node: Node<'t>) -> Option<Node<'t>> {
        let tree = self.tree;
        let index = tree.field(node, F::Index);
        let literal = crate::references::literal(index, tree.cx.source).is_some();
        if literal || index.is_some_and(|i| i.kind() == "number") {
            return None;
        }
        tree.field(node, F::Object).map(|o| tree.cx.unwrapped(o))
    }

    /// The argument of a call at `at`, without the comments.
    pub(crate) fn argument(&self, call: Node<'t>, at: usize) -> Option<Node<'t>> {
        let arguments = self.tree.field(call, F::Arguments)?;
        let mut found = crate::tree::nodes::named_children(arguments)
            .into_iter()
            .filter(|argument| argument.kind() != "comment");
        found.nth(at)
    }
}
