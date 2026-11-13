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

pub(crate) fn receipt(model: &Model, rule: &ForbiddenConstruct) -> Result<(), Reason> {
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
            .any(|s| s.construct() == Some(name.as_str()));
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
            return Err(Cause::Receipt("construct absence is not completely observed").into());
        }
    }
    if rule.selector().is_some() {
        selector_receipt(inventory, model, rule, &mut work)?;
    }
    Ok(())
}

fn matching(rule: &ForbiddenConstruct, site: &ConstructSite) -> Option<bool> {
    match (rule.selector(), &site.selector) {
        (Some(selector), Some(data)) => selector_match(selector, data),
        (None, None)
            if rule.constructs().iter().any(|c| word(c) == site.construct)
                && !allowed_ignore(rule, site) =>
        {
            Some(true)
        }
        _ => None,
    }
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
    if !inventory.selectors || !model.graph().observed().inventory_complete {
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

fn selected(model: &Model, rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    let owner = site.owner.split(':').next().unwrap_or_default();
    model
        .graph()
        .modules()
        .iter()
        .any(|(id, module)| model.holds(id) && in_scope(&site.owner, module.name()))
        && in_scope(owner, rule.source().as_text())
        && !rule
            .allowed_sources()
            .iter()
            .any(|a| in_scope(owner, a.as_text()))
        && !rule.exact_sources().iter().any(|a| a.as_text() == owner)
}

fn allowed_ignore(rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    let Some(data) = &site.signal else {
        return false;
    };
    if data.signal != archkeel_facts::vocab::Signal::TypeIgnore {
        return false;
    }
    rule.allowed_type_ignores().iter().any(|a| {
        data.qualified_name.as_deref() == Some(a.qualified_name().as_text())
            && data.line.and_then(|n| u64::try_from(n).ok()) == Some(*a.line())
            && data.statement.as_deref() == Some(a.statement().as_str())
            && data.tag.as_deref() == Some(a.tag().as_str())
    })
}
