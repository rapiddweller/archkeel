// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The named problems of the check (AD-371).

use std::fmt;

use crate::head::Status;
use crate::status::Unexplained;

/// One rule of the check that the payload breaks.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Problem {
    /// The schema version is not 2.x.y.
    SchemaVersion,
    /// The columns of one table have different lengths.
    ColumnLengths { table: &'static str },
    /// The string table is not unique and sorted by UTF-8 bytes.
    StringsNotSorted,
    /// An id lies outside its table, or -1 where the column needs a row.
    IdOutOfRange {
        column: &'static str,
        value: i64,
        size: usize,
    },
    /// An end column is not ascending or does not end at the length of its flat list.
    OffsetEnd { column: &'static str },
    /// A node parent is not an earlier node, or the first node is not the root.
    ParentOrder,
    /// A flag is neither 0 nor 1.
    FlagRange { column: &'static str },
    /// A code that this crate cannot read: it is never read as clean.
    UnknownCode { list: &'static str, value: u32 },
    /// A measure verdict does not follow value and budget.
    MeasureVerdict { row: usize },
    /// An unknown or undeclared measure names no gap.
    MeasureWithoutGap { row: usize },
    /// A measured value without budget and baseline does not name G-BUDGETS.
    MeasureWithoutBudgetGap { row: usize },
    /// The gap list is not unique and sorted by code.
    GapsNotSorted,
    /// A row names a gap that the gap list does not hold.
    GapNotListed,
    /// `counts.cycles` or `run.not_ranked` differs from the cycle findings.
    CycleCounts,
    /// A count of the summary differs from the rows.
    Count {
        name: &'static str,
        stated: u64,
        rows: u64,
    },
    /// The stated status differs from the status rule of AD-361 point 4.
    Status { stated: Status, rule: Status },
    /// A status other than PASS has no row that explains it (AD-361 point 5).
    Unexplained(Unexplained),
    /// The violation count of a rule differs from the violation rows that cite it.
    RuleCitations {
        rule: String,
        stated: u64,
        cited: u64,
    },
    /// A rule shows PASS without an evaluator receipt (AD-117).
    PassWithoutReceipt { rule: String },
    /// An unknowns row of source `run` in a run with a Target.
    RunRowWithTarget,
    /// A row breaks the row order of its table.
    RowOrder { table: &'static str, row: usize },
    /// A forbidden pair without its deciding rule, or an undecided pair with one.
    PermissionRule { row: usize },
    /// A component edge does not carry the permission of its pair.
    EdgeTarget { edge: usize },
    /// An allowed pair has no component edge.
    AllowedWithoutEdge { row: usize },
}

impl fmt::Display for Problem {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Problem::IdOutOfRange {
                column,
                value,
                size,
            } => {
                write!(
                    formatter,
                    "{column} holds {value}, outside its table of {size} rows"
                )
            }
            Problem::Count { name, stated, rows } => {
                write!(
                    formatter,
                    "summary.counts.{name} is {stated}, the rows give {rows}"
                )
            }
            Problem::Status { stated, rule } => {
                write!(
                    formatter,
                    "summary.status {stated:?} differs from the status rule ({rule:?})"
                )
            }
            Problem::Unexplained(reason) => write!(formatter, "{reason}"),
            Problem::RuleCitations {
                rule,
                stated,
                cited,
            } => {
                write!(
                    formatter,
                    "rule {rule} counts {stated} violations, {cited} rows cite it"
                )
            }
            other => write!(formatter, "{other:?}"),
        }
    }
}
