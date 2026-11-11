// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The columnar tables of the payload (AD-361 point 2).
//!
//! Each cell is a row id, a code, a count or an id into the one string table; -1 means absent.
//! The column order of each struct is the canonical key order of the schema. Columns of one table
//! must have equal length; the check, not the type, enforces it, because a decoded payload can
//! break it.

use serde::{Deserialize, Serialize};

use crate::codes::{
    Code, Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, Measure, MeasureState,
    Permission, Reason, UnknownReason, UnknownSource, Verdict, Vis,
};

/// A row index into the table that the column names.
pub type Id = u32;
/// A row index, or -1 for absent.
pub type OptId = i64;
/// An index into `strings`.
pub type StrId = u32;
/// An index into `strings`, or -1 for absent.
pub type OptStr = i64;
/// A code of `Gap`, or -1 for absent.
pub type OptGap = i64;
/// The value of `Flag`: 0 or 1.
pub type Flag = u8;

/// The column lengths of a table, in key order, for the check.
pub(crate) trait Columns {
    fn lengths(table: &Self) -> Vec<usize>;
}

/// A columnar table: a struct of equal-length columns in canonical key order, and the length of
/// each column for the check.
macro_rules! table {
    ($(#[$doc:meta])* $name:ident { $($(#[$attr:meta])* $column:ident: $cell:ty),+ $(,)? }) => {
        $(#[$doc])*
        #[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name {
            $($(#[$attr])* pub $column: Vec<$cell>),+
        }

        impl Columns for $name {
            fn lengths(table: &$name) -> Vec<usize> {
                vec![$(table.$column.len()),+]
            }
        }
    };
}

table!(
    /// The containment tree.
    Nodes {
        level: Code<Level>,
        parent: OptId,
        key: StrId,
        name: StrId,
        path: OptStr,
        package: OptId,
        modules: u64,
        units: u64,
        fan_in: u64,
        fan_out: u64,
    }
);

table!(
    /// One row per node and measure that applies.
    Measures {
        node: Id,
        def: Code<Measure>,
        state: Code<MeasureState>,
        value: i64,
        of: i64,
        gap: OptGap,
        budget: i64,
        budget_source: OptStr,
        baseline: i64,
        baseline_source: OptStr,
        verdict: Code<Verdict>,
    }
);

table!(
    /// Definitions.
    Units {
        module: Id,
        name: StrId,
        kind: Code<Kind>,
        vis: Code<Vis>,
        line: u64,
        end_line: i64,
        parent: OptId,
        decl: StrId,
        #[serde(rename = "static")] is_static: Flag,
    }
);

table!(
    /// Enum variants.
    Variants {
        unit: Id,
        name: StrId,
    }
);

table!(
    /// Direct edges: module edges first, then component, then package.
    Edges {
        level: Code<Level>,
        from: Id,
        to: Id,
        names: u64,
        sites: u64,
        target: Code<EdgeTarget>,
        rationale: OptStr,
        omitted: u64,
        via_end: u64,
    }
);

table!(
    /// The names that cross a module edge.
    Crossings {
        edge: Id,
        name: StrId,
        kind: Code<Kind>,
        unit: OptId,
        sites: u64,
        line: i64,
        reexport: Flag,
    }
);

table!(
    /// The permission of each ordered pair of sibling components.
    Permissions {
        component: Id,
        target: Id,
        status: Code<Permission>,
        rule: OptStr,
    }
);

table!(
    /// One row per violation record.
    Violations {
        kind: StrId,
        rules_end: u64,
        subjects_end: u64,
        source_module: OptStr,
        target_module: OptStr,
        symbol: OptStr,
        source_component: OptId,
        target_component: OptId,
        evidence_end: u64,
        path: OptStr,
        line: i64,
        node: OptId,
    }
);

table!(
    /// Why a fact or a verdict is unknown.
    Unknowns {
        source: Code<UnknownSource>,
        reason: Code<UnknownReason>,
        kind: StrId,
        node: Id,
        rule: OptStr,
        detail: StrId,
    }
);

table!(
    /// Typed findings.
    Findings {
        kind: Code<FindingKind>,
        subject: Id,
        value: u64,
        pool: i64,
        absolute: i64,
        relative_permille: i64,
        disposition: Code<Disposition>,
        reason: Code<Reason>,
        carrier_total: u64,
        gap: OptGap,
    }
);

table!(
    /// The names that carry a fan-in hub.
    Carriers {
        finding: Id,
        name: StrId,
        importers: u64,
        unit: OptId,
    }
);

table!(
    /// Fields of a unit; an absent table means that fields are not collected.
    Fields {
        unit: Id,
        name: StrId,
        #[serde(rename = "type")] type_name: StrId,
        type_unit: OptId,
    }
);

table!(
    /// Parameters of a unit; an absent table means that signatures are not collected.
    Params {
        unit: Id,
        pos: i64,
        name: OptStr,
        #[serde(rename = "type")] type_name: StrId,
        type_unit: OptId,
    }
);

/// The gap of an `OptGap` cell, or `None` for -1 and for a value beyond `u32`.
pub fn opt_gap(cell: OptGap) -> Option<Code<Gap>> {
    u32::try_from(cell).ok().map(Code::raw)
}
