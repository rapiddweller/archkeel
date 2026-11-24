// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The wrapper of the case `deref`: its `Deref` target is the type of `b`.

pub struct W;

static TARGET: crate::deref_b::X = crate::deref_b::X;

impl std::ops::Deref for W {
    type Target = crate::deref_b::X;
    fn deref(&self) -> &crate::deref_b::X {
        &TARGET
    }
}
