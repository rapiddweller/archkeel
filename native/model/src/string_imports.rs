// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The string imports that a contract declares (AD-1440).
//!
//! A string import is a call that names its module by a fixed string. The built-in rule
//! `STRING-IMPORT` forbids it. A record of `declarations.string_imports` names one site by its
//! module, its line and its literal target, and a count when two sites share a line. A record that
//! names another target, or a count that is not the number of sites, applies to nothing: the site
//! stays a violation.

use archkeel_contract::{ForbiddenConstruct, StringImportSite};

use crate::constructs::ConstructSite;
use crate::limits::word;
use crate::model::Model;

/// The module, the line and the target that a string import site states.
fn key(site: &ConstructSite) -> Option<(&str, u64, &str)> {
    let data = site.signal.as_ref()?;
    let line = u64::try_from(data.line?).ok()?;
    Some((site.owner.as_str(), line, data.expression.as_deref()?))
}

/// True for the observation of a string import.
pub(crate) fn is_site(site: &ConstructSite) -> bool {
    site.construct == "string_import"
}

/// True for a rule that forbids a string import.
pub(crate) fn forbids(rule: &ForbiddenConstruct) -> bool {
    rule.constructs()
        .iter()
        .any(|construct| word(construct) == "string_import")
}

fn sites_at<'a>(
    model: &'a Model,
    at: (&'a str, u64, &'a str),
) -> impl Iterator<Item = &'a ConstructSite> {
    let sites = &model.graph().constructs().sites;
    sites
        .iter()
        .filter(move |site| is_site(site) && key(site) == Some(at))
}

/// The record that declares the site: the same module, line and target, and a count that is the
/// number of such sites (one when the record names none).
pub(crate) fn declared<'m>(model: &'m Model, site: &ConstructSite) -> Option<&'m StringImportSite> {
    let at = key(site)?;
    let records = model.contract().declarations().as_ref()?.string_imports();
    let record = records.iter().find(|record| {
        record.module().as_text() == at.0
            && *record.line() == at.1
            && record.target().as_text() == at.2
    })?;
    let here = u64::try_from(sites_at(model, at).count()).ok()?;
    (here == record.site_count().unwrap_or(1)).then_some(record)
}

/// The records that apply, for the premises of the rule: the record and the module and line.
pub(crate) fn applied(model: &Model) -> Vec<(&StringImportSite, String)> {
    let Some(declarations) = model.contract().declarations().as_ref() else {
        return Vec::new();
    };
    let mut found: Vec<(&StringImportSite, String)> = Vec::new();
    for site in model
        .graph()
        .constructs()
        .sites
        .iter()
        .filter(|s| is_site(s))
    {
        if let Some(record) = declared(model, site) {
            if declarations.string_imports().contains(record)
                && !found.iter().any(|(seen, _)| seen.id() == record.id())
            {
                found.push((
                    record,
                    format!("{}:{}", record.module().as_text(), record.line()),
                ));
            }
        }
    }
    found
}

/// A record that applies to nothing: the index, the id and the claim (a defect, never silent).
pub fn problems(model: &Model) -> Vec<(usize, String, String)> {
    let Some(declarations) = model.contract().declarations().as_ref() else {
        return Vec::new();
    };
    let mut found = Vec::new();
    for (index, record) in declarations.string_imports().iter().enumerate() {
        let at = (
            record.module().as_text(),
            *record.line(),
            record.target().as_text(),
        );
        let here = u64::try_from(sites_at(model, at).count()).unwrap_or(u64::MAX);
        let claim = if here == 0 {
            format!(
                "no call in {} at line {} names {} by a string: the record applies to nothing",
                at.0, at.1, at.2
            )
        } else if here != record.site_count().unwrap_or(1) {
            format!(
                "the record counts {} but the scan has {here} such calls on the line: the record applies to nothing",
                record.site_count().unwrap_or(1)
            )
        } else {
            continue;
        };
        found.push((index, record.id().as_text().to_owned(), claim));
    }
    found
}
