// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnsame`: two closures with one signature from two modules; one holds the type.

pub fn other() -> Box<dyn Fn()> {
    Box::new(|| {})
}
