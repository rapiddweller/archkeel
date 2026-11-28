// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Which trojan horse sites of a reply a declaration names (AD-664, AD-1052, AD-1480): the module,
//! the form or the name, the scope and, only as a hint with a scope, the line. It reads collector
//! metadata, not source code. `door_reach.rs` applies the matched declarations.

use archkeel_contract::TrojanHorseReach as Declaration;
use archkeel_facts::data::{GapEffect, TrojanHorseForm};

use crate::coverage::data_of;

/// One trojan horse of the reply.
pub(crate) struct TrojanHorse<'f> {
    pub(crate) gap: &'f str,
    pub(crate) module: &'f str,
    pub(crate) form: Option<TrojanHorseForm>,
    pub(crate) name: Option<&'f str>,
    pub(crate) line: u32,
    pub(crate) scope: Option<&'f str>,
    pub(crate) exposed: &'f [String],
    pub(crate) effect: &'f GapEffect,
    pub(crate) evidence: Vec<String>,
    pub(crate) binding: Option<&'f str>,
}

/// The trojan horse of a gap, when the collector marks one and names its module and its effect.
pub(crate) fn trojan_horse(
    gap: &archkeel_facts::Record<archkeel_facts::GapFact>,
) -> Option<TrojanHorse<'_>> {
    let data = data_of(&gap.data);
    let site = data.trojan_horse.as_ref()?;
    Some(TrojanHorse {
        gap: gap.id.as_str(),
        module: data.module.as_ref()?.as_str(),
        form: site.form,
        name: Option::as_deref(&site.site_name),
        exposed: &site.exposed_to,
        line: site.line,
        scope: (!site.line_only).then(|| site.scope.as_deref().unwrap_or("")),
        effect: data.effect.as_ref()?,
        evidence: gap
            .evidence_ids
            .iter()
            .map(|id| id.as_str().to_owned())
            .collect(),
        binding: site.binding.as_deref(),
    })
}

/// True when the declaration names the module and the form or the name of this trojan horse.
fn same_site(
    horse: &TrojanHorse<'_>,
    declaration: &Declaration,
    form: Option<TrojanHorseForm>,
) -> bool {
    horse.module == declaration.module().as_text()
        && match form {
            Some(form) => horse.form == Some(form),
            None => horse.name == Option::as_deref(declaration.site_name()),
        }
}

/// True when the scope of the declaration, if it has one, is the scope of this trojan horse.
fn in_scope_of(horse: &TrojanHorse<'_>, declaration: &Declaration) -> bool {
    declaration
        .scope()
        .as_deref()
        .is_none_or(|scope| horse.scope == Some(scope))
}

/// The trojan horses that a declaration names (AD-664, AD-1052, AD-1480). With a `scope` the anchor is
/// the module, the form or name and the scope, and the `line` is a hint: when the scope holds
/// exactly `count` such sites they are the sites, wherever their lines are. When it holds more,
/// the line picks among them. Without a `scope` the line must equal the line of the site.
pub(crate) fn sites_of<'a, 'f>(
    horses: &'a [TrojanHorse<'f>],
    declaration: &Declaration,
    form: Option<TrojanHorseForm>,
    count: usize,
) -> Vec<&'a TrojanHorse<'f>> {
    let line_is = |horse: &&TrojanHorse<'_>| {
        declaration
            .line()
            .is_none_or(|line| u64::from(horse.line) == line)
    };
    let anchored: Vec<&TrojanHorse<'_>> = horses
        .iter()
        .filter(|horse| same_site(horse, declaration, form) && in_scope_of(horse, declaration))
        .collect();
    if declaration.scope().is_none() {
        return anchored.into_iter().filter(line_is).collect();
    }
    if anchored.len() <= count {
        return anchored;
    }
    let by_line: Vec<&TrojanHorse<'_>> = anchored.iter().copied().filter(line_is).collect();
    if by_line.len() == count {
        by_line
    } else {
        anchored
    }
}

/// The sites of the module with the name or the form of the declaration, as `line L scope S`, for
/// the row of a declaration that matches nothing.
pub(crate) fn near(
    horses: &[TrojanHorse<'_>],
    declaration: &Declaration,
    form: Option<TrojanHorseForm>,
) -> String {
    let mut sites: Vec<(u32, &str)> = horses
        .iter()
        .filter(|horse| same_site(horse, declaration, form))
        .map(|horse| (horse.line, horse.scope.unwrap_or("(scope not stated)")))
        .collect();
    sites.sort_unstable();
    let shown: Vec<String> = sites
        .iter()
        .take(6)
        .map(|(line, scope)| {
            let scope = if scope.is_empty() {
                "(module level)"
            } else {
                scope
            };
            format!("line {line} scope {scope}")
        })
        .collect();
    let more = sites.len().saturating_sub(shown.len());
    let tail = if more > 0 {
        format!(" and {more} more")
    } else {
        String::new()
    };
    format!("{}{tail}", shown.join("; "))
}
