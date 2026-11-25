// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The owner of the case `fielddrop`: it has no destructor, its field has.

pub struct Holder {
    _held: crate::fielddrop_b::D,
}

pub fn make() -> Holder {
    Holder { _held: crate::fielddrop_b::D }
}
