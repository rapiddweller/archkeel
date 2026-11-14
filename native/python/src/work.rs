// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bound the additional CPython validation work for one file.

pub(crate) const MAX_WORK: usize = 2_000_000;

pub(crate) struct Work {
    #[cfg(any(test, feature = "dump"))]
    limit: usize,
    left: usize,
    exceeded: bool,
}

impl Work {
    pub(crate) fn new() -> Self {
        Self::with_limit(MAX_WORK)
    }

    pub(crate) fn with_limit(limit: usize) -> Self {
        Self {
            #[cfg(any(test, feature = "dump"))]
            limit,
            left: limit,
            exceeded: false,
        }
    }

    pub(crate) fn charge(&mut self, count: usize) -> bool {
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

    pub(crate) fn failure(&self) -> Option<&'static str> {
        self.exceeded
            .then_some("CPython validation work limit exceeded")
    }

    #[cfg(any(test, feature = "dump"))]
    pub(crate) fn used(&self) -> usize {
        self.limit.saturating_sub(self.left)
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

    #[test]
    fn a_configured_limit_keeps_its_own_used_count() {
        let mut work = super::Work::with_limit(9);
        assert!(work.charge(4));
        assert_eq!(work.used(), 4);
        assert!(work.charge(5));
        assert_eq!(work.used(), 9);
        assert!(!work.charge(1));
    }
}
