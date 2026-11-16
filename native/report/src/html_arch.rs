// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The architecture picture (AD-496): a component map when the run has at most 12 components and
//! at most 30 pairs between them, the matrix above that. It draws `topology` and the violated
//! places in three views (AD-594); it decides nothing. The page decides only the form, from these
//! two numbers.

use std::collections::{BTreeMap, BTreeSet};

use super::cases::{one_line, Names};
use super::components;
use super::diff;
use super::frame::Frame;
use super::map::Picture;
use super::markup::{anchor, count, escape, status_icon};
use super::places::Places;
use super::views::{self, Link, Mark, LEGEND};

const MAP_COMPONENTS: usize = 12;
const MAP_EDGES: usize = 30;
/// The names of a public surface that a title lists.
const MAX_PUBLIC: usize = 8;

/// The rank of each component: the longest path from a component that nothing depends on. An edge
/// that would close a cycle does not count, so a cycle still has a finite picture.
fn ranks<'a>(ids: &[&'a str], links: &[Link<'a>]) -> BTreeMap<&'a str, usize> {
    let mut rank: BTreeMap<&str, usize> = ids.iter().map(|id| (*id, 0)).collect();
    for _ in 0..ids.len() {
        let mut changed = false;
        for link in links {
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

impl<'a> Picture<'a> {
    fn of(frame: &'a Frame, places: &Places, names: &Names<'a>) -> Option<Picture<'a>> {
        let topology = frame.topology.as_ref()?;
        let ids: Vec<&str> = topology.components.iter().map(|c| c.id.as_str()).collect();
        let (links, failing) = views::links(frame, places, names);
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
            linked: BTreeSet::new(),
            declared: topology
                .components
                .iter()
                .map(|c| (c.id.as_str(), c))
                .collect(),
        })
    }

    fn small(&self) -> bool {
        self.order.len() <= MAP_COMPONENTS && self.links.len() <= MAP_EDGES
    }

    /// The name of a component, a link to its block when it has one.
    fn label(&self, names: &Names<'a>, id: &str) -> String {
        let name = escape(names.name(id));
        if self.linked.contains(id) {
            format!("<a href=\"#{}\">{name}</a>", anchor("c-", id))
        } else {
            name
        }
    }

    /// The marks of one cell: one element for each mark of the pair.
    fn cell(link: &Link<'a>, names: &Names<'a>) -> String {
        let marks = link.marks().into_iter().map(|(mark, views)| {
            let title = link.title(mark, names);
            match mark {
                Mark::Plain => format!("<span class=\"rp-o {views}\" title=\"{title}\"></span>"),
                Mark::Unused => format!("<span class=\"rp-un {views}\" title=\"{title}\"></span>"),
                Mark::Fail => format!(
                    "<a class=\"rp-v {views}\" href=\"#x{}\" title=\"{title}\">{}</a>",
                    link.places[0],
                    link.places.len()
                ),
                Mark::Unknown => {
                    format!("<a class=\"rp-u {views}\" href=\"#unknown\" title=\"{title}\">?</a>")
                }
            }
        });
        format!("<td>{}</td>", marks.collect::<String>())
    }

    /// The columns of Target: the layer and the public surface, when the contract declares one.
    fn declared_cells(&self, id: &str, (layers, public): (bool, bool)) -> String {
        let row = self.declared.get(id);
        let mut cells = String::new();
        if layers {
            cells.push_str(&format!(
                "<td class=\"rp-n rp-in rp-t\">{}</td>",
                escape(row.and_then(|c| c.layer.as_deref()).unwrap_or(""))
            ));
        }
        if public {
            let names: &[String] = row.map_or(&[], |c| &c.public);
            let more = match names.len().saturating_sub(MAX_PUBLIC) {
                0 => String::new(),
                more => format!(" and {more} more"),
            };
            let shown: Vec<&str> = names.iter().take(MAX_PUBLIC).map(String::as_str).collect();
            cells.push_str(&format!(
                "<td class=\"rp-n rp-in rp-t\" title=\"{}{more}\">{}</td>",
                escape(&shown.join(", ")),
                names.len()
            ));
        }
        cells
    }

    fn matrix(&self, names: &Names<'a>) -> String {
        let index: BTreeMap<&str, usize> = self
            .order
            .iter()
            .enumerate()
            .map(|(i, id)| (*id, i + 1))
            .collect();
        let cells: BTreeMap<(&str, &str), &Link<'a>> =
            self.links.iter().map(|l| ((l.from, l.to), l)).collect();
        let rows = self.topology.components.iter();
        let columns = (
            rows.clone().any(|c| c.layer.is_some()),
            rows.clone().any(|c| !c.public.is_empty()),
        );
        let mut head = String::from("<th class=\"rp-mx__corner caption\" scope=\"col\">Component</th><th class=\"caption\" scope=\"col\">Modules</th>");
        for (shown, name) in [(columns.0, "Layer"), (columns.1, "Public")] {
            if shown {
                head.push_str(&format!(
                    "<th class=\"caption rp-in rp-t\" scope=\"col\">{name}</th>"
                ));
            }
        }
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
                format!("<span class=\"rp-st ak-t-fail rp-in rp-a rp-d\" title=\"FAIL\">{}<span class=\"rp-vh\">FAIL</span></span>", status_icon("FAIL"))
            } else {
                String::new()
            };
            body.push_str(&format!(
                "<tr><th scope=\"row\"><span class=\"rp-p\">{}</span> {}{state}</th><td class=\"rp-n\">{}</td>{}",
                index[from],
                self.label(names, from),
                self.modules.get(from).copied().unwrap_or(0),
                self.declared_cells(from, columns)
            ));
            for to in &self.order {
                body.push_str(&match cells.get(&(*from, *to)) {
                    _ if from == to => "<td class=\"rp-self\"></td>".to_owned(),
                    Some(link) => Self::cell(link, names),
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
    let Some(mut picture) = Picture::of(frame, places, names) else {
        return String::new();
    };
    let exceptions = components::exceptions(frame, places, names);
    picture.linked = exceptions.iter().map(|e| e.id.clone()).collect();
    let totals = &picture.topology.total;
    let differences = diff::differences(frame, &picture.links, places, names);
    let drawn = if picture.small() {
        format!(
            "<div class=\"rp-map-only\"><div class=\"rp-pic__scroll\">{}</div></div><div class=\"rp-mx-only\">{}</div>{differences}{LEGEND}",
            picture.component_map(names),
            picture.matrix(names)
        )
    } else {
        // Many components: the picture names the components with an exception and counts the
        // rest. The matrix is a table to look up, so it is folded.
        format!(
            "<div class=\"rp-in rp-a rp-d\">{}</div><div class=\"rp-in rp-a\">{}</div>{differences}<details class=\"rp-fold\"><summary class=\"caption\">Matrix of {}, {}: a row depends on the marked columns</summary>{}{LEGEND}</details>",
            tiles(&exceptions, picture.order.len()),
            exception_list(places, names),
            count(picture.order.len(), "component"),
            count(picture.observed(), "dependency"),
            picture.matrix(names)
        )
    };
    let (edges, requires) = (
        picture.topology.component_edges.len(),
        picture.topology.requires.len(),
    );
    let cut = if totals.components > picture.order.len()
        || totals.component_edges > edges
        || totals.requires > requires
    {
        format!(
            " The frame holds {} of {} components, {edges} of {} dependencies and {requires} of {} requirements.",
            picture.order.len(),
            totals.components,
            totals.component_edges,
            totals.requires
        )
    } else {
        String::new()
    };
    format!(
        "<section class=\"rp-sec\" aria-labelledby=\"arch\"><h2 class=\"h2\" id=\"arch\">Architecture</h2>\
<p class=\"body-sm rp-lede\">{}, {}, {} between components. {} with a violation.{cut}</p>\
<figure class=\"rp-pic\">{}{}{drawn}</figure></section>\n",
        count(picture.order.len(), "component"),
        count(totals.modules, "module"),
        count(picture.observed(), "dependency"),
        picture.failing.len(),
        views::switch(),
        views::ledes(frame, &picture.links, places)
    )
}

const MAX_TILES: usize = 8;

const MAX_LISTED: usize = 9;

/// The components with a violation or a gap, named; the others counted.
fn tiles(exceptions: &[components::Exception], all: usize) -> String {
    let tile = |e: &components::Exception| {
        let (class, icon, note) = if e.violations > 0 {
            ("fail", "FAIL", count(e.violations, "violation"))
        } else {
            ("unknown", "UNKNOWN", count(e.gaps, "gap"))
        };
        format!(
            "<li><a class=\"rp-tile rp-tile--{class}\" href=\"#{}\">{}{} &#183; {note}</a></li>",
            anchor("c-", &e.id),
            status_icon(icon),
            escape(&e.name)
        )
    };
    let shown: String = exceptions.iter().take(MAX_TILES).map(tile).collect();
    let (failing, gapped) = (
        exceptions.iter().filter(|e| e.violations > 0).count(),
        exceptions.iter().filter(|e| e.violations == 0).count(),
    );
    let more = exceptions.len().saturating_sub(MAX_TILES);
    let tail = if more > 0 {
        format!("<li class=\"rp-tile rp-tile--count\">+{more} more with an exception</li>")
    } else {
        String::new()
    };
    format!(
        "<ul class=\"rp-tiles\" aria-label=\"Components with an exception\">{shown}{tail}\
<li class=\"rp-tile rp-tile--count\">{failing} with a violation &#183; {gapped} with gaps &#183; {} without an exception</li></ul>",
        all.saturating_sub(exceptions.len())
    )
}

/// The violated places as one line each, so that the first screen names them.
fn exception_list(places: &Places, names: &Names<'_>) -> String {
    if places.total == 0 {
        return String::new();
    }
    let lines: String = places
        .shown
        .iter()
        .take(MAX_LISTED)
        .map(|place| {
            format!(
                "<li class=\"body-sm\"><a href=\"#x{n}\"><span class=\"rp-no\">{n}</span> {}</a></li>",
                escape(&one_line(names, place)),
                n = place.number
            )
        })
        .collect();
    let more = places.total.saturating_sub(MAX_LISTED);
    let tail = if more > 0 {
        format!("<li class=\"body-sm\"><a href=\"#violations\">+{more} more</a></li>")
    } else {
        String::new()
    };
    format!("<ol class=\"rp-ev\" aria-label=\"Violated places\">{lines}{tail}</ol>")
}
