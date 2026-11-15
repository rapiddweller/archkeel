// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The keys that are numbers or symbols whatever the values of the file are (AD-540). Such a key
//! cannot name `constructor` or `parent`, so it is no run-time key. The proof is local: a number,
//! an arithmetic result, a well-known symbol, or a name that is bound once to such a value and
//! that each write keeps a number.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_names::bound_scope;
use crate::script_scope::sole_binding_scope;
use crate::script_syntax::Producer;

/// The operators whose result is a number whatever the operands are.
const ARITHMETIC: &str = "- * / % ** & | ^ << >> >>>";

/// The assignment operators that keep a number a number.
const ARITHMETIC_UPDATES: &str = "-= *= /= %= **= &= |= ^= <<= >>= >>>=";

/// The well-known symbols: a key of them is a symbol, never the text `constructor`.
const SYMBOLS: &str = "\
    asyncIterator iterator hasInstance toStringTag toPrimitive \
    species isConcatSpreadable match matchAll replace \
    search split unscopables dispose";

/// Whether `name` is one of the words of `list`.
pub(crate) fn listed(list: &str, name: &str) -> bool {
    list.split_whitespace().any(|word| word == name)
}

/// The depth that a chain of numeric names is followed.
const DEPTH: u8 = 4;

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The key is a number or a symbol whatever the values of the file are, so it cannot name a
    /// member such as `constructor` or `parent`: a number, an arithmetic result, a unary `-`, `+`
    /// or `~`, an update, a well-known symbol, or a name that is bound once to such a value and
    /// that each write keeps a number (`for (let i = 0; i < n; i++)`).
    pub(crate) fn numeric_key(&self, node: Node<'t>) -> bool {
        self.numeric_at(node, DEPTH)
    }

    fn numeric_at(&self, node: Node<'t>, depth: u8) -> bool {
        let tree = self.tree;
        let node = tree.cx.unwrapped(node);
        let operator = tree.field(node, F::Operator).map(|o| o.kind());
        match (node.kind(), operator) {
            ("number" | "update_expression", _) => true,
            ("unary_expression", Some(operator)) => matches!(operator, "-" | "+" | "~"),
            ("binary_expression", Some("+")) => {
                let operands = crate::tree::nodes::named_children(node);
                operands.len() == 2 && operands.iter().all(|at| self.numeric_at(*at, depth))
            }
            ("binary_expression", Some(operator)) => listed(ARITHMETIC, operator),
            ("identifier", _) => depth > 0 && self.numeric_name(node, depth - 1),
            ("member_expression", _) => self.well_known_symbol(node),
            _ => false,
        }
    }

    /// `Symbol.iterator` and the other well-known symbols, with `Symbol` the free name.
    fn well_known_symbol(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let object = tree.field(node, F::Object);
        let property = tree.field(node, F::Property).map(|p| tree.text(p));
        let symbol = object.is_some_and(|object| {
            object.kind() == "identifier"
                && tree.text(object) == "Symbol"
                && bound_scope(tree, object, "Symbol").is_none()
        });
        symbol && property.is_some_and(|name| listed(SYMBOLS, &name))
    }

    /// The name has one binding, a declarator with a numeric value, and no write changes that.
    fn numeric_name(&self, name: Node<'t>, depth: u8) -> bool {
        let tree = self.tree;
        let text = tree.text(name);
        let Some(scope) = sole_binding_scope(tree, name, &text) else {
            return false;
        };
        let key = (scope.id(), text);
        if let Some(known) = self.numeric.borrow().get(&key) {
            return *known;
        }
        let declared = self.index.declared.get(&key).map(Vec::as_slice);
        let found = match declared {
            Some([declaration]) => {
                let value = tree.field(*declaration, F::Value);
                tree.k(*declaration) == K::VariableDeclarator
                    && value.is_some_and(|value| self.numeric_at(value, depth))
                    && self
                        .targets
                        .iter()
                        .all(|(owner, target)| self.keeps_number(*owner, *target, &key, depth))
            }
            _ => false,
        };
        self.numeric.borrow_mut().insert(key, found);
        found
    }

    /// The write at `owner` does not change a number of the name `key` into another value.
    fn keeps_number(
        &self,
        owner: Node<'t>,
        target: Node<'t>,
        key: &(usize, String),
        depth: u8,
    ) -> bool {
        let tree = self.tree;
        let same = tree.text(target) == key.1
            && bound_scope(tree, target, &key.1).is_some_and(|scope| scope.id() == key.0);
        if !same {
            return true;
        }
        let operator = tree.field(owner, F::Operator).map(|o| o.kind());
        let right = tree.field(owner, F::Right);
        match (owner.kind(), operator) {
            ("update_expression", _) => true,
            ("augmented_assignment_expression", Some("+=")) | ("assignment_expression", _) => {
                right.is_some_and(|right| self.numeric_at(right, depth))
            }
            ("augmented_assignment_expression", Some(operator)) => {
                listed(ARITHMETIC_UPDATES, operator)
            }
            _ => false,
        }
    }
}
