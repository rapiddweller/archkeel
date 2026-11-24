// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The other type of the control `generic`: the generic function runs for it.

    use crate::api::{self, Tr};

    #[derive(Default)]
pub struct Y;

    impl Tr for Y {
        fn hit(&self) {
            api::hit(14);
        }
    }
