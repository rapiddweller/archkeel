// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import scope of `interface_boundary` (AD-428). Lifecycle checks are separate.
//! Each selected crossing needs a known binding and a witnessed publication route.

use std::collections::HashSet;

use archkeel_contract::{Component, InterfaceBoundary, Rule};
use archkeel_facts::envelope::LimitSupport;

use crate::causes::InterfaceGap;
use crate::direction::{Crossing, Judged};
use crate::imports::Import;
use crate::model::Model;
use crate::ownership::owner_of;
use crate::reason::Reason;

/// One judgement serves both violations and the existing scope proof.
pub fn interface_crossings<'m>(model: &'m Model, rule: &InterfaceBoundary) -> Vec<Crossing<'m>> {
    let rejected: HashSet<&str> = model
        .contract()
        .rules()
        .iter()
        .filter_map(|r| match r {
            Rule::ForbiddenDependency(r) => Some(crate::direction::forbidden(model, r)),
            _ => None,
        })
        .flatten()
        .filter(|(_, j)| *j == Judged::Fail)
        .map(|(i, _)| i.id())
        .collect();
    model
        .graph()
        .imports()
        .iter()
        .filter_map(|import| {
            if !model.selects(import.source_module())
                || rejected.contains(import.id())
                || (import.under_type_checking() && !rule.include_type_checking())
            {
                return None;
            }
            let components = model.components();
            let from = owner_of(components, import.source_module())?;
            let to = owner_of(components, import.target_module())?;
            let source = components.get(from)?;
            let target = components.get(to)?;
            if from == to || target.public().is_none() {
                return None;
            }
            let judged = match assess(model, rule, target, import) {
                Ok(true) => Judged::Pass,
                Ok(false) => Judged::Fail,
                Err(_) => Judged::Undecided,
            };
            Some(Crossing {
                import,
                source,
                target,
                judged,
            })
        })
        .collect()
}

/// A receipt never creates a PASS. `Scope::complete` consumes it with all other proofs.
pub(crate) fn receipt(model: &Model, rule: &InterfaceBoundary) -> Result<(), Reason> {
    let supported = model
        .graph()
        .observed()
        .profile_limits
        .is_some_and(|p| p.interface_boundary == LimitSupport::Supported);
    if !supported {
        return Err(Reason::Interface(InterfaceGap::PublicationSurface));
    }
    for crossing in interface_crossings(model, rule) {
        assess(model, rule, crossing.target, crossing.import).map_err(Reason::Interface)?;
    }
    if model
        .graph()
        .modules()
        .iter()
        .any(|(id, _)| model.holds(id))
    {
        Ok(())
    } else {
        Err(Reason::NoSubjects)
    }
}

fn assess(
    model: &Model,
    rule: &InterfaceBoundary,
    target: &Component,
    import: &Import,
) -> Result<bool, InterfaceGap> {
    if import.under_type_checking()
        && (!import.symbols_known()
            || import.symbol().is_none_or(|n| n == "*" || n == "default")
            || !(1..=2).contains(&import.reexport_chain().len()))
    {
        return Err(InterfaceGap::TypePublication);
    }
    if !import.symbols_known() || import.symbol() == Some("*") {
        return Err(InterfaceGap::UnreadBinding);
    }
    let public: Vec<&str> = target
        .public()
        .iter()
        .flatten()
        .map(|p| p.as_text())
        .collect();
    let module = import.target_module();
    let Some(name) = import.symbol() else {
        let granted = rule.module_object_grants().iter().flatten().any(|g| {
            g.source_module().as_text() == import.source_module()
                && g.target_module().as_text() == module
        });
        return Ok(public.contains(&module) || granted);
    };
    if name.starts_with('_') {
        return Ok(false);
    }
    let route = format!("{module}.{name}");
    if !import.reexport_chain().contains(&route) {
        return Err(InterfaceGap::PublicationRoute);
    }
    // 4.0.1 `interface_covers_import`: the import is public when any hop of its route is. A
    // named type route keeps its first hop only (the collector proves one or two hops).
    let chain = import.reexport_chain();
    let hops = if import.under_type_checking() {
        &chain[..1.min(chain.len())]
    } else {
        chain
    };
    let mut unread = None;
    for hop in hops {
        let Some((hop_module, hop_name)) = hop.rsplit_once('.') else {
            continue;
        };
        match covers(model, &public, hop_module, hop_name) {
            Ok(true) => return Ok(true),
            Ok(false) => {}
            Err(gap) => unread = Some(gap),
        }
    }
    unread.map_or(Ok(false), Err)
}

/// `facade_covers`: one hop of a route against the public entries of the target component.
fn covers(model: &Model, public: &[&str], module: &str, name: &str) -> Result<bool, InterfaceGap> {
    if name.starts_with('_') {
        return Ok(false);
    }
    if public.contains(&format!("{module}:{name}").as_str()) {
        return Ok(true);
    }
    if !public.contains(&module) {
        return Ok(false);
    }
    let file = model
        .graph()
        .modules()
        .iter()
        .find(|(_, m)| m.name() == module)
        .map(|(_, m)| m);
    file.map(|m| {
        m.exports().is_empty() && !m.exports_literal() || m.exports().iter().any(|n| n == name)
    })
    .ok_or(InterfaceGap::PublicationSurface)
}
