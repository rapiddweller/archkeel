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
    ColumnLengths {
        /// The name of the table.
        table: &'static str,
    },
    /// The string table is not unique and sorted by UTF-8 bytes.
    StringsNotSorted,
    /// An id lies outside its table, or -1 where the column needs a row.
    IdOutOfRange {
        /// The name of the column.
        column: &'static str,
        /// The values of the point.
        value: i64,
        /// The size.
        size: usize,
    },
    /// An end column is not ascending or does not end at the length of its flat list.
    OffsetEnd {
        /// The name of the column.
        column: &'static str,
    },
    /// A node parent is not an earlier node, or the first node is not the root.
    ParentOrder,
    /// A flag is neither 0 nor 1.
    FlagRange {
        /// The name of the column.
        column: &'static str,
    },
    /// A code that this crate cannot read: it is never read as clean.
    UnknownCode {
        /// The name of the code list.
        list: &'static str,
        /// The code that the list does not hold.
        value: u32,
    },
    /// A measure verdict does not follow value and budget.
    MeasureVerdict {
        /// The index of the row.
        row: usize,
    },
    /// An unknown or undeclared measure names no gap.
    MeasureWithoutGap {
        /// The index of the row.
        row: usize,
    },
    /// A measured value without budget and baseline does not name G-BUDGETS.
    MeasureWithoutBudgetGap {
        /// The index of the row.
        row: usize,
    },
    /// The gap list is not unique and sorted by code.
    GapsNotSorted,
    /// A row names a gap that the gap list does not hold.
    GapNotListed,
    /// `counts.cycles` or `run.not_ranked` differs from the cycle findings.
    CycleCounts,
    /// A count of the summary differs from the rows.
    Count {
        /// The name of the count.
        name: &'static str,
        /// The count that the report states.
        stated: u64,
        /// The count of the rows that exist.
        rows: u64,
    },
    /// The stated status differs from the status rule of AD-361 point 4.
    Status {
        /// The status that the report states.
        stated: Status,
        /// The status that the rules give.
        rule: Status,
    },
    /// A status other than PASS has no row that explains it (AD-361 point 5).
    Unexplained(Unexplained),
    /// The violation count of a rule differs from the violation rows that cite it.
    RuleCitations {
        /// The id of the rule.
        rule: String,
        /// The count that the report states.
        stated: u64,
        /// The count that the rule cites.
        cited: u64,
    },
    /// A rule shows PASS without an evaluator receipt (AD-117).
    PassWithoutReceipt {
        /// The id of the rule.
        rule: String,
    },
    /// An unknowns row of source `run` in a run with a Target.
    RunRowWithTarget,
    /// A row breaks the row order of its table.
    RowOrder {
        /// The name of the table.
        table: &'static str,
        /// The index of the row that is out of order.
        row: usize,
    },
    /// A rule verdict with a reason that the verdict cannot have (PASS with `no_receipt`).
    VerdictReason {
        /// The id of the rule.
        rule: String,
    },
    /// A rule with verdict FAIL that no violation row cites (AD-361 point 5, lead decision L-23).
    FailRuleWithoutViolation {
        /// The id of the rule.
        rule: String,
    },
    /// `run.payload_budget.max_bytes` is not the budget of this version.
    PayloadBudget,
    /// A forbidden pair without its deciding rule, or an undecided pair with one.
    PermissionRule {
        /// The index of the row.
        row: usize,
    },
    /// A component edge does not carry the permission of its pair.
    EdgeTarget {
        /// The index of the edge.
        edge: usize,
    },
    /// An allowed pair has no component edge.
    AllowedWithoutEdge {
        /// The index of the row.
        row: usize,
    },
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
