// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The SDK support gate of `collect._Collection._sdk_constraints` (AD-385).

mod constraint;
mod version;
mod work;

use std::cmp::Ordering;

use crate::pubspec::SdkState;
use constraint::{constraints, Operator};
use version::Version;
use work::{Stop, Work};

pub(crate) struct Support {
    pub(crate) message: Option<&'static str>,
    pub(crate) work: usize,
}

/// Return no message only when Python leaves `sdk_supported` true.
pub(crate) fn check(state: SdkState, value: Option<&str>) -> Support {
    let work = Work::default();
    let message = match (state, value) {
        (SdkState::Missing, _) => None,
        (SdkState::Invalid, _) => Some("Dart SDK support constraint is missing or invalid"),
        (SdkState::Declared, None) => Some("Dart SDK constraint is missing"),
        (SdkState::Declared, Some(value)) => match supported(value, &work) {
            Ok(message) => message,
            Err(stop) => Some(stop.message()),
        },
    };
    Support {
        message,
        work: work.spent(),
    }
}

struct Bound {
    version: Version,
    inclusive: bool,
}

/// `_tighter_lower` and `_tighter_upper`: equal bounds keep both inclusion tests.
fn tighten(
    current: &mut Option<Bound>,
    candidate: Bound,
    lower: bool,
    work: &Work,
) -> Result<(), Stop> {
    let Some(old) = current else {
        *current = Some(candidate);
        return Ok(());
    };
    let order = candidate.version.compare(&old.version, work)?;
    match order {
        Ordering::Equal => old.inclusive &= candidate.inclusive,
        Ordering::Greater if lower => *old = candidate,
        Ordering::Less if !lower => *old = candidate,
        _ => {}
    }
    Ok(())
}

fn supported(value: &str, work: &Work) -> Result<Option<&'static str>, Stop> {
    let parsed = constraints(value, work)?;
    let mut lower = None;
    let mut upper = None;
    for (operator, raw) in parsed {
        work.charge(1)?;
        let version = Version::read(raw, work)?;
        match operator {
            Operator::Caret => {
                let ceiling = version.ceiling(work)?;
                tighten(
                    &mut lower,
                    Bound {
                        version,
                        inclusive: true,
                    },
                    true,
                    work,
                )?;
                tighten(
                    &mut upper,
                    Bound {
                        version: ceiling,
                        inclusive: false,
                    },
                    false,
                    work,
                )?;
            }
            Operator::Equal => {
                let copied = version.copy(work)?;
                tighten(
                    &mut lower,
                    Bound {
                        version,
                        inclusive: true,
                    },
                    true,
                    work,
                )?;
                tighten(
                    &mut upper,
                    Bound {
                        version: copied,
                        inclusive: true,
                    },
                    false,
                    work,
                )?;
            }
            Operator::Greater | Operator::GreaterEqual => {
                tighten(
                    &mut lower,
                    Bound {
                        version,
                        inclusive: operator == Operator::GreaterEqual,
                    },
                    true,
                    work,
                )?;
            }
            Operator::Less | Operator::LessEqual => {
                tighten(
                    &mut upper,
                    Bound {
                        version,
                        inclusive: operator == Operator::LessEqual,
                    },
                    false,
                    work,
                )?;
            }
        }
    }
    let unproven = Some("Dart SDK constraint does not prove support within 2.12 through 3.12");
    let Some(lower) = lower else {
        return Ok(unproven);
    };
    if let Some(upper) = upper {
        let order = lower.version.compare(&upper.version, work)?;
        if order == Ordering::Greater
            || (order == Ordering::Equal && !(lower.inclusive && upper.inclusive))
        {
            return Ok(unproven);
        }
    }
    if lower.version.supported(work)? {
        Ok(None)
    } else {
        Ok(Some(
            "Dart SDK constraint is outside parser support 2.12 through 3.12",
        ))
    }
}

#[cfg(test)]
#[path = "sdk_tests.rs"]
mod tests;
