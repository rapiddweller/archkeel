// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Directory boxes of the Explorer (issue 1488): one screen shows about `ON_SCREEN` module boxes.
//! A component with no parts and more modules than that gets one box for each directory of its
//! modules, and a directory that is still too large is cut into ranges of sorted file names. The
//! module keeps its owner in the contract; the box only places it on the map.

use std::collections::BTreeMap;

use super::atlas_node::Node;
use super::frame::Topology;

/// The most module boxes of one level: a 1440 x 900 screen in full view holds 6 x 5 module boxes
/// at the readable zoom of 85 percent (a box of 200 x 144 with the spacing of the layout).
pub(super) const ON_SCREEN: usize = 30;

/// The directory boxes of each large component without parts, and the box of each module that
/// such a box holds.
pub(super) fn split(
    nodes: &mut Vec<Node>,
    topology: &Topology,
    index: &BTreeMap<&str, usize>,
) -> BTreeMap<String, usize> {
    let mut by_owner: BTreeMap<usize, Vec<(&str, &str)>> = BTreeMap::new();
    for module in &topology.modules {
        if let Some(owner) = module.component.as_deref().and_then(|c| index.get(c)) {
            by_owner
                .entry(*owner)
                .or_default()
                .push((module.name.as_str(), module.path.as_str()));
        }
    }
    let mut place = BTreeMap::new();
    for (owner, modules) in by_owner {
        let has_parts = nodes.iter().any(|n| n.parent == Some(owner));
        if has_parts || modules.len() <= ON_SCREEN {
            continue;
        }
        for (label, members) in boxes(&modules) {
            let at = nodes.len();
            nodes.push(directory(nodes, owner, &label, members.len(), modules.len()));
            for name in members {
                place.insert(name.to_owned(), at);
            }
        }
    }
    place
}

/// The label and the module names of each box: a directory with at least two modules, cut into
/// balanced ranges of sorted file names when it holds more than `ON_SCREEN`. A directory of one
/// module gets no box: the module stays a box of its component.
fn boxes<'a>(modules: &[(&'a str, &'a str)]) -> Vec<(String, Vec<&'a str>)> {
    let directory = |path: &str| path.rsplit_once('/').map_or("", |(d, _)| d).to_owned();
    let common = common_directory(modules.iter().map(|(_, p)| directory(p)));
    let mut by_directory: BTreeMap<String, Vec<(&str, &str)>> = BTreeMap::new();
    for (name, path) in modules {
        let file = path.rsplit('/').next().unwrap_or(path);
        by_directory
            .entry(directory(path))
            .or_default()
            .push((file, name));
    }
    let mut out = Vec::new();
    for (dir, mut files) in by_directory {
        if files.len() < 2 {
            continue;
        }
        let relative = dir.strip_prefix(&common).unwrap_or(&dir).trim_matches('/');
        let base = common.rsplit('/').next().unwrap_or_default();
        let label = match (relative.is_empty(), base.is_empty()) {
            (true, true) => "./".to_owned(),
            (true, false) => format!("{base}/"),
            (false, _) => format!("{relative}/"),
        };
        files.sort_unstable();
        let parts = files.len().div_ceil(ON_SCREEN);
        let (size, extra) = (files.len() / parts, files.len() % parts);
        let mut start = 0;
        for part in 0..parts {
            let chunk = &files[start..start + size + usize::from(part < extra)];
            start += chunk.len();
            let name = if parts == 1 {
                label.clone()
            } else {
                format!("{label} {} to {}", chunk[0].0, chunk[chunk.len() - 1].0)
            };
            out.push((name, chunk.iter().map(|(_, n)| *n).collect()));
        }
    }
    out
}

/// The longest directory that holds every directory of the list, cut at a `/`.
fn common_directory(mut dirs: impl Iterator<Item = String>) -> String {
    let Some(first) = dirs.next() else {
        return String::new();
    };
    let mut common: Vec<String> = first.split('/').map(str::to_owned).collect();
    for dir in dirs {
        let shared = common
            .iter()
            .zip(dir.split('/'))
            .take_while(|(a, b)| a.as_str() == *b)
            .count();
        common.truncate(shared);
    }
    common.join("/")
}

fn directory(nodes: &[Node], owner: usize, label: &str, count: usize, all: usize) -> Node {
    // An id names one box: a label that an earlier box of the owner has gets a mark.
    let mut id = format!("FILES:{}:{label}", nodes[owner].id);
    while nodes.iter().any(|n| n.id == id) {
        id.push('\'');
    }
    Node {
        id,
        label: label.to_owned(),
        parent: Some(owner),
        layer: None,
        public: Vec::new(),
        path: label.to_owned(),
        about: vec![format!(
            "{count} modules of {} in `{label}`: the component has {all} modules, more than one screen shows ({ON_SCREEN}).",
            nodes[owner].label
        )],
        forbidden: Vec::new(),
        planned: Vec::new(),
        provenance: Vec::new(),
        members: None,
        rank: None,
        directory: true,
    }
}

#[cfg(test)]
mod tests {
    use super::boxes;

    #[test]
    fn a_large_flat_directory_is_cut_into_ranges_and_a_lone_module_keeps_no_box() {
        let names: Vec<String> = (0..52).map(|i| format!("m{i:02}")).collect();
        let mut modules: Vec<(&str, String)> = names
            .iter()
            .map(|n| (n.as_str(), format!("src/survey/{n}.rs")))
            .collect();
        modules.push(("d1", "src/survey/declared/a.rs".into()));
        modules.push(("d2", "src/survey/declared/b.rs".into()));
        modules.push(("lone", "src/survey/x/y.rs".into()));
        let rows: Vec<(&str, &str)> = modules.iter().map(|(n, p)| (*n, p.as_str())).collect();
        let found = boxes(&rows);
        let labels: Vec<(&str, usize)> = found.iter().map(|(l, m)| (l.as_str(), m.len())).collect();
        assert_eq!(
            labels,
            [
                ("survey/ m00.rs to m25.rs", 26),
                ("survey/ m26.rs to m51.rs", 26),
                ("declared/", 2),
            ]
        );
    }
}
