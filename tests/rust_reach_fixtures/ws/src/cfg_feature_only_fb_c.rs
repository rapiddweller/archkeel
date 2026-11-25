// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `cfg_feature_only_fb`: `B` only in `--no-default-features --features fb`.

#[cfg(all(not(feature = "fa"), feature = "fb"))]
pub fn make() -> Box<dyn std::any::Any> {
    Box::new(crate::cfg_feature_only_fb_b::B)
}

#[cfg(not(all(not(feature = "fa"), feature = "fb")))]
pub fn make() -> Box<dyn std::any::Any> {
    Box::new(crate::cfg_feature_only_fb_b::Safe)
}
