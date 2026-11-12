// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bound the additional CPython validation work for one file.

pub const MAX_WORK: usize = 2_000_000;

pub struct Work {
    left: usize,
    exceeded: bool,
}

impl Work {
    pub fn new() -> Self {
        Self {
            left: MAX_WORK,
            exceeded: false,
        }
    }

    pub fn charge(&mut self, count: usize) -> bool {
        match self.left.checked_sub(count) {
            Some(left) => {
                self.left = left;
                true
            }
            None => {
                self.left = 0;
                self.exceeded = true;
                false
            }
        }
    }

    pub fn failure(&self) -> Option<&'static str> {
        self.exceeded
            .then_some("CPython validation work limit exceeded")
    }

    #[cfg(any(test, feature = "dump"))]
    pub fn used(&self) -> usize {
        MAX_WORK.saturating_sub(self.left)
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_limit_is_inclusive_and_never_wraps() {
        let mut work = super::Work::new();
        assert!(work.charge(super::MAX_WORK));
        assert!(!work.charge(1));
        assert!(!work.charge(usize::MAX));
    }
}
