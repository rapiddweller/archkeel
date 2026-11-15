// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The host-entry rule of the script globals (AD-540).
//!
//! An AMPLIFIER form says that a value may be the global object: a member `source` or `parent`, the
//! `this` of a function, a window name in a pattern. It writes an unknown global only when the
//! scan can get such a value. The scan has a HOST ENTRY when a file is not an ES module, or when a
//! file names a free value that the host gives (a free name that is not inert, and whose use is
//! not contained). A DIRECT form (a root name that is passed on, code from text, a `constructor`
//! that is used, a key that can name `constructor`) blocks in every scan.
//!
//! PREMISE, not a proof: code outside the scan hands in no global object, no platform object and
//! no function or text that makes one. A caller can give `set(window, 'Math', x)` to
//! `export function set(o, k, v) { o[k] = v }` and the collector does not see it.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_names::bound_scope;
use crate::script_scope::sole_binding_scope;
use crate::script_syntax::Producer;
use crate::script_window::cooked;

/// The value globals of the ECMAScript library that give no host object. A name that is not on
/// the list is a host entry until someone adds it. `globalThis`, `eval` and `Function` are not
/// on it: each of them is the global object, or runs text.
const INERT: &str = "\
    Object Array Math JSON Map Set WeakMap WeakSet Symbol Promise Number String Boolean \
    BigInt Date RegExp Error TypeError RangeError SyntaxError ReferenceError EvalError \
    URIError AggregateError parseInt parseFloat isNaN isFinite NaN Infinity undefined \
    encodeURI encodeURIComponent decodeURI decodeURIComponent ArrayBuffer \
    SharedArrayBuffer DataView Int8Array Uint8Array Uint8ClampedArray Int16Array \
    Uint16Array Int32Array Uint32Array Float32Array Float64Array BigInt64Array \
    BigUint64Array Proxy Reflect Intl WeakRef FinalizationRegistry Atomics escape \
    unescape Iterator";

/// The comparisons whose operand is only read.
const COMPARISONS: &str = "== != === !== < <= > >=";

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
fn listed(list: &str, name: &str) -> bool {
    list.split_whitespace().any(|word| word == name)
}

/// The depth that a chain of numeric names is followed.
const DEPTH: u8 = 4;

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The file gives the scan a host entry (conditions 1 and 3 of AD-540): it is no ES module,
    /// or it names a free value of the host.
    pub(crate) fn needs_host(&self) -> bool {
        let tree = self.tree;
        let commonjs = tree.nodes.iter().any(|node| commonjs(*node));
        !self.module_syntax || commonjs || tree.nodes.iter().any(|node| self.names_host(*node))
    }

    /// A free name that is no inert name and whose use is not contained.
    fn names_host(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        if !matches!(node.kind(), "identifier" | "shorthand_property_identifier") {
            return false;
        }
        let parameter = tree
            .parent(node)
            .is_some_and(|p| p.kind() == "formal_parameters");
        if tree.in_type(node) || tree.declaration_name(node) || parameter {
            return false;
        }
        let name = tree.text(node);
        if bound_scope(tree, node, &name).is_some() {
            return false;
        }
        let inert = cooked(&name).is_some_and(|name| listed(INERT, &name));
        !(inert || self.contained(node))
    }

    /// The name heads a chain of literal members, and the chain is only read: the operand of
    /// `typeof`, of `!` or of a comparison, the left side of `&&`, or a condition.
    fn contained(&self, head: Node<'t>) -> bool {
        let tree = self.tree;
        let mut chain = head;
        while let Some(parent) = tree.parent(chain) {
            let literal = match parent.kind() {
                "parenthesized_expression" => true,
                "member_expression" => tree.is_field_of_parent(chain, F::Object),
                "subscript_expression" => {
                    let index = tree.field(parent, F::Index);
                    tree.is_field_of_parent(chain, F::Object)
                        && index.is_some_and(|index| self.text_of(index).is_some())
                }
                _ => false,
            };
            if !literal {
                break;
            }
            chain = parent;
        }
        let Some(parent) = tree.parent(chain) else {
            return false;
        };
        let operator = tree.field(parent, F::Operator).map(|o| o.kind());
        match (parent.kind(), operator) {
            ("unary_expression", Some(operator)) => matches!(operator, "typeof" | "!"),
            ("binary_expression", Some("&&")) => tree.is_field_of_parent(chain, F::Left),
            ("binary_expression", Some(operator)) => listed(COMPARISONS, operator),
            ("if_statement", _) => true,
            ("ternary_expression", _) => crate::tree::nodes::named_children(parent)
                .first()
                .is_some_and(|test| test.id() == chain.id()),
            _ => false,
        }
    }

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

/// `export =` is CommonJS (`import x = require()` binds a name that the walk does not bind, so
/// each use of it is a free name). A `with` statement is a syntax error in a
/// module, so a file that has one is no module that the scan can read as one.
fn commonjs(node: Node) -> bool {
    match node.kind() {
        "with_statement" => true,
        "export_statement" => (0..node.child_count())
            .filter_map(|at| node.child(at))
            .any(|child| child.kind() == "="),
        _ => false,
    }
}

#[cfg(test)]
#[path = "script_host_tests.rs"]
mod tests;
