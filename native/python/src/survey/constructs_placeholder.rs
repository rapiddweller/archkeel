// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a written empty function body.

use archkeel_facts::data::PlaceholderData;
use archkeel_facts::vocab::PlaceholderForm;
use archkeel_facts::ConstructFact;

use super::Walk;
use crate::module::Location;

pub(super) fn empty(walk: &mut Walk<'_>, place: Location, evidence: String) {
    let data = PlaceholderData {
        construct: "placeholder_body".to_owned(),
        form: PlaceholderForm::Empty,
        owner: walk.owner.clone(),
    };
    walk.record(
        place,
        evidence,
        "placeholder_body",
        "placeholder_body",
        ConstructFact::PlaceholderBody(data),
    );
}
