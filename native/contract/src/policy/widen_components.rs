// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The widenings and narrowings of components (Python `ir/widening.py`): presence, `public`,
//! `planned`, `requires`, `namespace` and each other field, which fails closed.

use std::collections::{BTreeMap, BTreeSet};

use crate::model::{Component, DecidedBy, Requirement};
use crate::policy::change::{fields_of, generic_widenings, ChangeKind, ContractChange};
use crate::policy::pyrepr::{list, word};
use crate::policy::reference::python_repr;

/// One effective `requires` entry: the target label, the selectors and the author (AD-50).
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
struct Entry {
    component: String,
    through: Vec<String>,
    decided_by: Option<String>,
}

/// Python `_effective_requires`: an entry without an author has the author of its component.
fn effective(component: &Component) -> Vec<Entry> {
    let author = component.decided_by.as_ref();
    component
        .requires
        .iter()
        .flatten()
        .map(|item: &Requirement| Entry {
            component: item.component.0.clone(),
            through: item
                .through
                .iter()
                .map(|selector| selector.0.clone())
                .collect(),
            decided_by: item.decided_by.as_ref().or(author).map(word::<DecidedBy>),
        })
        .collect()
}

/// Python `in_scope`: a name in a dotted prefix, without a part of a segment.
fn in_scope(name: &str, scope: &str) -> bool {
    name == scope
        || name
            .strip_prefix(scope)
            .is_some_and(|rest| rest.starts_with('.'))
}

/// Python `_required_port_assessment(...) is PASS` with known symbols.
fn port_passes(port: &str, module: &str, symbol: Option<&str>) -> bool {
    match port.split_once(':') {
        None => in_scope(module, port),
        Some((port_module, port_symbol)) => module == port_module && symbol == Some(port_symbol),
    }
}

/// Python `requires_covers` with a module.
fn covers(entries: &[&Entry], label: &str, module: &str, symbol: Option<&str>) -> bool {
    entries.iter().any(|entry| {
        entry.component == label
            && (entry.through.is_empty()
                || entry
                    .through
                    .iter()
                    .any(|port| port_passes(port, module, symbol)))
    })
}

/// Python `_contained`: `before` already let the same author import all that `entry` permits.
fn contained(entry: &Entry, before: &[Entry]) -> bool {
    let same: Vec<&Entry> = before
        .iter()
        .filter(|item| item.component == entry.component && item.decided_by == entry.decided_by)
        .collect();
    if entry.through.is_empty() {
        return same.iter().any(|item| item.through.is_empty());
    }
    entry.through.iter().all(|selector| {
        let (module, symbol) = selector.split_once(':').unwrap_or((selector, ""));
        let symbol = (!symbol.is_empty()).then_some(symbol);
        covers(&same, &entry.component, module, symbol)
    })
}

fn requires_widenings(subject: &str, before: &[Entry], after: &[Entry]) -> Vec<ContractChange> {
    let labels: BTreeSet<&str> = before.iter().map(|item| item.component.as_str()).collect();
    let new: BTreeSet<&Entry> = after
        .iter()
        .filter(|item| !contained(item, before) && !before.contains(item))
        .collect();
    new.into_iter()
        .map(|entry| {
            let name = python_repr(&entry.component);
            let message = if labels.contains(entry.component.as_str()) {
                let author = entry
                    .decided_by
                    .as_ref()
                    .map(|who| format!(", decided by {who}"))
                    .unwrap_or_default();
                let through = list(entry.through.iter().map(String::as_str));
                format!("{subject}.requires[{name}] gained an entry through {through}{author}")
            } else {
                format!("{subject}.requires gained an edge to {name}")
            };
            ContractChange::widened(ChangeKind::Gained, subject, "requires", message)
        })
        .collect()
}

fn namespace_widenings(
    subject: &str,
    before: Option<&str>,
    after: Option<&str>,
) -> Vec<ContractChange> {
    if before.is_none() || before == after {
        return Vec::new();
    }
    let text = |value: Option<&str>| value.map_or_else(|| "None".to_owned(), python_repr);
    let message = format!(
        "{subject}.namespace changed from {} to {}",
        text(before),
        text(after)
    );
    vec![ContractChange::widened(
        ChangeKind::Changed,
        subject,
        "namespace",
        message,
    )]
}

/// Python `last_name`: the segment after the last `:`, then after the last `.`.
fn last_name(name: &str) -> &str {
    let symbol = name.rsplit(':').next().unwrap_or(name);
    symbol.rsplit('.').next().unwrap_or(symbol)
}

fn alike(entry: &str, other: &str) -> bool {
    entry.contains(':') == other.contains(':') && last_name(entry) == last_name(other)
}

/// Python `_in_place_of`: the one lost entry that a gained entry may replace.
fn in_place_of(entry: &str, gained: &BTreeSet<&str>, lost: &BTreeSet<&str>) -> String {
    let matches: Vec<&&str> = lost.iter().filter(|item| alike(entry, item)).collect();
    let [only] = matches.as_slice() else {
        return String::new();
    };
    let twins: Vec<&&str> = gained.iter().filter(|item| alike(item, only)).collect();
    if twins.as_slice() == [&entry] {
        format!(" in place of {}", python_repr(only))
    } else {
        String::new()
    }
}

fn texts(values: Option<&Vec<crate::model::Selector>>) -> BTreeSet<&str> {
    values
        .into_iter()
        .flatten()
        .map(|item| item.0.as_str())
        .collect()
}

fn public_widenings(subject: &str, before: &Component, after: &Component) -> Vec<ContractChange> {
    let (old_public, new_public) = (texts(before.public.as_ref()), texts(after.public.as_ref()));
    let (old_planned, new_planned) = (
        texts(before.planned.as_ref()),
        texts(after.planned.as_ref()),
    );
    let dropped: BTreeSet<&str> = old_planned.difference(&new_planned).copied().collect();
    let promoted: BTreeSet<&str> = dropped.intersection(&new_public).copied().collect();
    let gained: BTreeSet<&str> = new_public
        .difference(&old_public)
        .filter(|item| !promoted.contains(*item))
        .copied()
        .collect();
    let lost: BTreeSet<&str> = old_public.difference(&new_public).copied().collect();
    let mut changes: Vec<ContractChange> = gained
        .iter()
        .map(|item| {
            let place = in_place_of(item, &gained, &lost);
            let message = format!("{subject}.public gained {}{place}", python_repr(item));
            ContractChange::widened(ChangeKind::Gained, subject, "public", message)
        })
        .collect();
    changes.extend(dropped.difference(&promoted).map(|item| {
        let message = format!("{subject}.planned lost {}", python_repr(item));
        ContractChange::widened(ChangeKind::Lost, subject, "planned", message)
    }));
    changes
}

fn component_widenings(before: &Component, after: &Component) -> Vec<ContractChange> {
    let subject = format!("component {}", python_repr(&before.label.0));
    let mut changes = public_widenings(&subject, before, after);
    changes.extend(requires_widenings(
        &subject,
        &effective(before),
        &effective(after),
    ));
    let namespace = |item: &Component| item.namespace.as_ref().map(|value| value.0.clone());
    changes.extend(namespace_widenings(
        &subject,
        namespace(before).as_deref(),
        namespace(after).as_deref(),
    ));
    let handled = ["public", "planned", "requires", "namespace"];
    changes.extend(generic_widenings(
        &subject,
        fields_of(before).as_ref(),
        fields_of(after).as_ref(),
        &handled,
    ));
    changes
}

fn presence(component: &Component, verb: &str) -> ContractChange {
    let subject = format!("component {}", python_repr(&component.label.0));
    let message = format!("{subject} {verb}");
    ContractChange::widened(ChangeKind::Presence, &subject, "presence", message)
}

fn by_id(items: &[Component]) -> BTreeMap<&str, &Component> {
    items
        .iter()
        .map(|item| (item.id.0.as_str(), item))
        .collect()
}

/// Python `_components_widenings`: components matched by ID.
pub(crate) fn components_widenings(
    before: &[Component],
    after: &[Component],
) -> Vec<ContractChange> {
    let old = by_id(before);
    let new = by_id(after);
    let mut changes: Vec<ContractChange> = new
        .iter()
        .filter(|(id, _)| !old.contains_key(*id))
        .map(|(_, item)| presence(item, "added"))
        .collect();
    changes.extend(
        old.iter()
            .filter(|(id, _)| !new.contains_key(*id))
            .map(|(_, item)| presence(item, "removed")),
    );
    for (id, item) in &old {
        if let Some(other) = new.get(id) {
            changes.extend(component_widenings(item, other));
        }
    }
    changes
}

/// Python `_requires_narrowings`: per target and author, entries that went away.
fn requires_narrowings(subject: &str, before: &[Entry], after: &[Entry]) -> Vec<ContractChange> {
    let keys: BTreeSet<(&str, Option<&str>)> = before
        .iter()
        .map(|item| (item.component.as_str(), item.decided_by.as_deref()))
        .collect();
    let mut changes = Vec::new();
    for (name, author) in keys {
        let key = |item: &&Entry| item.component == name && item.decided_by.as_deref() == author;
        let lists = |items: Vec<&Entry>| -> String {
            let texts: Vec<String> = items
                .iter()
                .map(|item| list(item.through.iter().map(String::as_str)))
                .collect();
            format!("[{}]", texts.join(", "))
        };
        let removed: Vec<&Entry> = before
            .iter()
            .filter(key)
            .filter(|item| !after.contains(item) && !contained(item, after))
            .collect();
        let replacements: Vec<&Entry> = after
            .iter()
            .filter(key)
            .filter(|item| !before.contains(item) && contained(item, before))
            .collect();
        let name = python_repr(name);
        let message = match (removed.is_empty(), replacements.is_empty()) {
            (true, _) => continue,
            (false, false) => format!(
                "{subject}.requires[{name}] narrowed from {} to {}",
                lists(removed),
                lists(replacements)
            ),
            (false, true) => format!(
                "{subject}.requires[{name}] dropped through {}",
                lists(removed)
            ),
        };
        changes.push(ContractChange::narrowed(
            ChangeKind::RequiresDropped,
            subject,
            "requires",
            message,
        ));
    }
    changes
}

/// The component part of Python `contract_narrowing_changes`.
pub(crate) fn components_narrowings(
    before: &[Component],
    after: &[Component],
) -> Vec<ContractChange> {
    let old = by_id(before);
    let mut changes = Vec::new();
    for component in after {
        let Some(previous) = old.get(component.id.0.as_str()) else {
            continue;
        };
        let subject = format!("component {}", python_repr(&component.label.0));
        let lost = texts(previous.public.as_ref());
        let kept = texts(component.public.as_ref());
        changes.extend(lost.difference(&kept).map(|entry| {
            let message = format!("{subject}.public lost {}", python_repr(entry));
            ContractChange::narrowed(ChangeKind::Lost, &subject, "public", message)
        }));
        changes.extend(requires_narrowings(
            &subject,
            &effective(previous),
            &effective(component),
        ));
    }
    changes
}
