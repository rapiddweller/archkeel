// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The causes of the UNKNOWN rules (AD-498): the rules that one hold of `explain.holds` keeps open,
//! grouped, largest first. The page copies the hold of each rule; it decides nothing.

use std::collections::BTreeMap;

use super::frame::Frame;
use super::markup::count;
use crate::head::RuleVerdict;

/// The rules that one cause holds.
pub(super) struct Cause<'a> {
    pub(super) kind: &'a str,
    /// The reason of the core, as written, for a cause that has no typed form.
    pub(super) reason: &'a str,
    pub(super) rules: Vec<&'a str>,
    /// The number of gaps that hold each rule of the cause.
    pub(super) total: usize,
    pub(super) unnamed: usize,
    /// Named gaps of this cause that are no rule of the contract (for example a hygiene code).
    pub(super) named: usize,
    /// What each named gap of a hygiene family points at: the file, the path and the subject.
    pub(super) members: Vec<&'a str>,
    /// The pairs of modules that hold the rules of the cause.
    pub(super) pairs: Vec<(&'a str, &'a str)>,
}

/// The causes of the UNKNOWN rules of a frame, the cause with most rules first.
pub(super) fn grouped(frame: &Frame) -> Vec<Cause<'_>> {
    let mut causes: BTreeMap<(&str, String, usize), Cause<'_>> = BTreeMap::new();
    for (rule, _) in frame
        .rules
        .iter()
        .filter(|(_, row)| row.1 == RuleVerdict::Unknown)
    {
        let held = frame.explain.holds.rules.get(rule);
        let reason = frame.explained.get(rule).map_or("", String::as_str);
        let kind = held
            .map(|h| h.kind.as_str())
            .filter(|kind| !kind.is_empty())
            .unwrap_or("other");
        let total = held.map_or(0, |h| h.total);
        // A cause with no typed form is told apart by the text of the core.
        let text = if kind == "other" { reason } else { "" };
        let card = causes
            .entry((kind, text.to_owned(), total))
            .or_insert_with(|| Cause {
                kind,
                reason,
                rules: Vec::new(),
                total,
                unnamed: held.map_or(0, |h| h.unnamed_imports),
                named: 0,
                members: Vec::new(),
                pairs: Vec::new(),
            });
        card.rules.push(rule);
        for pair in held.into_iter().flat_map(|h| &h.pairs) {
            let key = (pair.source.as_str(), pair.target.as_str());
            if !card.pairs.contains(&key) {
                card.pairs.push(key);
            }
        }
    }
    // A named gap has no rule row; its reason is its cause, and equal reasons are one cause.
    // #1616: near-identical hygiene gaps are one cause with a list: the family is the code and the
    // message, the member is what each gap points at.
    for reason in frame.named.values() {
        let (family, member) = match hygiene(reason) {
            Some((code, member, message)) => (format!("{code}: {message}"), Some(member)),
            None => (reason.clone(), None),
        };
        let card = causes.entry(("named", family, 0)).or_insert_with(|| Cause {
            kind: "named",
            reason,
            rules: Vec::new(),
            total: 0,
            unnamed: 0,
            named: 0,
            members: Vec::new(),
            pairs: Vec::new(),
        });
        card.named += 1;
        card.members.extend(member);
    }
    let mut list: Vec<Cause<'_>> = causes.into_values().collect();
    list.sort_by(|a, b| (b.rules.len() + b.named, a.kind).cmp(&(a.rules.len() + a.named, b.kind)));
    list
}

/// A hygiene reason (`contract hygiene <code>: <member>: <message>`) as its code, its member and
/// its message, so that gaps that differ only in the member are one cause (#1616).
pub(super) fn hygiene(reason: &str) -> Option<(&str, &str, &str)> {
    let (code, rest) = reason.strip_prefix("contract hygiene ")?.split_once(": ")?;
    let (member, message) = rest.rsplit_once(": ")?;
    Some((code, member, message))
}

/// The words for what a family of hygiene gaps says, with its count.
fn hygiene_title(code: &str, members: usize) -> String {
    match code {
        "responsibility.missing" => format!(
            "{} no written responsibility",
            if members == 1 {
                "1 component has".to_owned()
            } else {
                format!("{members} components have")
            }
        ),
        "rationale.placeholder" => format!(
            "{} still a placeholder",
            if members == 1 {
                "1 rationale is".to_owned()
            } else {
                format!("{members} rationales are")
            }
        ),
        "decision.open" => format!(
            "{} still open in the contract",
            if members == 1 {
                "1 decision is".to_owned()
            } else {
                format!("{members} decisions are")
            }
        ),
        _ => format!("{} of the kind {code}", count(members, "contract problem")),
    }
}

/// The id of the card of a cause on the page (#1764): the kind and the number of its gaps, and for a
/// cause that only its text tells apart, a short digest of that text. A NEXT link goes to it.
pub(super) fn anchor(cause: &Cause<'_>) -> String {
    let text = cause.reason.bytes().fold(0_u32, |hash, byte| {
        hash.wrapping_mul(31).wrapping_add(u32::from(byte))
    });
    match cause.kind {
        "other" | "named" => format!("cause-{}-{}-{text:08x}", cause.kind, cause.total),
        kind => format!("cause-{kind}-{}", cause.total),
    }
}

/// What the cause is, in one phrase.
pub(super) fn title(cause: &Cause<'_>) -> String {
    match cause.kind {
        "coverage_gaps" => format!("{} in the scan", count(cause.total, "coverage gap")),
        "pair_gaps" => format!("{} with gaps", count(cause.total, "module pair")),
        "allowed_pair_gaps" => format!(
            "{} with gaps that the contract allows",
            count(cause.total, "module pair")
        ),
        "scoped_gaps" => format!(
            "{} with an effect that the rule reads",
            count(cause.total, "gap")
        ),
        "unknown_imports" => format!(
            "{} that no gap names",
            count(cause.unnamed, "unresolved import")
        ),
        "no_source_files" => "the collector selected no source file".to_owned(),
        "named" if cause.members.len() > 1 => match hygiene(cause.reason) {
            Some((code, _, _)) => hygiene_title(code, cause.members.len()),
            None => short(cause.reason),
        },
        _ => short(cause.reason),
    }
}

/// A reason as one short sentence: a list after the last colon shows three examples and the number
/// of the others; a long text is cut at a word. The whole text stays in the cause card.
pub(super) fn short(reason: &str) -> String {
    if let Some((head, tail)) = reason.rsplit_once(": ") {
        let items: Vec<&str> = tail.split(", ").collect();
        if items.len() > 4 {
            return format!(
                "{head}: {}, +{} more",
                items[..3].join(", "),
                items.len() - 3
            );
        }
    }
    if reason.chars().count() <= 140 {
        return reason.to_owned();
    }
    let cut: String = reason.chars().take(140).collect();
    let end = cut.rfind(' ').unwrap_or(cut.len());
    format!("{} \u{2026}", &cut[..end])
}
