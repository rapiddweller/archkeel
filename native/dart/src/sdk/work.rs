// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bounded work account and stop reasons of the SDK check (AD-387).

use std::cell::Cell;

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

/// Each scan and copy is charged before it runs. No partial bound proves support.
#[derive(Default)]
pub(super) struct Work(Cell<usize>);

impl Work {
    pub(super) fn charge(&self, amount: usize) -> Result<(), Stop> {
        let spent = self.0.get().saturating_add(amount);
        self.0.set(spent);
        if spent > WORK_LIMIT {
            Err(Stop::Work)
        } else {
            Ok(())
        }
    }

    pub(super) fn spent(&self) -> usize {
        self.0.get()
    }
}
