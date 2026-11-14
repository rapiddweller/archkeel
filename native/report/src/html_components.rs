// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The drill-down from a component to its modules, their files and its imports (AD-498). It shows
//! what the topology of the frame holds and nothing below a file: the frame has no symbol. The page
//! keeps its size by rule: a component with a violation or a gap comes first, then the largest;
//! the first components have all tables, the next ones only their modules, and the rest one line.
//! Each cut states both numbers.

use std::collections::{BTreeMap, BTreeSet};

use super::cases::Names;
use super::frame::{Edge, Frame, Module, Topology};
use super::markup::{anchor, count, escape, level_icon, status_icon};
use super::places::{Kind, Places};

/// The components with all tables; the other components of an exception are one line.
const FULL: usize = 24;
/// The rows of one table.
const MAX_MODULES: usize = 25;
const MAX_TARGETS: usize = 12;
const MAX_GAPS: usize = 6;
const SHOWN_EVIDENCE: usize = 3;

const ARROW: &str = "<svg width=\"30\" height=\"14\" viewBox=\"0 0 30 14\" aria-hidden=\"true\">\
<path class=\"rp-line\" d=\"M1 7H21\"/><path class=\"rp-fill\" d=\"M21 3L29 7L21 11z\"/></svg>";

/// A component with what the page needs to rank and draw it.
struct Entry<'a> {
    id: &'a str,
    name: &'a str,
    modules: Vec<&'a Module>,
    /// The numbers of the violated places of each module of the component.
    marks: BTreeMap<&'a str, Vec<usize>>,
    gaps: Vec<(&'a str, &'a str)>,
    uses: usize,
    used_by: usize,
}

impl Entry<'_> {
    fn violations(&self) -> usize {
        // A place that touches several modules of the component is one violation.
        self.marks.values().flatten().collect::<BTreeSet<_>>().len()
    }

    /// The group of the component: 0 with a violation, 1 with a gap, 2 without an exception.
    fn group(&self) -> usize {
        match (self.violations(), self.gaps.len()) {
            (0, 0) => 2,
            (0, _) => 1,
            _ => 0,
        }
    }
}

/// Whether an edge between two components leaves (`out`) or enters the component.
fn leaves(edge: &Edge, id: &str, out: bool) -> bool {
    let end = if out { &edge.source } else { &edge.target };
    edge.source != edge.target && end == id
}

fn marks(places: &Places) -> BTreeMap<&str, Vec<usize>> {
    let mut found: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
    for place in &places.shown {
        match &place.kind {
            Kind::Import { source, .. } => found.entry(source).or_default().push(place.number),
            Kind::Cycle(cycle) => {
                let from: BTreeSet<&str> = cycle.path.iter().map(|s| s.from.as_str()).collect();
                for module in from {
                    found.entry(module).or_default().push(place.number);
                }
            }
        }
    }
    found
}

fn entries<'a>(frame: &'a Frame, places: &'a Places, names: &Names<'a>) -> Vec<Entry<'a>> {
    let Some(topology) = frame.topology.as_ref() else {
        return Vec::new();
    };
    let numbers = marks(places);
    let mut list: Vec<Entry<'a>> = topology
        .components
        .iter()
        .map(|component| {
            let modules: Vec<&Module> = topology
                .modules
                .iter()
                .filter(|m| m.component.as_deref() == Some(component.id.as_str()))
                .collect();
            let own: BTreeSet<&str> = modules.iter().map(|m| m.name.as_str()).collect();
            let gaps = frame
                .collection_gaps
                .iter()
                .filter_map(|gap| {
                    let subject = gap.subjects.iter().find(|s| own.contains(s.as_str()))?;
                    Some((subject.as_str(), gap.reason.as_str()))
                })
                .collect();
            let links = |out: bool| {
                topology
                    .component_edges
                    .iter()
                    .filter(|e| e.resolution == "resolved" && leaves(e, &component.id, out))
                    .count()
            };
            Entry {
                id: &component.id,
                name: names.name(&component.id),
                marks: modules
                    .iter()
                    .filter_map(|m| {
                        numbers
                            .get(m.name.as_str())
                            .map(|n| (m.name.as_str(), n.clone()))
                    })
                    .collect(),
                modules,
                gaps,
                uses: links(true),
                used_by: links(false),
            }
        })
        .collect();
    list.sort_by(|a, b| {
        (a.group(), b.modules.len(), a.name).cmp(&(b.group(), a.modules.len(), b.name))
    });
    list
}

fn badge(entry: &Entry<'_>) -> String {
    let (state, class, text) = match (entry.violations(), entry.gaps.len()) {
        (0, 0) => return String::new(),
        (0, gaps) => ("UNKNOWN", "unknown", count(gaps, "gap")),
        (violations, _) => ("FAIL", "fail", count(violations, "violation")),
    };
    format!(
        "<span class=\"ak-badge ak-badge--{class} tag\">{}{text}</span><span class=\"rp-vh\">{state}</span>",
        status_icon(state)
    )
}

fn summary(entry: &Entry<'_>) -> String {
    format!(
        "<span class=\"rp-kind\">{}<span class=\"rp-vh\">component</span><span class=\"rp-code\">{}</span></span>\
<span class=\"caption rp-comp__meta\">{} &#183; uses {} &#183; used by {}</span><span>{}</span>",
        level_icon("component"),
        escape(entry.name),
        count(entry.modules.len(), "module"),
        entry.uses,
        entry.used_by,
        badge(entry)
    )
}

fn modules_table(entry: &Entry<'_>) -> String {
    let mut modules: Vec<&&Module> = entry.modules.iter().collect();
    modules.sort_by_key(|m| (!entry.marks.contains_key(m.name.as_str()), m.name.as_str()));
    let rows: String = modules
        .iter()
        .take(MAX_MODULES)
        .map(|module| {
            let marks = entry.marks.get(module.name.as_str());
            let links: String = marks
                .into_iter()
                .flatten()
                .map(|n| format!("<a href=\"#x{n}\" class=\"rp-no\">{n}</a> "))
                .collect();
            format!(
                "<tr{}><td class=\"code\">{}</td><td class=\"code rp-at\">{}</td><td class=\"caption\">{links}</td></tr>",
                if marks.is_some() { " class=\"rp-mod--x\"" } else { "" },
                escape(&module.name),
                escape(&module.path)
            )
        })
        .collect();
    format!(
        "<div class=\"rp-scroll\"><table class=\"rp-mini\"><caption class=\"caption\">{} Modules: {} of {}</caption>\
<thead><tr><th class=\"caption\">Module</th><th class=\"caption\">{} File</th><th class=\"caption\">Exception</th></tr></thead>\
<tbody>{rows}</tbody></table></div>",
        level_icon("module"),
        entry.modules.len().min(MAX_MODULES),
        entry.modules.len(),
        level_icon("file")
    )
}

fn evidence(edge: &Edge) -> String {
    let shown: Vec<String> = edge
        .evidence
        .iter()
        .take(SHOWN_EVIDENCE)
        .map(|at| {
            format!(
                "<span class=\"rp-code\">{}</span>",
                escape(&format!("{}:{}", at.path, at.line))
            )
        })
        .collect();
    let more = edge.evidence_total.saturating_sub(shown.len());
    let tail = if more > 0 {
        format!(" <span class=\"rp-at\">and {more} more</span>")
    } else {
        String::new()
    };
    format!("{}{tail}", shown.join(", "))
}

/// The imports of a component to other components (`out`), or of other components to it.
fn imports_table(
    topology: &Topology,
    names: &Names<'_>,
    entry: &Entry<'_>,
    (out, linked): (bool, &BTreeSet<&str>),
) -> String {
    let edges: Vec<&Edge> = topology
        .component_edges
        .iter()
        .filter(|e| leaves(e, entry.id, out))
        .collect();
    if edges.is_empty() {
        return String::new();
    }
    let rows: String = edges
        .iter()
        .take(MAX_TARGETS)
        .map(|edge| {
            let other = if out { &edge.target } else { &edge.source };
            let label = if edge.resolution == "resolved" && linked.contains(other.as_str()) {
                format!("<a href=\"#{}\">{}</a>", anchor("c-", other), escape(names.name(other)))
            } else if edge.resolution == "resolved" {
                escape(names.name(other))
            } else {
                "<span class=\"rp-at\">outside the contract</span>".to_owned()
            };
            format!(
                "<tr><td class=\"body-sm\">{label}</td><td class=\"code ak-num\">{}</td><td class=\"caption\">{}</td></tr>",
                edge.count,
                evidence(edge)
            )
        })
        .collect();
    format!(
        "<div class=\"rp-scroll\"><table class=\"rp-mini\"><caption class=\"caption\">{ARROW} Imports {}: {} of {}</caption>\
<thead><tr><th class=\"caption\">{}</th><th class=\"caption ak-num\">Imports</th><th class=\"caption\">First evidence</th></tr></thead>\
<tbody>{rows}</tbody></table></div>",
        if out { "of other components" } else { "by other components" },
        edges.len().min(MAX_TARGETS),
        edges.len(),
        if out { "Target" } else { "Source" }
    )
}

fn gaps_table(entry: &Entry<'_>) -> String {
    if entry.gaps.is_empty() {
        return String::new();
    }
    let rows: String = entry
        .gaps
        .iter()
        .take(MAX_GAPS)
        .map(|(module, reason)| {
            format!(
                "<tr><td class=\"code\">{}</td><td class=\"body-sm\">{}</td></tr>",
                escape(module),
                escape(reason)
            )
        })
        .collect();
    format!(
        "<div class=\"rp-scroll\"><table class=\"rp-mini\"><caption class=\"caption\">Gaps: {} of {}</caption>\
<thead><tr><th class=\"caption\">Module</th><th class=\"caption\">Reason</th></tr></thead><tbody>{rows}</tbody></table></div>",
        entry.gaps.len().min(MAX_GAPS),
        entry.gaps.len()
    )
}

fn panel(
    topology: &Topology,
    names: &Names<'_>,
    entry: &Entry<'_>,
    (depth, linked): (usize, &BTreeSet<&str>),
) -> String {
    let id = anchor("c-", entry.id);
    if depth > FULL {
        return format!(
            "<div class=\"rp-comp rp-comp--line\" id=\"{id}\">{}</div>",
            summary(entry)
        );
    }
    let mut body = modules_table(entry);
    body.push_str(&gaps_table(entry));
    body.push_str(&imports_table(topology, names, entry, (true, linked)));
    body.push_str(&imports_table(topology, names, entry, (false, linked)));
    format!(
        "<details class=\"rp-comp\" id=\"{id}\"><summary>{}</summary><div class=\"rp-comp__body\">{body}</div></details>",
        summary(entry)
    )
}

/// A component with a violation or a gap, for the picture and for the links to its block.
pub(super) struct Exception {
    pub(super) id: String,
    pub(super) name: String,
    pub(super) violations: usize,
    pub(super) gaps: usize,
}

/// The components that have a block on the page, a violation first, then a gap, then the largest.
pub(super) fn exceptions(frame: &Frame, places: &Places, names: &Names<'_>) -> Vec<Exception> {
    entries(frame, places, names)
        .iter()
        .filter(|entry| entry.group() < 2)
        .map(|entry| Exception {
            id: entry.id.to_owned(),
            name: entry.name.to_owned(),
            violations: entry.violations(),
            gaps: entry.gaps.len(),
        })
        .collect()
}

/// The section of the components, or nothing when the frame has no topology.
pub(super) fn section(frame: &Frame, places: &Places, names: &Names<'_>) -> String {
    let Some(topology) = frame.topology.as_ref() else {
        return String::new();
    };
    let all = entries(frame, places, names);
    let list: Vec<&Entry<'_>> = all.iter().filter(|entry| entry.group() < 2).collect();
    if list.is_empty() {
        return String::new();
    }
    let mut html = "<section class=\"rp-sec\" aria-labelledby=\"components\"><h2 class=\"h2\" id=\"components\">Components with an exception</h2>\
<details class=\"rp-fold\"><summary class=\"caption\">Modules, files and imports of each component with an exception</summary>\
<p class=\"body-sm rp-lede\">Open a component for its modules and files, and for its imports with file and line. \
The frame holds no level below a file.</p>"
        .to_owned();
    html.push_str(&format!(
        "<p class=\"caption rp-note\">{} of {} have a violation or a gap. All tables for {}{}. \
The others are in the matrix. Every row: <span class=\"rp-code\">archkeel report --topology --output report.json --format json</span></p>",
        list.len(),
        count(all.len(), "component"),
        count(list.len().min(FULL), "component"),
        if list.len() > FULL {
            format!("; one line for {}", count(list.len() - FULL, "component"))
        } else {
            String::new()
        }
    ));
    let linked: BTreeSet<&str> = list.iter().map(|entry| entry.id).collect();
    let labels = ["WITH A VIOLATION", "WITH GAPS"];
    let mut group = usize::MAX;
    for (index, entry) in list.iter().enumerate() {
        if entry.group() != group {
            group = entry.group();
            let size = list.iter().filter(|e| e.group() == group).count();
            html.push_str(&format!(
                "<h3 class=\"caption rp-group\">{} &#183; {size}</h3>",
                labels[group.min(1)]
            ));
        }
        html.push_str(&panel(topology, names, entry, (index + 1, &linked)));
    }
    html.push_str("</details></section>\n");
    html
}
