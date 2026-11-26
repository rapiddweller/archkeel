// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module whose surface the collector cannot read, as an import states it (#2089).

use archkeel_facts::vocab::RouteWithheld::{Escaped, OutsideWrite, UnreadAll};

use crate::imports::Import;

impl Import {
    /// The module whose surface the collector cannot read, and the word of the cause, when this
    /// import states one: `unread_all`, `outside_write` or `escaped`. The survey writes no symbol
    /// record for such a module.
    pub fn opaque_surface(&self) -> Option<(&str, &'static str)> {
        match self.route_withheld()? {
            (cause @ (UnreadAll | OutsideWrite | Escaped), Some(module)) => {
                Some((module.as_str(), cause.as_str()))
            }
            _ => None,
        }
    }
}
