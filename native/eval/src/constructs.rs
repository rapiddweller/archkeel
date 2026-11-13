// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Forbidden construct rows. The model's matching receipt is the only absence proof (AD-408).

use std::collections::BTreeMap;

use archkeel_contract::ForbiddenConstruct;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{Model, Reason};

use crate::{ConstructViolation, Violation};

pub(crate) fn check(
    id: &str,
    rule: &ForbiddenConstruct,
    model: &Model,
) -> Result<Vec<Violation>, Reason> {
    let matches = model.graph().constructs().matches(model, rule)?;
    let mut found: BTreeMap<(String, Vec<String>, String), ConstructViolation> = BTreeMap::new();
    let mut work = 4_000_000usize;
    for matched in matches {
        work = work
            .checked_sub(1)
            .ok_or(Reason::TooManyRows("construct violations"))?;
        if !matched.known {
            continue;
        }
        let site = matched.site;
        let identity = if rule.selector().is_some() || site.evidence.is_empty() {
            vec![site.id.clone()]
        } else {
            site.evidence.clone()
        };
        let key = (site.owner.clone(), identity, site.construct.clone());
        let prefix = if rule.selector().is_some() {
            "VIO-SELECTOR"
        } else {
            "VIO"
        };
        let row = found.entry(key).or_insert_with(|| ConstructViolation {
            id: stable_id(prefix, &[Part::Text(id), Part::Text(&site.id)]),
            rule: id.to_owned(),
            source: rule.source().as_text().to_owned(),
            owner: site.owner.clone(),
            construct: site.construct.clone(),
            facts: Vec::new(),
            evidence: site.evidence.clone(),
            provenance: if rule.selector().is_some() {
                rule.head().provenance().to_vec()
            } else {
                Vec::new()
            },
            selector: rule.selector().clone(),
        });
        row.facts.push(site.id.clone());
    }
    let mut rows: Vec<Violation> = found
        .into_values()
        .map(|mut row| {
            row.facts.sort();
            row.facts.dedup();
            Violation::Construct(Box::new(row))
        })
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    Ok(rows)
}
