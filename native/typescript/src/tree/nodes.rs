// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Generic reads of the children of a syntax tree node. A node with few children is read by index,
//! which costs no cursor.

use tree_sitter::Node;

/// A node with this many children or fewer is read by index, which costs no cursor.
const FEW_CHILDREN: usize = 12;

pub fn named_children(node: Node) -> Vec<Node> {
    if node.child_count() <= FEW_CHILDREN {
        return (0..node.child_count())
            .filter_map(|index| node.child(index))
            .filter(Node::is_named)
            .collect();
    }
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

/// Call `visit` for each child, without a vector: a node with few children is read by index.
pub fn each_child<'t>(node: Node<'t>, mut visit: impl FnMut(Node<'t>)) {
    if node.child_count() <= FEW_CHILDREN {
        (0..node.child_count())
            .filter_map(|index| node.child(index))
            .for_each(visit);
        return;
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        visit(child);
    }
}

pub fn children(node: Node) -> Vec<Node> {
    if node.child_count() <= FEW_CHILDREN {
        return (0..node.child_count())
            .filter_map(|index| node.child(index))
            .collect();
    }
    let mut cursor = node.walk();
    node.children(&mut cursor).collect()
}
