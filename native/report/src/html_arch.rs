// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The architecture picture (AD-496): a component map when the run has at most 12 components and
//! at most 30 dependencies between them, the matrix above that. It draws `topology` and the
//! violated places; it decides nothing. The page decides only the form, from these two numbers.

use std::collections::{BTreeMap, BTreeSet};

use super::cases::Names;
use super::frame::{Frame, Topology};
use super::markup::{count, escape, status_icon};
use super::places::{Kind, Places};

const MAP_COMPONENTS: usize = 12;
const MAP_EDGES: usize = 30;
const NODE_W: usize = 160;
const NODE_H: usize = 80;
const COLUMN: usize = 220;
const ROW: usize = 110;
/// The space left of the first column, for the edges that return to it.
const LEFT: usize = 50;
const LANE: usize = 10;

/// A dependency between two components of the contract, with the places that break it.
struct Link<'a> {
    from: &'a str,
    to: &'a str,
    imports: usize,
    marks: Vec<usize>,
}

struct Picture<'a> {
    topology: &'a Topology,
    /// Component ids in drawing order: a component stands above what it depends on.
    order: Vec<&'a str>,
    rank: BTreeMap<&'a str, usize>,
    links: Vec<Link<'a>>,
    failing: BTreeSet<String>,
    modules: BTreeMap<&'a str, usize>,
}

/// The rank of each component: the longest path from a component that nothing depends on. An edge
/// that would close a cycle does not count, so a cycle still has a finite picture.
fn ranks<'a>(ids: &[&'a str], links: &[Link<'a>]) -> BTreeMap<&'a str, usize> {
    let mut rank: BTreeMap<&str, usize> = ids.iter().map(|id| (*id, 0)).collect();
    for _ in 0..ids.len() {
        let mut changed = false;
        for link in links.iter().filter(|link| link.from != link.to) {
            let next = rank[link.from] + 1;
            if next < ids.len() && next > rank[link.to] {
                rank.insert(link.to, next);
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }
    rank
}

type Marks<'a> = BTreeMap<(&'a str, &'a str), Vec<usize>>;

/// The numbers of the places that break each pair of components, and the failing components.
fn marks<'a>(places: &Places, names: &Names<'a>) -> (Marks<'a>, BTreeSet<String>) {
    let mut marks: BTreeMap<(&str, &str), Vec<usize>> = BTreeMap::new();
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

impl<'a> Picture<'a> {
    fn of(frame: &'a Frame, places: &Places, names: &Names<'a>) -> Option<Picture<'a>> {
        let topology = frame.topology.as_ref()?;
        let ids: Vec<&str> = topology.components.iter().map(|c| c.id.as_str()).collect();
        let known: BTreeSet<&str> = ids.iter().copied().collect();
        let (marks, failing) = marks(places, names);
        let mut links: Vec<Link<'a>> = topology
            .component_edges
            .iter()
            .filter(|edge| {
                edge.resolution == "resolved"
                    && known.contains(edge.source.as_str())
                    && known.contains(edge.target.as_str())
            })
            .map(|edge| Link {
                from: edge.source.as_str(),
                to: edge.target.as_str(),
                imports: edge.count,
                marks: marks
                    .get(&(edge.source.as_str(), edge.target.as_str()))
                    .cloned()
                    .unwrap_or_default(),
            })
            .collect();
        links.sort_by(|a, b| (a.from, a.to).cmp(&(b.from, b.to)));
        let rank = ranks(&ids, &links);
        let mut order = ids.clone();
        order.sort_by_key(|id| (rank[id], names.name(id).to_owned()));
        let mut modules: BTreeMap<&str, usize> = BTreeMap::new();
        for module in &topology.modules {
            if let Some(id) = module.component.as_deref() {
                *modules.entry(id).or_default() += 1;
            }
        }
        Some(Picture {
            topology,
            order,
            rank,
            links,
            failing,
            modules,
        })
    }

    /// The dependencies between two components: the ones that the picture shows.
    fn drawn(&self) -> usize {
        self.links
            .iter()
            .filter(|link| link.from != link.to)
            .count()
    }

    fn small(&self) -> bool {
        self.order.len() <= MAP_COMPONENTS && self.drawn() <= MAP_EDGES
    }

    /// The top left corner of a node.
    fn at(&self, positions: &BTreeMap<&str, (usize, usize)>, id: &str) -> (usize, usize) {
        positions.get(id).copied().unwrap_or((20, 20))
    }

    fn positions(&self, top: usize) -> (BTreeMap<&'a str, (usize, usize)>, usize, usize) {
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
    fn route(
        &self,
        link: &Link<'a>,
        positions: &BTreeMap<&str, (usize, usize)>,
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
        (path, (x1 + x2) / 2, lane)
    }

    fn map(&self, names: &Names<'a>) -> String {
        let edges: Vec<&Link<'a>> = self.links.iter().filter(|l| l.from != l.to).collect();
        let top = edges.iter().filter(|l| self.lane(l) == Some(true)).count();
        let bottom = edges.iter().filter(|l| self.lane(l) == Some(false)).count();
        let offset = if top > 0 { 20 + top * LANE } else { 20 };
        let (positions, width, content) = self.positions(offset);
        let height = content + if bottom > 0 { bottom * LANE + 10 } else { 0 };
        let mut svg = format!(
            "<svg class=\"ak-diagram rp-map\" viewBox=\"0 0 {width} {height}\" style=\"max-width:{width}px\" role=\"img\" \
aria-label=\"Component map: {}, {}.\"><defs>{}</defs>",
            count(self.order.len(), "component"),
            count(self.drawn(), "dependency"),
            ["ak-arrow", "ak-arrow-fail"]
                .iter()
                .map(|id| format!(
                    "<marker id=\"{id}\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" markerWidth=\"8\" markerHeight=\"8\" orient=\"auto\">\
<path class=\"ak-arrowhead{}\" d=\"M0 1L10 5L0 9z\"/></marker>",
                    if id.ends_with("fail") { " ak-arrowhead--fail" } else { "" }
                ))
                .collect::<String>()
        );
        let (mut above, mut below) = (0, 0);
        for link in edges {
            let (d, mx, my) = self.route(link, &positions, content, (&mut above, &mut below));
            let fail = !link.marks.is_empty();
            svg.push_str(&format!(
                "<path class=\"ak-edge{}\" d=\"{d}\" marker-end=\"url(#ak-arrow{})\"><title>{} imports {}: {}</title></path>",
                if fail { " ak-edge--violation" } else { "" },
                if fail { "-fail" } else { "" },
                escape(names.name(link.from)),
                escape(names.name(link.to)),
                count(link.imports, "import")
            ));
            if let Some(first) = link.marks.first() {
                svg.push_str(&format!(
                    "<a href=\"#x{first}\"><g class=\"rp-callout\"><circle cx=\"{mx}\" cy=\"{my}\" r=\"10\"/><text x=\"{mx}\" y=\"{}\">{first}</text></g></a>",
                    my + 4
                ));
            }
        }
        for id in &self.order {
            let (x, y) = self.at(&positions, id);
            let fail = self.failing.contains(*id);
            let modules = count(self.modules.get(id).copied().unwrap_or(0), "module");
            let name = escape(names.name(id));
            let tag = if fail {
                format!(
                    "<g class=\"ak-node__tag-fail\" transform=\"translate({},{})\">{}<text class=\"ak-node__tag tag\" x=\"20\" y=\"11\">FAIL</text></g>",
                    x + 16,
                    y + 50,
                    status_icon("FAIL").replace("<svg class=\"ak-icon\"", "<svg width=\"14\" height=\"14\" y=\"-1\" class=\"ak-icon ak-node__icon\"")
                )
            } else {
                String::new()
            };
            svg.push_str(&format!(
                "<g class=\"ak-node{}\"><title>{name}{}</title><rect class=\"ak-node__box\" x=\"{x}\" y=\"{y}\" width=\"{NODE_W}\" height=\"{NODE_H}\" rx=\"8\"/>\
<text class=\"ak-node__title ui\" x=\"{}\" y=\"{}\">{name}</text><text class=\"ak-node__path code\" x=\"{}\" y=\"{}\">{modules}</text>{tag}</g>",
                if fail { " ak-node--fail" } else { "" },
                if fail { ": FAIL" } else { "" },
                x + 16,
                y + 26,
                x + 16,
                y + 44
            ));
        }
        svg.push_str("</svg>");
        svg
    }

    fn matrix(&self, names: &Names<'a>) -> String {
        let index: BTreeMap<&str, usize> = self
            .order
            .iter()
            .enumerate()
            .map(|(i, id)| (*id, i + 1))
            .collect();
        let cells: BTreeMap<(&str, &str), &Link<'_>> =
            self.links.iter().map(|l| ((l.from, l.to), l)).collect();
        let mut head = String::from("<th class=\"rp-mx__corner caption\" scope=\"col\">Component</th><th class=\"caption\" scope=\"col\">Modules</th>");
        for id in &self.order {
            head.push_str(&format!(
                "<th scope=\"col\" title=\"{}\">{}</th>",
                escape(names.name(id)),
                index[id]
            ));
        }
        let mut body = String::new();
        for from in &self.order {
            let state = if self.failing.contains(*from) {
                format!("<span class=\"rp-st ak-t-fail\" title=\"FAIL\">{}<span class=\"rp-vh\">FAIL</span></span>", status_icon("FAIL"))
            } else {
                String::new()
            };
            body.push_str(&format!(
                "<tr><th scope=\"row\"><span class=\"rp-p\">{}</span> {}{state}</th><td class=\"rp-n\">{}</td>",
                index[from],
                escape(names.name(from)),
                self.modules.get(from).copied().unwrap_or(0)
            ));
            for to in &self.order {
                let (from_name, to_name) = (escape(names.name(from)), escape(names.name(to)));
                body.push_str(&match cells.get(&(*from, *to)) {
                    _ if from == to => "<td class=\"rp-self\"></td>".to_owned(),
                    Some(link) if !link.marks.is_empty() => format!(
                        "<td class=\"rp-v\"><a href=\"#x{}\" title=\"{from_name} to {to_name}: {}\">{}</a></td>",
                        link.marks[0],
                        count(link.marks.len(), "violation"),
                        link.marks.len()
                    ),
                    Some(link) => format!(
                        "<td class=\"rp-o\" title=\"{from_name} to {to_name}: {}\"></td>",
                        count(link.imports, "import")
                    ),
                    None => "<td></td>".to_owned(),
                });
            }
            body.push_str("</tr>");
        }
        let cell = (840 / self.order.len().max(1)).clamp(10, 17);
        format!("<div class=\"rp-scroll\"><table class=\"rp-mx\" style=\"--c:{cell}px\"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")
    }
}

/// The section of the picture, or nothing when the frame has no topology.
pub(super) fn section(frame: &Frame, places: &Places, names: &Names<'_>) -> String {
    let Some(picture) = Picture::of(frame, places, names) else {
        return String::new();
    };
    let totals = &picture.topology.total;
    let drawn = if picture.small() {
        format!(
            "<div class=\"rp-map-only\"><div class=\"rp-pic__scroll\">{}</div></div><div class=\"rp-mx-only\">{}</div>",
            picture.map(names),
            picture.matrix(names)
        )
    } else {
        // A matrix of many components is a table to look up, not a picture: it is folded.
        format!(
            "<details class=\"rp-fold\"><summary class=\"caption\">Matrix of {}, {}: a row depends on the marked columns</summary>{}</details>",
            count(picture.order.len(), "component"),
            count(picture.drawn(), "dependency"),
            picture.matrix(names)
        )
    };
    let listed = picture.topology.component_edges.len();
    let cut = if totals.components > picture.order.len() || totals.component_edges > listed {
        format!(
            " The frame holds {} of {} components and {listed} of {} dependencies.",
            picture.order.len(),
            totals.components,
            totals.component_edges
        )
    } else {
        String::new()
    };
    format!(
        "<section class=\"rp-sec\" aria-labelledby=\"arch\"><h2 class=\"h2\" id=\"arch\">Architecture</h2>\
<p class=\"body-sm rp-lede\">{}, {}, {} between components. {} with a violation.{cut}</p>\
<figure class=\"rp-pic\">{drawn}<p class=\"caption rp-note\">Read a component: it depends on what its arrows or marked columns show. \
A dashed red arrow, or a red cell, is a place that breaks a rule; its number links to the block.</p></figure></section>\n",
        count(picture.order.len(), "component"),
        count(totals.modules, "module"),
        count(picture.drawn(), "dependency"),
        picture.failing.len()
    )
}
