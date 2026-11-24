// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `cfg_feature_only_fb`: it makes a value that a cfg set creates.

pub fn run() {
    drop(crate::cfg_feature_only_fb_c::make());
}
