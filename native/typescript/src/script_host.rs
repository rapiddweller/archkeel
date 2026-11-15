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

use crate::kinds::F;
use crate::script_names::bound_scope;
use crate::script_numeric::listed;
use crate::script_syntax::Producer;
use crate::script_window::{cooked, string_text};

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

/// The file gives the scan a host entry (conditions 1 and 3 of AD-540): it is no ES module, or it
/// names a free value of the host.
pub(crate) fn needs_host(producer: &Producer) -> bool {
    producer.needs_host_here()
}

/// The places of the free names whose use is only read (AD-576).
pub(crate) fn contained_reads(producer: &Producer) -> Vec<(i64, i64)> {
    let nodes = producer.tree.nodes.iter();
    nodes
        .flat_map(|node| producer.contained_read(*node))
        .collect()
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    fn needs_host_here(&self) -> bool {
        let tree = self.tree;
        let commonjs = tree.nodes.iter().any(|node| commonjs(*node));
        !self.module_syntax || commonjs || tree.nodes.iter().any(|node| self.names_host(*node))
    }

    /// The places that a site of a contained use starts at: the free name, and each member after
    /// it (a site of `globalThis.process` starts at the member, one of `a.b.c` at each name).
    fn contained_read(&self, node: Node<'t>) -> Vec<(i64, i64)> {
        let tree = self.tree;
        let free = matches!(node.kind(), "identifier" | "shorthand_property_identifier")
            && !tree.in_type(node)
            && !tree.declaration_name(node)
            && bound_scope(tree, node, &tree.text(node)).is_none();
        if !(free && node.kind() == "identifier" && self.contained(node)) {
            return Vec::new();
        }
        let place = |at: Node<'t>| (tree.span(at).line, tree.span(at).column);
        let mut places = vec![place(node)];
        let mut chain = node;
        while let Some(parent) = tree.parent(chain) {
            if tree.is_field_of_parent(chain, F::Object) {
                places.extend(tree.field(parent, F::Property).map(place));
            } else if parent.kind() != "parenthesized_expression" {
                break;
            }
            chain = parent;
        }
        places
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
                        && index.is_some_and(|index| string_text(self, index).is_some())
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
