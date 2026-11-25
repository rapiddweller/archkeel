// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `derefc`.

pub struct W;

impl std::ops::Deref for W {
    type Target = ();
    fn deref(&self) -> &() {
        crate::api::hit(45);
        &()
    }
}
