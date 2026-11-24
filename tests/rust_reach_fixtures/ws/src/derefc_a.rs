// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `derefc`: foreign code calls the `Deref` of a type of `b`.

pub fn run() -> usize {
    regdep::through(&crate::derefc_b::W)
}
