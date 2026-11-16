// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The component map of the architecture picture (AD-496): the boxes and the arrows as one SVG.
//! Each pair has one path; a view shows the marks of the pair that name it (AD-594).

use std::collections::{BTreeMap, BTreeSet};

use super::cases::Names;
use super::frame::{Component, Topology};
use super::markup::{anchor, count, escape, status_icon};
use super::views::{declared_note, Link, Mark};

const NODE_W: usize = 160;
const NODE_H: usize = 80;
const COLUMN: usize = 220;
const ROW: usize = 110;
/// The space left of the first column, for the edges that return to it.
const LEFT: usize = 50;
const LANE: usize = 10;

type Positions<'a> = BTreeMap<&'a str, (usize, usize)>;

/// The facts of the picture, the same for the map and for the matrix.
pub(super) struct Picture<'a> {
    pub(super) topology: &'a Topology,
    /// Component ids in drawing order: a component stands above what it depends on.
    pub(super) order: Vec<&'a str>,
    pub(super) rank: BTreeMap<&'a str, usize>,
    /// The pairs of all views. The form and the place of a box are the same in each view.
    pub(super) links: Vec<Link<'a>>,
    pub(super) failing: BTreeSet<String>,
    pub(super) modules: BTreeMap<&'a str, usize>,
    /// The components that have a block on the page: only these names are links.
    pub(super) linked: BTreeSet<String>,
    /// The rows of the components, for what the contract declares about each.
    pub(super) declared: BTreeMap<&'a str, &'a Component>,
}

/// One row for each mark: the id of its arrowhead, the class of its path and the class of the
/// arrowhead.
const STYLES: [(Mark, &str, &str, &str); 4] = [
    (Mark::Plain, "ak-arrow", "", ""),
    (
        Mark::Fail,
        "ak-arrow-fail",
        " ak-edge--violation",
        " ak-arrowhead--fail",
    ),
    (
        Mark::Unknown,
        "rp-arrow-unknown",
        " rp-edge--unknown",
        " rp-arrowhead--unknown",
    ),
    (
        Mark::Unused,
        "rp-arrow-unused",
        " rp-edge--unused",
        " rp-arrowhead--unused",
    ),
];

/// The arrowheads of the map, one for each mark.
fn arrowheads() -> String {
    STYLES
        .iter()
        .map(|(_, id, _, class)| {
            format!(
                "<marker id=\"{id}\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" markerWidth=\"8\" markerHeight=\"8\" orient=\"auto\">\
<path class=\"ak-arrowhead{class}\" d=\"M0 1L10 5L0 9z\"/></marker>"
            )
        })
        .collect()
}

impl<'a> Picture<'a> {
    /// The observed dependencies between two components.
    pub(super) fn observed(&self) -> usize {
        self.links.iter().filter(|link| link.imports > 0).count()
    }

    /// The top left corner of a node.
    fn at(&self, positions: &Positions<'_>, id: &str) -> (usize, usize) {
        positions.get(id).copied().unwrap_or((20, 20))
    }

    fn positions(&self, top: usize) -> (Positions<'a>, usize, usize) {
        let mut column_count: BTreeMap<usize, usize> = BTreeMap::new();
        let mut positions = BTreeMap::new();
        for id in &self.order {
            let column = self.rank[id];
            let row = column_count.entry(column).or_default();
            positions.insert(*id, (LEFT + column * COLUMN, top + *row * ROW));
            *row += 1;
        }
        let columns = column_count.keys().next_back().map_or(1, |last| last + 1);
        let rows = column_count.values().copied().max().unwrap_or(1);
        (
            positions,
            LEFT + 20 + (columns - 1) * COLUMN + NODE_W,
            top + 20 + (rows - 1) * ROW + NODE_H,
        )
    }

    /// Whether an edge runs in a lane around the boxes: it spans more than one column or goes back.
    fn lane(&self, link: &Link<'a>) -> Option<bool> {
        let (from, to) = (self.rank[link.from], self.rank[link.to]);
        if to == from + 1 {
            None
        } else {
            Some(to > from)
        }
    }

    /// The path of an edge and the point where its mark sits. A lane edge leaves to the right, runs
    /// along a lane above or below all boxes and enters from the left: it crosses no box.
    /// A lane spans two columns or more, thus the moved mark stays on its lane.
    fn route(
        &self,
        link: &Link<'a>,
        positions: &Positions<'_>,
        content: usize,
        (above, below): (&mut usize, &mut usize),
    ) -> (String, usize, usize) {
        let (fx, fy) = self.at(positions, link.from);
        let (tx, ty) = self.at(positions, link.to);
        let (x1, y1, x2, y2) = (fx + NODE_W, fy + NODE_H / 2, tx, ty + NODE_H / 2);
        let Some(up) = self.lane(link) else {
            let curve = format!("M{x1} {y1}C{} {y1} {} {y2} {x2} {y2}", x1 + 40, x2 - 40);
            return (curve, (x1 + x2) / 2, (y1 + y2) / 2);
        };
        let used = if up { above } else { below };
        *used += 1;
        let lane = if up {
            10 + (*used - 1) * LANE
        } else {
            content + 10 + (*used - 1) * LANE
        };
        let gap = 12 + (*used % 4) * 8;
        let path = format!("M{x1} {y1}H{}V{lane}H{}V{y2}H{x2}", x1 + gap, x2 - gap);
        // Two lanes between the same columns have the same middle: each mark moves along its lane.
        (path, (x1 + x2) / 2 + ((*used - 1) % 4) * 24, lane)
    }

    /// The paths of one pair: one for each mark, on the same route.
    fn edge(
        &self,
        link: &Link<'a>,
        names: &Names<'a>,
        (d, mx, my): (String, usize, usize),
    ) -> String {
        let mut svg = String::new();
        for (mark, views) in link.marks() {
            let (arrow, class) = STYLES
                .iter()
                .find(|style| style.0 == mark)
                .map_or(("ak-arrow", ""), |style| (style.1, style.2));
            svg.push_str(&format!(
                "<path class=\"ak-edge{class} {views}\" d=\"{d}\" marker-end=\"url(#{arrow})\"><title>{}</title></path>",
                link.title(mark, names)
            ));
            let callout = match mark {
                Mark::Fail => Some((
                    format!("#x{}", link.places[0]),
                    link.places[0].to_string(),
                    "",
                )),
                Mark::Unknown => Some((
                    "#unknown".to_owned(),
                    "?".to_owned(),
                    " rp-callout--unknown",
                )),
                Mark::Plain | Mark::Unused => None,
            };
            if let Some((href, text, kind)) = callout {
                svg.push_str(&format!(
                    "<a class=\"{views}\" href=\"{href}\"><g class=\"rp-callout{kind}\"><circle cx=\"{mx}\" cy=\"{my}\" r=\"10\"/><text x=\"{mx}\" y=\"{}\">{text}</text></g></a>",
                    my + 4
                ));
            }
        }
        svg
    }

    /// One box. The tag of a violation shows in As-Is and in Diff; the declared layer and the
    /// public surface show in Target.
    fn node(&self, id: &'a str, names: &Names<'a>, (x, y): (usize, usize)) -> String {
        let fail = self.failing.contains(id);
        let modules = count(self.modules.get(id).copied().unwrap_or(0), "module");
        let name = escape(names.name(id));
        let mut tags = String::new();
        if fail {
            tags.push_str(&format!(
                "<g class=\"ak-node__tag-fail rp-in rp-a rp-d\" transform=\"translate({},{})\">{}<text class=\"ak-node__tag tag\" x=\"20\" y=\"11\">FAIL</text></g>",
                x + 16,
                y + 50,
                status_icon("FAIL").replace("<svg class=\"ak-icon\"", "<svg width=\"14\" height=\"14\" y=\"-1\" class=\"ak-icon ak-node__icon\"")
            ));
        }
        let declared = self
            .declared
            .get(id)
            .map(|c| declared_note(c))
            .unwrap_or_default();
        if !declared.is_empty() {
            tags.push_str(&format!(
                "<text class=\"ak-node__path code rp-in rp-t\" x=\"{}\" y=\"{}\">{declared}</text>",
                x + 16,
                y + 62
            ));
        }
        let node = format!(
            "<g class=\"ak-node{}\"><title>{name}{}</title><rect class=\"ak-node__box\" x=\"{x}\" y=\"{y}\" width=\"{NODE_W}\" height=\"{NODE_H}\" rx=\"8\"/>\
<text class=\"ak-node__title ui\" x=\"{}\" y=\"{}\">{name}</text><text class=\"ak-node__path code\" x=\"{}\" y=\"{}\">{modules}</text>{tags}</g>",
            if fail { " ak-node--fail" } else { "" },
            if fail { ": FAIL" } else { "" },
            x + 16,
            y + 26,
            x + 16,
            y + 44
        );
        if self.linked.contains(id) {
            format!("<a href=\"#{}\">{node}</a>", anchor("c-", id))
        } else {
            node
        }
    }

    pub(super) fn component_map(&self, names: &Names<'a>) -> String {
        let top = self
            .links
            .iter()
            .filter(|l| self.lane(l) == Some(true))
            .count();
        let bottom = self
            .links
            .iter()
            .filter(|l| self.lane(l) == Some(false))
            .count();
        let offset = if top > 0 { 20 + top * LANE } else { 20 };
        let (positions, width, content) = self.positions(offset);
        let height = content + if bottom > 0 { bottom * LANE + 10 } else { 0 };
        let mut svg = format!(
            "<svg class=\"ak-diagram rp-map\" viewBox=\"0 0 {width} {height}\" style=\"max-width:{width}px\" role=\"img\" \
aria-label=\"Component map: {}, {}.\"><defs>{}</defs>",
            count(self.order.len(), "component"),
            count(self.observed(), "dependency"),
            arrowheads()
        );
        let (mut above, mut below) = (0, 0);
        for link in &self.links {
            let route = self.route(link, &positions, content, (&mut above, &mut below));
            svg.push_str(&self.edge(link, names, route));
        }
        for id in &self.order {
            svg.push_str(&self.node(id, names, self.at(&positions, id)));
        }
        svg.push_str("</svg>");
        svg
    }
}
