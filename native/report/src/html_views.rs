// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The three views of the architecture picture (AD-594). As-Is shows the observed dependencies,
//! Target shows the declared structure, Diff shows where the two differ. The picture is drawn
//! once: each mark names the views that show it, and the style sheet shows the marks of the
//! selected view. Each mark is a fact of the frame; the page decides nothing.

use std::collections::{BTreeMap, BTreeSet};

use super::cases::Names;
use super::frame::{Component, Frame};
use super::markup::{count, escape};
use super::places::{Kind, Places};

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum View {
    AsIs,
    Target,
    Diff,
}

impl View {
    pub(super) const ALL: [View; 3] = [View::AsIs, View::Target, View::Diff];

    /// The class of a mark that this view shows.
    pub(super) fn class(self) -> &'static str {
        ["rp-a", "rp-t", "rp-d"][self as usize]
    }

    fn label(self) -> &'static str {
        ["As-Is", "Target", "Diff"][self as usize]
    }
}

/// How a view shows a pair of components.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Mark {
    /// An observed dependency or a declared requirement, without an exception.
    Plain,
    /// A place of the pair breaks a rule.
    Fail,
    /// A gap holds the pair: a rule cannot decide it.
    Unknown,
    /// The contract declares the requirement and no observed import uses it.
    Unused,
}

/// A pair of two components of the contract with each fact that the frame states about it.
#[derive(Default)]
pub(super) struct Link<'a> {
    pub(super) from: &'a str,
    pub(super) to: &'a str,
    /// The observed imports between the two components. Zero when the scan observed none.
    pub(super) imports: usize,
    /// The observed imports that use the declared requirement, when the contract declares one.
    pub(super) declared: Option<usize>,
    /// The numbers of the violated places of the pair.
    pub(super) places: Vec<usize>,
    pub(super) held: bool,
}

impl Link<'_> {
    /// The mark of the pair in a view, or `None` when the view does not show the pair. In Diff an
    /// exception comes before information: a violation, then a gap, then an unused requirement.
    pub(super) fn mark(&self, view: View) -> Option<Mark> {
        let fail = !self.places.is_empty();
        match view {
            View::AsIs if self.imports == 0 => None,
            View::AsIs | View::Diff if fail => Some(Mark::Fail),
            View::AsIs => Some(Mark::Plain),
            View::Target => self.declared.map(|_| Mark::Plain),
            View::Diff if self.held => Some(Mark::Unknown),
            View::Diff if self.declared == Some(0) => Some(Mark::Unused),
            View::Diff => None,
        }
    }

    /// Each mark of the pair with the classes of the views that show it: one element for a mark.
    pub(super) fn marks(&self) -> Vec<(Mark, String)> {
        let mut marks: Vec<(Mark, String)> = Vec::new();
        for view in View::ALL {
            let Some(mark) = self.mark(view) else {
                continue;
            };
            match marks.iter_mut().find(|(found, _)| *found == mark) {
                Some((_, classes)) => *classes = format!("{classes} {}", view.class()),
                None => marks.push((mark, format!("rp-in {}", view.class()))),
            }
        }
        marks
    }

    /// What a mark of the pair says, as escaped text for a title.
    pub(super) fn title(&self, mark: Mark, names: &Names<'_>) -> String {
        let facts = match mark {
            Mark::Fail => count(self.places.len(), "violation"),
            Mark::Unknown => "a gap holds this pair".to_owned(),
            Mark::Unused => "declared, no observed import uses it".to_owned(),
            Mark::Plain if self.imports == 0 => "declared".to_owned(),
            Mark::Plain if self.declared.is_some() => {
                format!("{}, declared", count(self.imports, "import"))
            }
            Mark::Plain => count(self.imports, "import"),
        };
        format!("{}: {facts}", self.pair(names))
    }

    /// The names of the two components, escaped.
    pub(super) fn pair(&self, names: &Names<'_>) -> String {
        format!(
            "{} to {}",
            escape(names.name(self.from)),
            escape(names.name(self.to))
        )
    }
}

type Marks<'a> = BTreeMap<(&'a str, &'a str), Vec<usize>>;

/// The numbers of the places that break each pair of components, and the failing components.
fn violated<'a>(places: &Places, names: &Names<'a>) -> (Marks<'a>, BTreeSet<String>) {
    let mut marks: Marks<'a> = BTreeMap::new();
    let mut failing = BTreeSet::new();
    for place in &places.shown {
        match &place.kind {
            Kind::Import {
                source,
                target: Some(target),
                ..
            } => {
                if let (Some((from, _)), Some((to, _))) =
                    (names.component(source), names.component(target))
                {
                    marks.entry((from, to)).or_default().push(place.number);
                    failing.insert(from.to_owned());
                }
            }
            Kind::Import { source, .. } => {
                failing.extend(names.component(source).map(|(id, _)| id.to_owned()));
            }
            // A cycle puts each component on its path in the place.
            Kind::Cycle(cycle) => failing.extend(
                cycle
                    .path
                    .iter()
                    .flat_map(|step| [&step.from_component, &step.to_component])
                    .flatten()
                    .cloned(),
            ),
        }
    }
    (marks, failing)
}

/// Each pair of modules that a gap holds, with the rules that it holds: the pairs that
/// `explain.holds` names for a rule that is UNKNOWN.
pub(super) fn held_pairs(frame: &Frame) -> BTreeMap<(&str, &str), Vec<&str>> {
    let mut pairs: BTreeMap<(&str, &str), Vec<&str>> = BTreeMap::new();
    let holds = frame
        .rules
        .iter()
        .filter(|(_, row)| row.1 == "UNKNOWN")
        .filter_map(|(rule, _)| Some((rule.as_str(), frame.explain.holds.rules.get(rule)?)));
    for (rule, hold) in holds {
        for pair in &hold.pairs {
            let rules = pairs
                .entry((pair.source.as_str(), pair.target.as_str()))
                .or_default();
            rules.push(rule);
        }
    }
    pairs
}

/// The pairs of components that a gap holds.
fn held<'a>(frame: &'a Frame, names: &Names<'a>) -> BTreeSet<(&'a str, &'a str)> {
    held_pairs(frame)
        .into_keys()
        .filter_map(|(source, target)| {
            Some((names.component(source)?.0, names.component(target)?.0))
        })
        .collect()
}

/// The pairs of the picture in the order of their ids, and the failing components. A pair of a
/// component with itself, or with a name that is no component of the frame, is not drawn.
pub(super) fn links<'a>(
    frame: &'a Frame,
    places: &Places,
    names: &Names<'a>,
) -> (Vec<Link<'a>>, BTreeSet<String>) {
    let Some(topology) = frame.topology.as_ref() else {
        return (Vec::new(), BTreeSet::new());
    };
    let known: BTreeSet<&str> = topology.components.iter().map(|c| c.id.as_str()).collect();
    let mut found: BTreeMap<(&str, &str), Link<'a>> = BTreeMap::new();
    let mut note = |from: &'a str, to: &'a str, write: &dyn Fn(&mut Link<'a>)| {
        if from != to && known.contains(from) && known.contains(to) {
            write(found.entry((from, to)).or_insert_with(|| Link {
                from,
                to,
                ..Link::default()
            }));
        }
    };
    for edge in &topology.component_edges {
        if edge.resolution == "resolved" {
            note(&edge.source, &edge.target, &|link| {
                link.imports += edge.count;
            });
        }
    }
    for require in &topology.requires {
        note(&require.source, &require.target, &|link| {
            link.declared = Some(require.imports);
        });
    }
    let (marks, failing) = violated(places, names);
    for ((from, to), numbers) in &marks {
        note(from, to, &|link| link.places.clone_from(numbers));
    }
    for (from, to) in held(frame, names) {
        note(from, to, &|link| link.held = true);
    }
    (found.into_values().collect(), failing)
}

/// What the contract declares for a component: its layer and the size of its public surface.
pub(super) fn declared_note(component: &Component) -> String {
    let layer = component.layer.as_deref().map(escape);
    let public =
        (!component.public.is_empty()).then(|| format!("{} public", component.public.len()));
    layer
        .into_iter()
        .chain(public)
        .collect::<Vec<_>>()
        .join(" &#183; ")
}

/// The three radio inputs and their labels. The inputs come before the picture, so the style
/// sheet reads the selected view from them: the page needs no script for the views.
pub(super) fn switch() -> String {
    let mut inputs = String::new();
    let mut labels = String::new();
    for view in View::ALL {
        let id = format!("rp-view-{}", &view.class()[3..]);
        inputs.push_str(&format!(
            "<input class=\"rp-vh\" type=\"radio\" name=\"rp-view\" id=\"{id}\"{}>",
            if view == View::AsIs { " checked" } else { "" }
        ));
        labels.push_str(&format!(
            "<label class=\"ak-seg__btn ui\" for=\"{id}\">{}</label>",
            view.label()
        ));
    }
    format!("{inputs}<div class=\"ak-seg rp-tabs\">{labels}</div>")
}

const MAX_LAYER_ORDERS: usize = 5;

/// One sentence for each view: what the view shows, with the numbers of the frame.
pub(super) fn ledes(frame: &Frame, links: &[Link<'_>], places: &Places) -> String {
    let Some(topology) = frame.topology.as_ref() else {
        return String::new();
    };
    let declared = links.iter().filter(|l| l.declared.is_some()).count();
    let layered = topology.components.iter().filter(|c| c.layer.is_some());
    let public = topology.components.iter().filter(|c| !c.public.is_empty());
    let target = if declared + topology.layers.len() == 0
        && layered.clone().count() + public.clone().count() == 0
    {
        "the contract declares no requirement, layer or public surface.".to_owned()
    } else {
        format!(
            "what the contract declares. {}, {} with a layer, {} with a public surface.",
            count(declared, "requirement"),
            count(layered.count(), "component"),
            public.count()
        )
    };
    let unused = links
        .iter()
        .filter(|l| l.mark(View::Diff) == Some(Mark::Unused))
        .count();
    let mut html = format!(
        "<p class=\"caption rp-note rp-in rp-a\"><b>As-Is:</b> the observed dependencies.</p>\
<p class=\"caption rp-note rp-in rp-t\"><b>Target:</b> {target}</p>\
<p class=\"caption rp-note rp-in rp-d\"><b>Diff:</b> {}, {} of modules that a gap holds, {} without an observed import.</p>",
        count(places.total, "violated place"),
        count(held_pairs(frame).len(), "pair"),
        count(unused, "requirement")
    );
    for order in topology.layers.iter().take(MAX_LAYER_ORDERS) {
        html.push_str(&format!(
            "<p class=\"caption rp-note rp-in rp-t\">Layers of <b class=\"rp-code\">{}</b>, inner to outer: {}.</p>",
            escape(&order.rule),
            escape(&order.layers.join(", "))
        ));
    }
    if topology.layers.len() > MAX_LAYER_ORDERS {
        html.push_str(&format!(
            "<p class=\"caption rp-note rp-in rp-t\">The page shows {MAX_LAYER_ORDERS} of {} layer orders.</p>",
            topology.layers.len()
        ));
    }
    html
}

/// How to read the picture in each view; it sits with the picture that it explains.
pub(super) const LEGEND: &str = "<p class=\"caption rp-note rp-in rp-a\">A dashed red arrow or a red cell breaks a rule; its number links to the block.</p>\
<p class=\"caption rp-note rp-in rp-t\">An arrow or a marked cell is a declared requirement. A forbidden pair is in the rules list.</p>\
<p class=\"caption rp-note rp-in rp-d\">Dashed red: breaks a rule. Dotted, or a question mark: a gap holds the pair. \
Grey dotted, or a ring: declared and not used, for information only.</p>";
