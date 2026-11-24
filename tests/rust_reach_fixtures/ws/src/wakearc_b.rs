// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `wakearc`: `Wake`.

pub struct X;

impl std::task::Wake for X {
    fn wake(self: std::sync::Arc<Self>) {
        crate::api::hit(47);
    }
}
