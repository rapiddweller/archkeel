// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The block of each violated place (AD-496): the path from the component to the file, the
//! relation with its line, the rules that fail there with their sides, and for a cycle the closed
//! path with the evidence of each step. A cut states both numbers.

use std::collections::BTreeMap;

use super::frame::{CyclePath, Frame, Module};
use super::markup::{count, escape, level_icon};
use super::places::{Kind, Place, Places, Violated};

/// The names of the modules and the components of the topology.
pub(super) struct Names<'a> {
    modules: BTreeMap<&'a str, &'a Module>,
    components: BTreeMap<&'a str, &'a str>,
}

impl<'a> Names<'a> {
    pub(super) fn of(frame: &'a Frame) -> Names<'a> {
        let topology = frame.topology.as_ref();
        Names {
            modules: topology
                .into_iter()
                .flat_map(|t| &t.modules)
                .map(|m| (m.name.as_str(), m))
                .collect(),
            components: topology
                .into_iter()
                .flat_map(|t| &t.components)
                .map(|c| (c.id.as_str(), c.name.as_str()))
                .collect(),
        }
    }

    /// The component id and name that own a module.
    pub(super) fn component(&self, module: &str) -> Option<(&'a str, &'a str)> {
        let id = self.modules.get(module)?.component.as_deref()?;
        Some((id, *self.components.get(id)?))
    }

    pub(super) fn file(&self, module: &str) -> Option<&'a str> {
        self.modules.get(module).map(|m| m.path.as_str())
    }

    /// Whether a name is a module of the topology.
    pub(super) fn is_module(&self, name: &str) -> bool {
        self.modules.contains_key(name)
    }

    /// The name of a component id, or the id.
    pub(super) fn name(&self, id: &'a str) -> &'a str {
        self.components.get(id).copied().unwrap_or(id)
    }
}

const ARROW: &str = "<svg width=\"56\" height=\"14\" viewBox=\"0 0 56 14\" aria-hidden=\"true\" \
style=\"color:var(--fail)\"><path class=\"rp-line rp-line--fail\" d=\"M1 7H47\"/>\
<path class=\"rp-fill\" d=\"M47 3L55 7L47 11z\"/></svg>";

fn row(level: &str, name: &str, link: Option<&str>) -> String {
    let name = match link {
        Some(anchor) => format!(
            "<a href=\"#{anchor}\"><span class=\"code rp-row__name\">{}</span></a>",
            escape(name)
        ),
        None => format!("<span class=\"code rp-row__name\">{}</span>", escape(name)),
    };
    format!(
        "<li class=\"rp-row\"><span class=\"rp-row__box\">{}<span class=\"tag\">{level}</span>{name}</span></li>",
        level_icon(level)
    )
}

/// The rows of one tower: the component, the module and the file, as far as the frame holds them.
fn tower(names: &Names<'_>, module: &str, file: Option<&str>, label: &str) -> (String, usize) {
    let mut rows = String::new();
    let mut levels = 0;
    if let Some((_, name)) = names.component(module) {
        // A component has no block to link to yet: its name is text (no link without a target).
        rows.push_str(&row("component", name, None));
        levels += 1;
    }
    rows.push_str(&row("module", module, None));
    levels += 1;
    if let Some(file) = file.or_else(|| names.file(module)) {
        rows.push_str(&row("file", file, None));
        levels += 1;
    }
    (
        format!("<ol class=\"rp-tower\" aria-label=\"{label}\">{rows}</ol>"),
        levels,
    )
}

/// The words of what a rule says about its two sides, from `explain.rules`.
fn sides(frame: &Frame, names: &Names<'_>, rule: &str) -> String {
    let Some(shape) = frame.explain.rules.get(rule) else {
        return String::new();
    };
    let list = |ids: &[String]| {
        let shown: Vec<&str> = ids.iter().take(4).map(|id| names.name(id)).collect();
        let more = ids.len().saturating_sub(shown.len());
        let tail = if more > 0 {
            format!(" and {more} more")
        } else {
            String::new()
        };
        format!("{}{tail}", shown.join(", "))
    };
    match (shape.direction.as_str(), shape.source.is_empty()) {
        // A cycle is between members of the rule; the sides would say "all components".
        ("none" | "acyclic", _) | (_, true) => String::new(),
        (direction @ ("forbids" | "allows"), false) => format!(
            " &#183; {direction}: {} to {}",
            escape(&list(&shape.source)),
            escape(&list(&shape.target))
        ),
        (direction, false) => format!(
            " &#183; {}: {}",
            escape(direction),
            escape(&list(&shape.source))
        ),
    }
}

/// The rules that fail at a place. A cycle rule is worded by the level of its members, as the
/// frame shows it: a module of the topology is a module cycle, else a component cycle.
fn violated(frame: &Frame, names: &Names<'_>, rules: &[Violated], level: Option<&str>) -> String {
    let mut list = String::from("<ul class=\"rp-rules\">");
    for found in rules {
        let kind = frame
            .rules
            .get(&found.rule)
            .map(|row| row.0.replace('_', " "))
            .unwrap_or_default();
        let kind = match level {
            Some(level) if kind == "no component cycles" => format!("no {level} cycles"),
            _ => kind,
        };
        list.push_str(&format!(
            "<li class=\"body-sm\">Violates <b class=\"rp-code\">{}</b> &#183; {} &#183; cause: {}{}</li>",
            escape(&found.rule),
            escape(&kind),
            escape(&found.cause),
            sides(frame, names, &found.rule)
        ));
    }
    list.push_str("</ul>");
    list
}

/// The places of some evidence ids as `file:line`, equal places once with their number.
fn counted(frame: &Frame, ids: &[String]) -> Vec<(String, usize)> {
    let mut found: Vec<(String, usize)> = Vec::new();
    for place in ids.iter().filter_map(|id| frame.place(id)) {
        match found.iter_mut().find(|(seen, _)| *seen == place) {
            Some((_, number)) => *number += 1,
            None => found.push((place, 1)),
        }
    }
    found
}

/// The places as markup: `file:line`, `x3` for a place that the evidence names three times, and
/// the number of places that the frame holds and the page leaves out.
fn places_text(frame: &Frame, ids: &[String], shown: usize, total: usize) -> String {
    let found = counted(frame, ids);
    let mut text = found
        .iter()
        .take(shown)
        .map(|(place, number)| {
            let times = if *number > 1 {
                format!(" &#215;{number}")
            } else {
                String::new()
            };
            format!("<span class=\"rp-code\">{}</span>{times}", escape(place))
        })
        .collect::<Vec<_>>()
        .join(", ");
    let more = total.saturating_sub(ids.len()) + found.len().saturating_sub(shown);
    if more > 0 {
        text.push_str(&format!(" <span class=\"rp-at\">and {more} more</span>"));
    }
    text
}

fn evidence_line(frame: &Frame, ids: &[String], shown: usize) -> String {
    places_text(frame, ids, shown, ids.len())
}

fn head(number: usize, title: &str) -> String {
    format!(
        "<div class=\"rp-dos__head\"><span class=\"rp-no\" aria-label=\"Violation {number}\">{number}</span>\
<h3 class=\"h3\">{}</h3></div>",
        escape(title)
    )
}

fn import_block(
    frame: &Frame,
    names: &Names<'_>,
    place: &Place,
    (source, target, evidence): (&str, Option<&str>, &[String]),
) -> String {
    let first = evidence.first().and_then(|id| frame.locations.get(id));
    let from_file = first.map(|at| at.path.as_str());
    let (from, mut levels) = tower(names, source, from_file, "From");
    let title = match target {
        Some(target) => format!("{source} imports {target}"),
        None => source.to_owned(),
    };
    let mut path = from;
    if let Some(target) = target {
        let (to, to_levels) = tower(names, target, None, "To");
        levels = levels.max(to_levels);
        let line = first.map_or_else(String::new, |at| format!("line {}", at.line));
        path.push_str(&format!(
            "<ul class=\"rp-rels\" aria-label=\"Relation\"><li class=\"rp-rel rp-r{levels} rp-rel--fail\">\
<span class=\"tag\">IMPORTS</span><span class=\"caption\">{line}</span>{ARROW}</li></ul>{to}"
        ));
    }
    format!(
        "<article class=\"rp-dos\" id=\"x{n}\">{}<div class=\"rp-dos__body\">\
<div class=\"rp-path rp-path--{levels}\" role=\"group\" aria-label=\"Evidence path\">{path}</div>\
<p class=\"caption rp-at\">Evidence: {}</p></div>{}</article>",
        head(place.number, &title),
        evidence_line(frame, evidence, 5),
        violated(frame, names, &place.rules, None),
        n = place.number
    )
}

/// A module as people read it: its file first, the long id only in the `title`.
fn file_cell(names: &Names<'_>, module: &str) -> String {
    let shown = names.file(module).unwrap_or(module);
    format!(
        "<span title=\"{}\">{}</span>",
        escape(module),
        escape(shown)
    )
}

fn step_row(frame: &Frame, names: &Names<'_>, index: usize, step: &super::frame::Step) -> String {
    let cited = places_text(frame, &step.evidence, 2, step.evidence_total);
    format!(
        "<tr><td class=\"code ak-num\">{}</td><td class=\"code\">{}</td><td class=\"code\">{}</td>\
<td class=\"caption\">{}</td></tr>",
        index + 1,
        file_cell(names, &step.from),
        file_cell(names, &step.to),
        cited
    )
}

/// The sentence that closes the path: the last step imports the start of the first step.
fn closing(names: &Names<'_>, cycle: &CyclePath) -> String {
    match (cycle.path.first(), cycle.path.last()) {
        (Some(_), Some(last)) if !cycle.truncated => format!(
            "Step {} imports {}, where step 1 starts.",
            cycle.path.len(),
            file_cell(names, &last.to)
        ),
        _ => String::new(),
    }
}

fn cycle_block(frame: &Frame, names: &Names<'_>, place: &Place, cycle: &CyclePath) -> String {
    let level = if cycle.members.iter().all(|m| names.is_module(m)) {
        "module"
    } else {
        "component"
    };
    let owners: std::collections::BTreeSet<&str> = cycle
        .path
        .iter()
        .flat_map(|step| [&step.from_component, &step.to_component])
        .flatten()
        .map(|id| names.name(id))
        .collect();
    let title = match owners.iter().collect::<Vec<_>>().as_slice() {
        [one] => format!("Cycle of {} in {one}", count(cycle.members.len(), "member")),
        _ => format!("Cycle of {}", count(cycle.members.len(), "member")),
    };
    let rows: String = cycle
        .path
        .iter()
        .enumerate()
        .map(|(index, step)| step_row(frame, names, index, step))
        .collect();
    let cut = if cycle.truncated || cycle.steps_total > cycle.path.len() {
        format!(
            "<p class=\"caption rp-note\">The path has {} steps; the page shows {}.</p>",
            cycle.steps_total,
            cycle.path.len()
        )
    } else {
        String::new()
    };
    format!(
        "<article class=\"rp-dos\" id=\"x{n}\">{}<div class=\"rp-dos__body\"><div class=\"rp-scroll\">\
<table class=\"rp-mini\"><caption class=\"caption\">{members} are in this cycle. Shortest closed path shown: {steps}. {closing}</caption><thead><tr><th class=\"caption ak-num\">Step</th><th class=\"caption\">From</th>\
<th class=\"caption\">To</th><th class=\"caption\">Imports</th></tr></thead><tbody>{rows}</tbody></table></div>\
{cut}</div>{}</article>",
        head(place.number, &title),
        violated(frame, names, &place.rules, Some(level)),
        n = place.number,
        members = count(cycle.members.len(), "member"),
        steps = count(cycle.path.len(), "step"),
        closing = closing(names, cycle)
    )
}

/// The section of the violated places, or nothing when no rule fails.
pub(super) fn section(frame: &Frame, places: &Places, names: &Names<'_>) -> String {
    if places.total == 0 {
        return String::new();
    }
    let rules = frame.rules_with("FAIL");
    let mut page = format!(
        "<section class=\"rp-sec\" aria-labelledby=\"violations\"><h2 class=\"h2\" id=\"violations\">Violations</h2>\
<p class=\"body-sm rp-lede\">{} in the code, {} broken. One block for each place; a place lists each rule that fails there.</p>",
        count(places.total, "place"),
        count(rules, "rule")
    );
    for place in &places.shown {
        let block = match &place.kind {
            Kind::Import {
                source,
                target,
                evidence,
            } => import_block(frame, names, place, (source, target.as_deref(), evidence)),
            Kind::Cycle(cycle) => cycle_block(frame, names, place, cycle),
        };
        if place.number <= OPEN_PLACES {
            page.push_str(&block);
        } else {
            // A place after the first ones is folded under its line. The id moves to the fold, so
            // a link to the place opens it.
            let id = format!("id=\"x{}\"", place.number);
            page.push_str(&format!(
                "<details class=\"rp-fold rp-place\" {id}><summary class=\"body-sm\"><span class=\"rp-no\">{}</span> {}</summary>{}</details>",
                place.number,
                escape(&one_line(names, place)),
                block.replacen(&format!(" {id}"), "", 1)
            ));
        }
    }
    for (rule, cycles) in &frame.explain.cycles {
        if cycles.total > cycles.items.len() {
            page.push_str(&format!(
                "<p class=\"caption rp-note\">The frame lists {} of {} cycles of <span class=\"rp-code\">{}</span>.</p>",
                cycles.items.len(),
                cycles.total,
                escape(rule)
            ));
        }
    }
    if places.total > places.shown.len() {
        page.push_str(&format!(
            "<p class=\"caption rp-note\">The page shows {} of {} places. Every row: \
<span class=\"rp-code\">archkeel report --output report.json --format json</span></p>",
            places.shown.len(),
            places.total
        ));
    }
    page.push_str("</section>\n");
    page
}

/// The violated places that show open; the others are folded under one line.
const OPEN_PLACES: usize = 2;

/// A place as one line of text, for the list of the exceptions.
pub(super) fn one_line(names: &Names<'_>, place: &Place) -> String {
    match &place.kind {
        Kind::Cycle(cycle) => {
            let mut owners = cycle
                .path
                .iter()
                .flat_map(|step| [&step.from_component, &step.to_component])
                .flatten()
                .map(|id| names.name(id))
                .collect::<Vec<_>>();
            owners.sort_unstable();
            owners.dedup();
            let level = if cycle.members.iter().all(|m| names.is_module(m)) {
                "modules"
            } else {
                "components"
            };
            match owners.as_slice() {
                [one] => format!("Cycle of {} {level} in {one}", cycle.members.len()),
                _ => format!("Cycle of {} {level}", cycle.members.len()),
            }
        }
        Kind::Import { source, target, .. } => {
            let file = |module: &str| names.file(module).unwrap_or(module).to_owned();
            match target {
                Some(target) => format!("{} imports {}", file(source), file(target)),
                None => file(source),
            }
        }
    }
}
