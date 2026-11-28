// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Contract matching above the reply inventory. Both the evaluator and scope proof use it (AD-408).

use archkeel_contract::ForbiddenConstruct;
use archkeel_facts::data::SelectorData;
use archkeel_facts::envelope::ConstructSupport;
use archkeel_facts::vocab::Status;

use crate::causes::Cause;
use crate::constructs::{ConstructMatch, ConstructSite, Constructs, Work};
use crate::limits::word;
use crate::model::Model;
use crate::ownership::in_scope;
use crate::reason::Reason;
use crate::selection::{unused_by_module, UnusedAllowance};

/// Matching forbidden sites; a literal conflict of a proven selector is not forbidden.
pub fn matches<'a>(
    model: &'a Model,
    rule: &ForbiddenConstruct,
) -> Result<Vec<ConstructMatch<'a>>, Reason> {
    let inventory = model.graph().constructs();
    let mut work = Work(4_000_000);
    let mut found = Vec::new();
    for site in &inventory.sites {
        work.charge(1)?;
        work.charge(model.graph().modules().len())?;
        work.charge(rule.allowed_sources().len())?;
        work.charge(rule.exact_sources().len())?;
        work.charge(rule.constructs().len())?;
        work.charge(rule.allowed_type_ignores().len())?;
        if !selected(model, rule, site) {
            continue;
        }
        if let Some(known) = matching(rule, site) {
            found.push(ConstructMatch { site, known });
        }
    }
    Ok(found)
}

pub(crate) fn receipt<'a>(
    model: &Model,
    rule: &'a ForbiddenConstruct,
) -> Result<Option<&'a str>, Reason> {
    let mut needs_premise = false;
    let inventory = model.graph().constructs();
    let mut work = Work(4_000_000);
    let modules = model.graph().modules().len();
    work.charge(
        inventory
            .symbols
            .len()
            .saturating_mul(modules.saturating_add(1)),
    )?;
    work.charge(modules.saturating_mul(model.components().len().saturating_add(1)))?;
    if model.source_modules(rule.source().as_text()).is_empty()
        && !inventory.symbols.iter().any(|(module, name)| {
            model.selects(module)
                && in_scope(name, module)
                && model
                    .graph()
                    .modules()
                    .iter()
                    .any(|(_, m)| m.name() == module)
                && in_scope(name, rule.source().as_text())
        })
    {
        return Err(Reason::NoSubjects);
    }
    for construct in rule.constructs() {
        work.charge(archkeel_facts::vocab::Signal::ALL.len())?;
        let name = word(construct);
        let signal = archkeel_facts::vocab::Signal::ALL
            .iter()
            .any(|s| s.construct() == Some(String::as_str(&name)));
        let measured = if signal {
            inventory.signals_measured
        } else {
            inventory.constructs_measured
        };
        if !measured {
            return Err(Cause::Receipt("the construct record section is not measured").into());
        }
        work.charge(inventory.capabilities.len().saturating_add(1))?;
        let support = inventory
            .capabilities
            .iter()
            .find(|(name, _)| name == &word(construct));
        if !matches!(
            support,
            Some((_, ConstructSupport::Supported | ConstructSupport::Decided))
        ) {
            let conditional = match name.as_str() {
                "placeholder_body" => inventory.placeholder_under_premise,
                "any_annotation" => inventory.any_annotation_under_premise,
                _ => false,
            };
            if !conditional {
                return Err(Cause::Receipt("construct absence is not completely observed").into());
            }
            needs_premise = true;
        }
        // A form in a module that the rule judges can hide a site, though the survey is `supported`.
        let mut hidden = inventory
            .unseen
            .iter()
            .filter(|(owner, hidden)| *hidden == name && judges(model, rule, owner))
            .map(|(owner, _)| owner.as_str())
            .collect::<Vec<_>>();
        hidden.sort_unstable();
        if let Some(first) = hidden.first() {
            return Err(Cause::UnseenForm(format!("{name} in {first}")).into());
        }
    }
    if rule.selector().is_some() {
        selector_receipt(inventory, model, rule, &mut work)?;
    }
    Ok(needs_premise.then(|| rule.source().as_text()))
}

/// Whether the site is one that the rule names, before its type-ignore allowances apply.
fn named(rule: &ForbiddenConstruct, site: &ConstructSite) -> Option<bool> {
    match (rule.selector(), &site.selector) {
        (Some(selector), Some(data)) => selector_match(selector, data),
        (None, None) if rule.constructs().iter().any(|c| word(c) == site.construct) => Some(true),
        _ => None,
    }
}

fn matching(rule: &ForbiddenConstruct, site: &ConstructSite) -> Option<bool> {
    named(rule, site).filter(|_| rule.selector().is_some() || !allowed_ignore(rule, site))
}

fn selector_match(
    selector: &archkeel_contract::ConstructSelector,
    data: &SelectorData,
) -> Option<bool> {
    let wrong_receiver = data
        .receiver_type
        .as_deref()
        .is_some_and(|r| r != selector.receiver().as_text());
    let wrong_member = selector.member().as_ref().is_some_and(|member| {
        data.member.as_ref() != Some(member)
            && !(data.member.is_none() && data.status == Status::Unknown)
    });
    if data.selector_role.as_str() != word(selector.role()) || wrong_receiver || wrong_member {
        return None;
    }
    let known = data.status == Status::Decided
        && data.receiver_type.as_deref() == Some(selector.receiver().as_text());
    let conflict = selector.literal().is_some()
        && data.literal.is_some()
        && selector.literal() != &data.literal;
    let literal_matches = selector.literal().is_none() || selector.literal() == &data.literal;
    (!(known && conflict)).then_some(known && literal_matches)
}

fn selector_receipt(
    inventory: &Constructs,
    model: &Model,
    rule: &ForbiddenConstruct,
    work: &mut Work,
) -> Result<(), Reason> {
    let Some(selector) = rule.selector() else {
        return Ok(());
    };
    let observed = model.graph().observed();
    if !observed.construct_selectors || !observed.inventory_complete {
        return Err(Cause::Receipt("the selector inventory is not complete").into());
    }
    let matches = matches(model, rule)?;
    if matches.iter().any(|m| !m.known) {
        return Err(Cause::Receipt("unresolved selected identity").into());
    }
    let mut any = false;
    for site in &inventory.sites {
        work.charge(
            model
                .graph()
                .modules()
                .len()
                .saturating_add(rule.allowed_sources().len())
                .saturating_add(rule.exact_sources().len())
                .saturating_add(1),
        )?;
        if !selected(model, rule, site) {
            continue;
        }
        if let Some(data) = &site.selector {
            // A proven different literal is a selected subject too, but not a violation.
            any |= data.selector_role.as_str() == word(selector.role())
                && data.receiver_type.as_deref() == Some(selector.receiver().as_text())
                && data.member == *selector.member()
                && data.status == Status::Decided;
        }
    }
    if !any {
        return Err(Cause::Receipt("no selected subject was observed").into());
    }
    Ok(())
}

/// The module or function that owns the site.
fn owner(site: &ConstructSite) -> &str {
    site.owner.split(':').next().unwrap_or_default()
}

/// Whether the site lies in the source of the rule.
fn in_source(model: &Model, rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    owner_in_source(model, rule, &site.owner)
}

fn owner_in_source(model: &Model, rule: &ForbiddenConstruct, full_owner: &str) -> bool {
    let owner = full_owner.split(':').next().unwrap_or_default();
    model
        .graph()
        .modules()
        .iter()
        .any(|(id, module)| model.holds(id) && in_scope(full_owner, module.name()))
        && in_scope(owner, rule.source().as_text())
}

fn selected(model: &Model, rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    judges(model, rule, &site.owner)
}

/// Whether the rule judges the code of `full_owner`: it lies in the source and no exemption names it.
fn judges(model: &Model, rule: &ForbiddenConstruct, full_owner: &str) -> bool {
    let owner = full_owner.split(':').next().unwrap_or_default();
    owner_in_source(model, rule, full_owner)
        && !rule
            .allowed_sources()
            .iter()
            .any(|a| in_scope(owner, a.as_text()))
        && !rule.exact_sources().iter().any(|a| a.as_text() == owner)
}

fn allowed_ignore(rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    ignores_at(rule, site).next().is_some()
}

/// The positions of the `allowed_type_ignores` entries that name the site.
fn ignores_at<'r>(
    rule: &'r ForbiddenConstruct,
    site: &'r ConstructSite,
) -> impl Iterator<Item = usize> + 'r {
    let data = site
        .signal
        .as_ref()
        .filter(|_| site.construct == "type_ignore");
    rule.allowed_type_ignores()
        .iter()
        .enumerate()
        .filter(move |(_, a)| {
            data.is_some_and(|data| {
                data.qualified_name.as_deref() == Some(a.qualified_name().as_text())
                    && data.line.and_then(|n| u64::try_from(n).ok()) == Some(*a.line())
                    && data.statement.as_deref() == Some(a.statement().as_str())
                    && data.tag.as_deref() == Some(a.tag().as_str())
            })
        })
        .map(|(at, _)| at)
}

/// The exception entries of a rule that name no site that it judges (AD-1070). A rule whose
/// receipt is not complete, or that judges no site, reports none: an unread site can be the one.
pub(crate) fn unused_allowances(model: &Model, rule: &ForbiddenConstruct) -> Vec<UnusedAllowance> {
    if receipt(model, rule).is_err() {
        return Vec::new();
    }
    let sites = model.graph().constructs().sites.iter();
    let sites: Vec<_> = sites
        .filter(|site| in_source(model, rule, site) && named(rule, site).is_some())
        .collect();
    if sites.is_empty() {
        return Vec::new();
    }
    let owners: Vec<&str> = sites.iter().map(|site| owner(site)).collect();
    let (allowed, exact) = (rule.allowed_sources(), rule.exact_sources());
    // An entry that names code with a form that can hide a site is not unused: the site can be there.
    let words: Vec<String> = rule.constructs().iter().map(word).collect();
    let unseen = &model.graph().constructs().unseen;
    let hidden = |entry: &str| {
        unseen.iter().any(|(module, hidden)| {
            words.contains(hidden) && (in_scope(module, entry) || in_scope(entry, module))
        })
    };
    let mut found = unused_by_module(allowed, exact, &owners, hidden);
    let used: Vec<usize> = sites
        .iter()
        .flat_map(|site| ignores_at(rule, site))
        .collect();
    let ignores = rule.allowed_type_ignores().iter().enumerate();
    found.extend(
        ignores
            .filter(|(at, _)| !used.contains(at))
            .map(|(index, ignore)| {
                let entry = format!("{}:{}", ignore.qualified_name().as_text(), ignore.line());
                UnusedAllowance {
                    field: "allowed_type_ignores",
                    index,
                    entry,
                }
            }),
    );
    found
}
