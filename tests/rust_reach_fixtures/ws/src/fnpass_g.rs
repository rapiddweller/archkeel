// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `fnpass`: a generic function that another module calls coerces the closure of that module.

pub fn pack<F: Fn() + 'static>(f: F) -> Box<dyn Fn()> {
    Box::new(f)
}
