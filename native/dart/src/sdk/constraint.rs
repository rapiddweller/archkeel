// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The full-match grammar of `collect._valid_constraint`, without regex backtracking.

use super::work::{Stop, Work};
use crate::pytext::{decimal, is_space};

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Operator {
    Caret,
    Greater,
    GreaterEqual,
    Less,
    LessEqual,
    Equal,
}

pub(super) type RawVersion<'a> = [&'a str; 3];

struct Cursor<'a, 'w> {
    rest: &'a str,
    work: &'w Work,
}

impl<'a> Cursor<'a, '_> {
    fn peek(&self) -> Result<Option<char>, Stop> {
        self.work.charge(1)?;
        Ok(self.rest.chars().next())
    }

    fn take(&mut self) -> Result<Option<char>, Stop> {
        let found = self.peek()?;
        if let Some(found) = found {
            self.rest = self.rest.get(found.len_utf8()..).ok_or(Stop::Malformed)?;
        }
        Ok(found)
    }

    fn skip(&mut self, predicate: impl Fn(char) -> bool) -> Result<(), Stop> {
        while self.peek()?.is_some_and(&predicate) {
            self.take()?;
        }
        Ok(())
    }

    fn operator(&mut self) -> Result<Operator, Stop> {
        let first = self.take()?;
        let equal = matches!(first, Some('>' | '<')) && self.peek()? == Some('=');
        if equal {
            self.take()?;
        }
        match (first, equal) {
            (Some('^'), _) => Ok(Operator::Caret),
            (Some('='), _) => Ok(Operator::Equal),
            (Some('>'), true) => Ok(Operator::GreaterEqual),
            (Some('>'), false) => Ok(Operator::Greater),
            (Some('<'), true) => Ok(Operator::LessEqual),
            (Some('<'), false) => Ok(Operator::Less),
            _ => Err(Stop::Malformed),
        }
    }

    fn digits(&mut self) -> Result<&'a str, Stop> {
        let before = self.rest;
        self.skip(|c| decimal(c).is_some())?;
        let size = before.len().saturating_sub(self.rest.len());
        if size == 0 {
            return Err(Stop::Malformed);
        }
        before.get(..size).ok_or(Stop::Malformed)
    }

    fn version(&mut self) -> Result<RawVersion<'a>, Stop> {
        let mut parts = ["", "", ""];
        for (index, part) in parts.iter_mut().enumerate() {
            self.work.charge(1)?;
            *part = self.digits()?;
            if index == 2 || self.peek()? != Some('.') {
                break;
            }
            self.take()?;
        }
        for marker in ['-', '+'] {
            self.work.charge(1)?;
            if self.peek()? != Some(marker) {
                continue;
            }
            self.take()?;
            let before = self.rest.len();
            self.skip(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-'))?;
            if before == self.rest.len() {
                return Err(Stop::Malformed);
            }
        }
        Ok(parts)
    }
}

/// Validate the whole input before converting a number, as Python does before `_constraint_floor`.
pub(super) fn constraints<'a>(
    text: &'a str,
    work: &Work,
) -> Result<Vec<(Operator, RawVersion<'a>)>, Stop> {
    work.charge(text.len())?;
    let mut cursor = Cursor { rest: text, work };
    cursor.skip(is_space)?;
    let mut result = Vec::new();
    loop {
        work.charge(1)?;
        let operator = cursor.operator()?;
        if operator == Operator::Caret && !result.is_empty() {
            return Err(Stop::Malformed);
        }
        cursor.skip(is_space)?;
        result.push((operator, cursor.version()?));
        cursor.skip(is_space)?;
        if cursor.rest.is_empty() {
            return Ok(result);
        }
        if operator == Operator::Caret {
            return Err(Stop::Malformed);
        }
        if cursor.peek()? == Some(',') {
            cursor.take()?;
            cursor.skip(is_space)?;
        }
    }
}
