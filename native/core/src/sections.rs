// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Sections` request: the rows of each requested section, or the reason that it has none.
//! Slice S1 writes the rows of `modules` and `packages` here.

use std::collections::BTreeMap;

use archkeel_model::{Model, Reason, Rows, Section};

/// One requested section and its rows or the reason that it has none.
pub(crate) type SectionAnswer = (Section, Result<Rows, Reason>);

pub(crate) fn answer(model: &Result<Model, Reason>, sections: &[Section]) -> Vec<SectionAnswer> {
    sections
        .iter()
        .map(|section| {
            let rows = match model {
                Ok(model) => model.rows(*section),
                Err(reason) => Err(reason.clone()),
            };
            (*section, rows)
        })
        .collect()
}

/// The reason of each section that has no rows.
pub(crate) fn unsupported(answers: Vec<SectionAnswer>) -> BTreeMap<&'static str, String> {
    answers
        .into_iter()
        .map(|(section, rows)| match rows {
            Ok(rows) => match rows {},
            Err(reason) => (section.name(), reason.to_string()),
        })
        .collect()
}
