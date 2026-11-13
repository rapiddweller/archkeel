// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Import violations of the public interface (AD-428).

use crate::Violation;
use archkeel_contract::InterfaceBoundary;
use archkeel_model::{Judged, Model};

pub(crate) fn check(id: &str, rule: &InterfaceBoundary, model: &Model) -> Vec<Violation> {
    let mut rows: Vec<_> = archkeel_model::interface_crossings(model, rule)
        .into_iter()
        .filter(|c| c.judged == Judged::Fail)
        .map(|c| {
            Violation::private_import(
                id,
                [c.source.label().as_text(), c.target.label().as_text()],
                c.import,
            )
        })
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    rows
}
