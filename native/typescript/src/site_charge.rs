// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bytes that the records of a file copy and hash, charged before any record is made (AD-751).
//!
//! The record of a site holds the text of its expression, and its id is a SHA-256 over that text.
//! A call chain `a.b().b()...` of n links gives n sites whose texts grow by one link each, so the
//! records of one file cost the sum of these lengths: the square of the chain. Real chains are
//! short; a generated or hostile file within the file limit can make the sum reach terabytes.

use crate::site_types::{Expression, Site};
use crate::source::Span;

/// The most bytes of expression text that the records of one file may copy and hash. The highest
/// value that a real project reaches is 181 KB (AD-751); the `sites-chained-calls` shape of
/// 20,000 calls costs 800 MB and stays below the limit.
const MAX_RECORD_TEXT: u64 = 1 << 30;

/// The sum of the expression lengths of the sites of a file, and the site with the longest one.
struct Charge {
    bytes: u64,
    longest: Option<(u64, Span)>,
}

/// The gap reason and the span of the longest site, when the file is over `MAX_RECORD_TEXT`.
pub(crate) fn over(sites: &[Site], rel: &str) -> Option<(String, Span)> {
    let charged = charge(sites);
    let (length, span) = charged
        .longest
        .filter(|_| charged.bytes > MAX_RECORD_TEXT)?;
    let reason = format!(
            "The call chain at line {} is too long to record: {} bytes of receiver text exceed the work limit of {MAX_RECORD_TEXT} (its own text has {length} bytes): {rel}",
            span.line, charged.bytes
        );
    Some((reason, span))
}

fn charge(sites: &[Site]) -> Charge {
    let mut total = Charge {
        bytes: 0,
        longest: None,
    };
    for site in sites {
        let length = match site.expression {
            Expression::Node(text) => span_of(text.start, text.end),
            Expression::Member(receiver, name) => {
                span_of(receiver.start, receiver.end) + 1 + span_of(name.start, name.end)
            }
        };
        total.bytes = total.bytes.saturating_add(length);
        if total
            .longest
            .as_ref()
            .is_none_or(|(most, _)| length > *most)
        {
            total.longest = Some((length, site.span.clone()));
        }
    }
    total
}

fn span_of(start: usize, end: usize) -> u64 {
    end.saturating_sub(start) as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    fn charged(source: &str) -> Charge {
        let parsed = crate::parse::parse(
            &mut crate::syntax::Parsers::new(),
            "a.ts",
            source.as_bytes(),
        );
        charge(&parsed.syntax.sites.sites)
    }

    #[test]
    fn a_chain_of_n_calls_costs_the_square_of_n() {
        let small = charged(&format!("a{};", ".b()".repeat(100))).bytes;
        let large = charged(&format!("a{};", ".b()".repeat(200))).bytes;
        assert!(large > 3 * small && large < 5 * small, "{small} {large}");
    }

    #[test]
    fn the_scaling_shape_of_20000_calls_stays_below_the_limit_and_200000_calls_do_not() {
        let at = |links: usize| charged(&format!("a{};", ".b()".repeat(links)));
        assert!(at(20_000).bytes < MAX_RECORD_TEXT);
        let refused = at(200_000);
        assert!(refused.bytes > MAX_RECORD_TEXT);
        assert_eq!(refused.longest.map(|(length, _)| length), Some(799_999));
    }

    #[test]
    fn plain_code_costs_its_own_length_once() {
        let charge = charged("f(x); g.h(y);");
        assert!(charge.bytes < 40);
        assert!(charge.longest.is_some());
    }
}
