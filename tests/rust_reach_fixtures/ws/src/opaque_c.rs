// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The function of the case `opaque` that hides the type behind `impl Tr`.

use crate::api::Tr;

pub fn make() -> impl Tr {
    crate::opaque_b::X
}
