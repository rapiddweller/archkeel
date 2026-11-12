// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Collection assembly from typed resolver inputs (AD-398).

use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::Record;
use serde::Serialize;

#[derive(Serialize)]
pub(crate) struct Output {
    full_scope: bool,
    gaps: Vec<Record<GapFact>>,
}

pub(crate) fn build() -> Output {
    let (_, gap) = crate::records::gap(
        ".",
        1,
        ExceptionName::UnsupportedDeclaration,
        "CollectionPending: Dart collection assembly is not complete",
        None,
    );
    Output {
        full_scope: false,
        gaps: vec![gap],
    }
}
