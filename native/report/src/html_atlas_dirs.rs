// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Directory boxes of the Explorer (issue 1488, AD-794): a component with no parts and more modules
//! than one screen shows (`ON_SCREEN`) gets one box for each directory of its modules. A directory
//! that is still too large gets one box inside it for each file prefix that two or more of its
//! files share (`lazy_binds.rs`, `lazy_cover.rs`). The structure decides; sorted names are never
//! cut into ranges. The module keeps its owner in the contract; a box only places it on the map.

use std::collections::BTreeMap;

use super::atlas_node::{Node, ON_SCREEN};
use super::frame::Topology;

/// A box to make: its label, the box that holds it (an index into the same list), and the names
/// of the modules that it places directly.
struct Planned<'a> {
    label: String,
    inside: Option<usize>,
    members: Vec<&'a str>,
}

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
        let planned = boxes(&modules);
        let mut made: Vec<usize> = Vec::new();
        for item in &planned {
            let parent = item.inside.map_or(owner, |i| made[i]);
            let count = members_under(&planned, made.len());
            let at = nodes.len();
            nodes.push(directory(
                nodes,
                owner,
                parent,
                &item.label,
                count,
                modules.len(),
            ));
            made.push(at);
            for name in &item.members {
                place.insert((*name).to_owned(), at);
            }
        }
    }
    place
}

/// The number of modules in a planned box and in the boxes inside it.
fn members_under(planned: &[Planned<'_>], at: usize) -> usize {
    planned[at].members.len()
        + (0..planned.len())
            .filter(|i| planned[*i].inside == Some(at))
            .map(|i| members_under(planned, i))
            .sum::<usize>()
}

/// The boxes of one component: a box for each directory with two or more modules, and inside a
/// directory with more than `ON_SCREEN` modules a box for each file prefix of two or more files. A
/// component whose modules all stand in one directory gets the prefix boxes without a directory
/// box. A module that shares no directory or prefix stays where it is.
fn boxes<'a>(modules: &[(&'a str, &'a str)]) -> Vec<Planned<'a>> {
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
    let single = by_directory.len() == 1;
    let mut boxed: Vec<(String, usize)> = Vec::new();
    let mut alone: Vec<(String, &'a str)> = Vec::new();
    for (dir, files) in by_directory {
        if files.len() < 2 {
            alone.extend(files.iter().map(|(_, name)| (dir.clone(), *name)));
            continue;
        }
        let relative = dir.strip_prefix(&common).unwrap_or(&dir).trim_matches('/');
        let base = common.rsplit('/').next().unwrap_or_default();
        let label = match (relative.is_empty(), base.is_empty()) {
            (true, true) => "./".to_owned(),
            (true, false) => format!("{base}/"),
            (false, _) => format!("{relative}/"),
        };
        let inside = if single {
            None
        } else {
            out.push(Planned {
                label: label.clone(),
                inside: None,
                members: Vec::new(),
            });
            Some(out.len() - 1)
        };
        // With one directory and no directory box, a module that no prefix box takes stays a box
        // of the component.
        let loose = prefixes(&mut out, inside, &label, &files, 1);
        if let Some(at) = inside {
            out[at].members = loose;
            boxed.push((dir, at));
        }
    }
    // A module alone in its directory goes into the box of the nearest directory above it.
    for (dir, name) in alone {
        let above = boxed
            .iter()
            .filter(|(d, _)| dir.starts_with(&format!("{d}/")))
            .max_by_key(|(d, _)| d.len());
        if let Some((_, at)) = above {
            out[*at].members.push(name);
        }
    }
    out
}

/// The prefix boxes of a directory with more than `ON_SCREEN` files; the modules that no box takes.
/// The prefix is the first `depth` parts of the file name at `_` (`lazy`, then `lazy_bind`): the
/// first depth from `from` on that gives two or more boxes of two or more files. A prefix box that
/// is still too large gets the boxes of the next depth inside it.
fn prefixes<'a>(
    out: &mut Vec<Planned<'a>>,
    inside: Option<usize>,
    label: &str,
    files: &[(&str, &'a str)],
    from: usize,
) -> Vec<&'a str> {
    let all: Vec<&'a str> = files.iter().map(|(_, name)| *name).collect();
    if files.len() <= ON_SCREEN {
        return all;
    }
    let key = |file: &str, depth: usize| {
        let stem = file.split('.').next().unwrap_or(file);
        stem.split('_').take(depth).collect::<Vec<_>>().join("_")
    };
    let split = (from..from + 4).find_map(|depth| {
        let mut by_prefix: BTreeMap<String, Vec<(&str, &'a str)>> = BTreeMap::new();
        for (file, name) in files {
            by_prefix
                .entry(key(file, depth))
                .or_default()
                .push((file, name));
        }
        (by_prefix.values().filter(|m| m.len() >= 2).count() >= 2).then_some((depth, by_prefix))
    });
    let Some((depth, by_prefix)) = split else {
        return all;
    };
    let mut loose = Vec::new();
    for (prefix, members) in by_prefix {
        if members.len() < 2 {
            loose.extend(members.iter().map(|(_, name)| *name));
            continue;
        }
        let joined = members
            .iter()
            .all(|(file, _)| file.starts_with(&format!("{prefix}_")));
        let star = if joined { "_*" } else { "*" };
        let name = if inside.is_some() {
            format!("{prefix}{star}")
        } else {
            format!("{label}{prefix}{star}")
        };
        out.push(Planned {
            label: name,
            inside,
            members: Vec::new(),
        });
        let at = out.len() - 1;
        out[at].members = prefixes(out, Some(at), label, &members, depth + 1);
    }
    loose
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

fn directory(
    nodes: &[Node],
    owner: usize,
    parent: usize,
    label: &str,
    count: usize,
    all: usize,
) -> Node {
    // An id names one box: a label that an earlier box of the owner has gets a mark.
    let scope = if parent == owner {
        nodes[owner].id.clone()
    } else {
        nodes[parent].id.clone()
    };
    let mut id = format!("FILES:{scope}:{label}");
    while nodes.iter().any(|n| n.id == id) {
        id.push('\'');
    }
    Node {
        id,
        label: label.to_owned(),
        parent: Some(parent),
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

    fn plan(rows: &[(String, String)]) -> Vec<(String, Option<usize>, usize)> {
        let modules: Vec<(&str, &str)> =
            rows.iter().map(|(n, p)| (n.as_str(), p.as_str())).collect();
        boxes(&modules)
            .into_iter()
            .map(|b| (b.label, b.inside, b.members.len()))
            .collect()
    }

    #[test]
    fn a_large_directory_is_split_by_file_prefix_and_never_by_ranges_of_names() {
        let mut rows: Vec<(String, String)> = Vec::new();
        for i in 0..20 {
            rows.push((format!("lazy{i}"), format!("src/survey/lazy_{i:02}.rs")));
            rows.push((
                format!("hazards{i}"),
                format!("src/survey/hazards_{i:02}.rs"),
            ));
        }
        rows.push(("mod".into(), "src/survey/mod.rs".into()));
        rows.push(("d1".into(), "src/survey/declared/a.rs".into()));
        rows.push(("d2".into(), "src/survey/declared/b.rs".into()));
        rows.push(("lone".into(), "src/survey/x/y.rs".into()));
        assert_eq!(
            plan(&rows),
            [
                // `mod.rs`, and `x/y.rs`, alone in its directory, in the box above it.
                ("survey/".to_owned(), None, 2),
                ("hazards_*".to_owned(), Some(0), 20),
                ("lazy_*".to_owned(), Some(0), 20),
                ("declared/".to_owned(), None, 2),
            ]
        );
    }

    #[test]
    fn a_prefix_that_every_file_shares_splits_at_the_next_part() {
        let mut rows: Vec<(String, String)> = Vec::new();
        for i in 0..20 {
            rows.push((format!("a{i}"), format!("t/beta/beta_agent_{i:02}.py")));
            rows.push((format!("s{i}"), format!("t/beta/beta_session_{i:02}.py")));
        }
        let found = plan(&rows);
        assert_eq!(
            found,
            [
                ("beta/beta_agent_*".to_owned(), None, 20),
                ("beta/beta_session_*".to_owned(), None, 20),
            ]
        );
    }

    #[test]
    fn files_with_no_shared_prefix_stay_one_box() {
        let rows: Vec<(String, String)> = (0..40)
            .map(|i| {
                (
                    format!("m{i}"),
                    format!("src/a/{}.rs", ["x", "y", "z"][i % 3].repeat(i + 1)),
                )
            })
            .collect();
        assert!(plan(&rows).is_empty());
    }
}
