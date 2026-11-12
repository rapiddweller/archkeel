// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bounded work account and stop reasons of the SDK check (AD-387).

use crate::work::Counter;

const WORK_LIMIT: usize = 1 << 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Stop {
    Malformed,
    Work,
    Digits,
}

impl Stop {
    pub(super) fn message(self) -> &'static str {
        match self {
            Self::Malformed => "Dart SDK constraint is malformed",
            Self::Work => {
                "SdkConstraintWorkLimit: Dart SDK constraint analysis passes the work limit"
            }
            Self::Digits => {
                "SdkConstraintDigitLimit: Dart SDK version component has more than 4300 digits"
            }
        }
    }
}

pub(super) type Work = Counter<WORK_LIMIT>;

impl From<crate::work::WorkLimit> for Stop {
    fn from(_: crate::work::WorkLimit) -> Self {
        Self::Work
    }
}
