// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import scope of `interface_boundary` (AD-428). Lifecycle checks are separate.
//! Each selected crossing needs a known binding and a witnessed publication route.

use std::collections::HashSet;

use archkeel_contract::{Component, InterfaceBoundary, Rule};
use archkeel_facts::envelope::LimitSupport;

use crate::causes::{InterfaceGap, InterfaceHold};
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
                || namespace(model, import)
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

/// AD-604: an import of a whole module binds no name when the collector writes each use through
/// it as a record of its own. The uses are the crossings; the import itself publishes nothing.
fn namespace(model: &Model, import: &Import) -> bool {
    import.symbols_known()
        && import.symbol().is_none()
        && model.graph().observed().analysis.namespace_uses
}

/// A name that a re-export publishes outside the package of its module (AD-608), judged against
/// the `public` entries of the component of that module.
pub struct Publication<'m> {
    /// The re-export record.
    pub import: &'m Import,
    /// The component that publishes the name.
    pub component: &'m Component,
    /// The published name, `*` for a glob.
    pub name: &'m str,
    /// Pass when an entry lists the name, Undecided for a glob.
    pub judged: Judged,
}

/// AD-608: a re-export that publishes a name outside its package must publish a name that its
/// component lists in `public` (`module:name`, or the whole module). A component without
/// `public` is no subject, as for an import.
pub fn interface_publications<'m>(
    model: &'m Model,
    rule: &InterfaceBoundary,
) -> Vec<Publication<'m>> {
    let components = model.components();
    model
        .graph()
        .imports()
        .iter()
        .filter_map(|import| {
            let name = import.published_as()?;
            if !model.selects(import.source_module())
                || (import.under_type_checking() && !rule.include_type_checking())
            {
                return None;
            }
            let component = components.get(owner_of(components, import.source_module())?)?;
            let public = component.public().as_ref()?;
            let module = import.source_module();
            let listed = public.iter().any(|entry| {
                let entry = entry.as_text();
                entry == module || entry == format!("{module}:{name}")
            });
            let judged = match (name, listed) {
                (_, true) => Judged::Pass,
                ("*", false) => Judged::Undecided,
                (_, false) => Judged::Fail,
            };
            Some(Publication {
                import,
                component,
                name,
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
        return Err(Reason::Interface(InterfaceHold::bare(
            InterfaceGap::PublicationSurface,
        )));
    }
    let mut undecided: Vec<(InterfaceGap, &Import, Option<&str>)> = Vec::new();
    for crossing in interface_crossings(model, rule) {
        if let Err(gap) = assess(model, rule, crossing.target, crossing.import) {
            undecided.push((gap, crossing.import, crossing.import.symbol()));
        }
    }
    for publication in interface_publications(model, rule) {
        if publication.judged == Judged::Undecided {
            let gap = InterfaceGap::UnreadBinding;
            undecided.push((gap, publication.import, Some(publication.name)));
        }
    }
    let listed = undecided
        .iter()
        .map(|(gap, import, name)| (*gap, import.source_module(), import.target_module(), *name));
    if let Some(hold) = InterfaceHold::of(listed) {
        return Err(Reason::Interface(hold));
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
    let public: Vec<&str> = target
        .public()
        .iter()
        .flatten()
        .map(|p| p.as_text())
        .collect();
    let module = import.target_module();
    if !import.symbols_known() && import.symbol().is_none() && surface_stated(model) {
        return whole_namespace(&public, module, import);
    }
    if !import.symbols_known() || import.symbol() == Some("*") {
        return Err(InterfaceGap::UnreadBinding);
    }
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
    match unread {
        Some(gap) => Err(gap),
        // AD-604: a later hop of a route that the collector proves only in part may be public.
        None if !import.route_complete() => Err(InterfaceGap::PublicationRoute),
        None => Ok(false),
    }
}

/// True when the linked collector states the publication surface of each import (AD-749).
fn surface_stated(model: &Model) -> bool {
    model
        .graph()
        .observed()
        .profile_limits
        .is_some_and(|p| p.publication_surface == LimitSupport::Supported)
}

/// AD-749 (4.0.1 AD-97): with a stated publication surface, a record without a name binds each
/// name of its target module, and the collector reads no use of them. It passes when `public`
/// lists the module. It fails only when no name of the module can be public: no `module:name`
/// entry, and a complete route, so no re-export of the module can pass on a name of another
/// module. Any other case is a gap.
fn whole_namespace(public: &[&str], module: &str, import: &Import) -> Result<bool, InterfaceGap> {
    let prefix = format!("{module}:");
    if public.contains(&module) {
        Ok(true)
    } else if public.iter().any(|entry| entry.starts_with(&prefix)) {
        Err(InterfaceGap::UnreadBinding)
    } else if !import.route_complete() {
        Err(InterfaceGap::PublicationRoute)
    } else {
        Ok(false)
    }
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

/// `interface_covers_import` for a count of uses (AD-514): whether the route of an import reaches
/// a public entry of `target`. A hop that the survey cannot read counts as not reaching it, so a
/// caller that counts uses never counts one that it cannot prove.
pub fn publishes(
    model: &Model,
    target: &Component,
    module: &str,
    symbol: Option<&str>,
    hops: &[String],
) -> bool {
    let public: Vec<&str> = target
        .public()
        .iter()
        .flatten()
        .map(|p| p.as_text())
        .collect();
    let Some(name) = symbol else {
        return public.contains(&module);
    };
    if target.public().is_none() || name.starts_with('_') {
        return false;
    }
    hops.iter().any(|hop| {
        hop.rsplit_once('.').is_some_and(|(hop_module, hop_name)| {
            covers(model, &public, hop_module, hop_name) == Ok(true)
        })
    })
}
