// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `cfg_feature_only_fb`.

pub struct B;

impl Drop for B {
    fn drop(&mut self) {
        crate::api::hit(68);
    }
}

pub struct Safe;
