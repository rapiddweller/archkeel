// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `fnvalue` that passes the generic function as a value.

pub fn pick() -> fn() {
    crate::fnvalue_a::call_hit::<crate::fnvalue_b::X>
}
