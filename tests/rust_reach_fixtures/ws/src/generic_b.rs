// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the control `generic`: the generic function never runs for it.

    use crate::api::{self, Tr};

    #[derive(Default)]
pub struct X;

    impl Tr for X {
        fn hit(&self) {
            api::hit(13);
        }
    }
