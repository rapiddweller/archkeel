// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cause of a withheld route, as an import states it, for the text of a hold (#2089).

use archkeel_facts::vocab::RouteWithheld::{Escaped, OutsideWrite, UnreadAll};

use crate::imports::Import;

impl Import {
    /// The word of the cause that the collector states for the withheld route of this import
    /// (AD-1210), and the module or hop that it names, when it names one.
    pub fn withheld_cause(&self) -> Option<(&'static str, Option<&str>)> {
        let (cause, at) = self.published.withheld.as_ref()?;
        Some((cause.as_str(), at.as_deref()))
    }

    /// The module whose surface the collector cannot read, and the word of the cause, when this
    /// import states one: `unread_all`, `outside_write` or `escaped`. The survey writes no symbol
    /// record for such a module.
    pub fn opaque_surface(&self) -> Option<(&str, &'static str)> {
        match self.published.withheld.as_ref()? {
            (cause @ (UnreadAll | OutsideWrite | Escaped), Some(module)) => {
                Some((module.as_str(), cause.as_str()))
            }
            _ => None,
        }
    }
}
