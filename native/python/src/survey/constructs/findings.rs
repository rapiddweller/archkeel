// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the construct survey finds in the modules.

use archkeel_facts::sections::SignalFact;
use archkeel_facts::{ConstructFact, Record};

use crate::survey::support::Support;

pub(in crate::survey) struct Findings {
    pub(in crate::survey) records: Vec<Record<ConstructFact>>,
    pub(in crate::survey) signals: Vec<Record<SignalFact>>,
    pub(in crate::survey) support: Support,
    pub(in crate::survey) protocol_unchanged: bool,
}
