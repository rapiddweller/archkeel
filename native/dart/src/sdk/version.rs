// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Python integers up to its 4300-digit conversion limit. No machine integer truncates a bound.

use super::constraint::RawVersion;
use super::work::{Stop, Work};
use crate::pytext::decimal;
use std::cmp::Ordering;

pub(super) const DIGIT_LIMIT: usize = 4300;

#[derive(Clone, Default, PartialEq, Eq, PartialOrd, Ord)]
struct Natural {
    width: usize,
    digits: Vec<u8>,
}

impl Natural {
    fn read(raw: &str, work: &Work) -> Result<Self, Stop> {
        let mut digits = Vec::new();
        let mut written = 0usize;
        for c in raw.chars() {
            work.charge(1)?;
            written = written.saturating_add(1);
            if written > DIGIT_LIMIT {
                return Err(Stop::Digits);
            }
            let digit = decimal(c).ok_or(Stop::Malformed)?;
            if digit != 0 || !digits.is_empty() {
                digits.push(digit);
            }
        }
        Ok(Self {
            width: digits.len(),
            digits,
        })
    }

    fn small(value: u8) -> Self {
        let digits = match value {
            0 => Vec::new(),
            1..=9 => vec![value],
            _ => vec![value / 10, value % 10],
        };
        Self {
            width: digits.len(),
            digits,
        }
    }

    fn next(&self, work: &Work) -> Result<Self, Stop> {
        work.charge(self.width)?;
        let mut digits = self.digits.clone();
        for digit in digits.iter_mut().rev() {
            work.charge(1)?;
            if *digit < 9 {
                *digit = digit.saturating_add(1);
                return Ok(Self {
                    width: digits.len(),
                    digits,
                });
            }
            *digit = 0;
        }
        work.charge(digits.len().saturating_add(1))?;
        digits.insert(0, 1);
        Ok(Self {
            width: digits.len(),
            digits,
        })
    }
}

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
pub(super) struct Version([Natural; 3]);

impl Version {
    pub(super) fn read(raw: RawVersion<'_>, work: &Work) -> Result<Self, Stop> {
        let [major, minor, patch] = raw;
        Ok(Self([
            Natural::read(major, work)?,
            Natural::read(minor, work)?,
            Natural::read(patch, work)?,
        ]))
    }

    fn cost(&self) -> usize {
        let [major, minor, patch] = &self.0;
        major
            .width
            .saturating_add(minor.width)
            .saturating_add(patch.width)
            .saturating_add(3)
    }

    pub(super) fn copy(&self, work: &Work) -> Result<Self, Stop> {
        work.charge(self.cost())?;
        Ok(self.clone())
    }

    pub(super) fn compare(&self, other: &Self, work: &Work) -> Result<Ordering, Stop> {
        work.charge(self.cost().saturating_add(other.cost()))?;
        Ok(self.cmp(other))
    }

    pub(super) fn ceiling(&self, work: &Work) -> Result<Self, Stop> {
        let [major, minor, patch] = &self.0;
        if major.width > 0 {
            Ok(Self([
                major.next(work)?,
                Natural::default(),
                Natural::default(),
            ]))
        } else if minor.width > 0 {
            Ok(Self([
                Natural::default(),
                minor.next(work)?,
                Natural::default(),
            ]))
        } else {
            Ok(Self([
                Natural::default(),
                Natural::default(),
                patch.next(work)?,
            ]))
        }
    }

    pub(super) fn supported(&self, work: &Work) -> Result<bool, Stop> {
        work.charge(self.cost().saturating_mul(2))?;
        let [major, minor, _] = &self.0;
        let pair = (major, minor);
        Ok(pair >= (&Natural::small(2), &Natural::small(12))
            && pair <= (&Natural::small(3), &Natural::small(12)))
    }
}
