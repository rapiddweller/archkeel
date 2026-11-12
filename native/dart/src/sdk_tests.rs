// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn missing_is_supported_but_invalid_is_not() {
    assert!(check(SdkState::Missing, Some(">=4")).message.is_none());
    assert_eq!(
        check(SdkState::Invalid, Some("^3")).message,
        Some("Dart SDK support constraint is missing or invalid")
    );
    assert_eq!(
        check(SdkState::Declared, None).message,
        Some("Dart SDK constraint is missing")
    );
}

#[test]
fn the_written_exclusive_floor_is_not_incremented() {
    assert!(check(SdkState::Declared, Some(">3.12 <4"))
        .message
        .is_none());
    assert_eq!(
        check(SdkState::Declared, Some(">2.11 <4")).message,
        Some("Dart SDK constraint is outside parser support 2.12 through 3.12")
    );
}

#[test]
fn every_input_scan_and_bound_copy_counts_work() {
    assert_eq!(check(SdkState::Declared, Some(">=3.12.0 <4")).work, 86);
}

#[test]
fn decimal_values_equal_the_oracle_for_every_code_point() {
    use crate::pytext::{decimal, ranges};
    use crate::unicode_tables::DECIMAL;
    let expected = ranges(DECIMAL);
    for (start, end) in expected {
        for code in start..=end {
            let c = char::from_u32(code).unwrap();
            assert_eq!(decimal(c), Some(u8::try_from((code - start) % 10).unwrap()));
        }
    }
    for c in ['²', 'Ⅲ', 'a', '\u{10d40}'] {
        assert_eq!(decimal(c), None);
    }
}

#[test]
fn work_and_digit_limits_never_prove_partial_support() {
    let start = std::time::Instant::now();
    let text = ">=3 ".repeat(200_000);
    assert_eq!(
        check(SdkState::Declared, Some(&text)).message,
        Some(Stop::Work.message())
    );
    let text = format!("^{}3.12", "0".repeat(version::DIGIT_LIMIT));
    assert_eq!(
        check(SdkState::Declared, Some(&text)).message,
        Some(Stop::Digits.message())
    );
    assert!(start.elapsed().as_secs() < 10);
}
