// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the fact sheet of a box that groups components says (AD-710): a layer or a group has no
//! contract text of its own, so its sheet aggregates its members. It says plainly that the box
//! groups N components, lists each member with the first line of its own responsibility, and shows
//! the union of their public surfaces and of what they are not responsible for. Nothing is
//! written for a field that no member fills.

use std::collections::BTreeSet;

use super::atlas_node::Node;

/// A box that holds no contract text: a layer of a layer order, or a group of a large level.
fn groups_components(node: &Node) -> bool {
    node.rank.is_some() || node.id.starts_with("GROUP:")
}

/// The components under a box: its children, and for a child box its members in turn. A component
/// is a member whether or not it has parts of its own.
fn members(nodes: &[Node], at: usize) -> Vec<usize> {
    let mut found = Vec::new();
    for (i, node) in nodes.iter().enumerate() {
        if node.parent != Some(at) {
            continue;
        }
        if groups_components(node) {
            found.extend(members(nodes, i));
        } else {
            found.push(i);
        }
    }
    found
}

/// The first line of a text, cut at its first full stop.
fn first_line(text: &str) -> &str {
    text.split_once(". ")
        .map_or(text, |(head, _)| head)
        .trim_end_matches('.')
}

/// Write the sheet of each layer and group from its member components.
pub(super) fn aggregate(nodes: &mut [Node]) {
    for at in 0..nodes.len() {
        if !groups_components(&nodes[at]) {
            continue;
        }
        let found = members(nodes, at);
        let (mut public, mut forbidden) = (BTreeSet::new(), BTreeSet::new());
        let mut lines = Vec::new();
        for i in &found {
            let member = &nodes[*i];
            public.extend(member.public.iter().cloned());
            forbidden.extend(member.forbidden.iter().cloned());
            if let Some(first) = member.about.first() {
                lines.push(format!("{}: {}", member.label, first_line(first)));
            }
        }
        let count = found.len();
        // A box that holds one component is that component: it shows the facts of the contract
        // for it, not a generated line (the shell has components that are also layers).
        if let [only] = found[..] {
            let own = (
                nodes[only].about.clone(),
                nodes[only].forbidden.clone(),
                nodes[only].public.clone(),
                nodes[only].provenance.clone(),
                nodes[only].planned.clone(),
                nodes[only].path.clone(),
            );
            let node = &mut nodes[at];
            (
                node.about,
                node.forbidden,
                node.public,
                node.provenance,
                node.planned,
                node.path,
            ) = own;
            node.members = Some(1);
            continue;
        }
        let noun = if count == 1 {
            "component"
        } else {
            "components"
        };
        let intro = match nodes[at].rank {
            Some(_) => {
                let place = nodes[at]
                    .about
                    .first()
                    .and_then(|t| t.split_once(':'))
                    .map(|(h, _)| h);
                let place = place.map_or(String::new(), |p| format!(" ({})", p.to_lowercase()));
                format!(
                    "This box groups {count} {noun} of layer {}{place}.",
                    nodes[at].label
                )
            }
            None => {
                let why = nodes[at].about.first().cloned().unwrap_or_default();
                format!("{why} This box groups {count} {noun}.")
                    .trim()
                    .to_owned()
            }
        };
        let node = &mut nodes[at];
        node.about = std::iter::once(intro).chain(lines).collect();
        node.public = public.into_iter().collect();
        node.forbidden = forbidden.into_iter().collect();
        node.members = Some(count);
    }
}
