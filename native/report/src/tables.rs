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
    BudgetVerdict, Code, Disposition, EdgeTarget, FindingKind, FindingReason, Gap, Kind,
    MeasureDef, MeasureState, NodeLevel, Permission, UnknownReason, UnknownSource, Vis,
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
        /// The level of the node or the edge.
        level: Code<NodeLevel>,
        /// The index of the parent.
        parent: OptId,
        /// The key of the node, as a string id.
        key: StrId,
        /// The name of the node, as a string id.
        name: StrId,
        /// The path of the node, as an optional string id.
        path: OptStr,
        /// The index of the package node.
        package: OptId,
        /// How many modules the node holds.
        modules: u64,
        /// How many definitions the node holds.
        units: u64,
        /// How many nodes import this one.
        fan_in: u64,
        /// How many nodes this one imports.
        fan_out: u64,
    }
);

table!(
    /// One row per node and measure that applies.
    Measures {
        /// The node that the measure is for.
        node: Id,
        /// The measure.
        def: Code<MeasureDef>,
        /// The state of the measure.
        state: Code<MeasureState>,
        /// The value of the measure.
        value: i64,
        /// The size that the value is part of.
        of: i64,
        /// The gap that limits the value.
        gap: OptGap,
        /// The budget.
        budget: i64,
        /// Where the budget comes from.
        budget_source: OptStr,
        /// The baseline value.
        baseline: i64,
        /// Where the baseline comes from.
        baseline_source: OptStr,
        /// The verdict.
        verdict: Code<BudgetVerdict>,
    }
);

table!(
    /// Definitions.
    Units {
        /// The module.
        module: Id,
        /// The name of the definition, as a string id.
        name: StrId,
        /// The kind of the row.
        kind: Code<Kind>,
        /// The visibility.
        vis: Code<Vis>,
        /// The first line of the definition.
        line: u64,
        /// The last line of the definition, or -1.
        end_line: i64,
        /// The index of the parent.
        parent: OptId,
        /// The declaration as written, as a string id.
        decl: StrId,
        /// True when the definition is static.
        #[serde(rename = "static")] is_static: Flag,
    }
);

table!(
    /// Enum variants.
    Variants {
        /// The index of the enum.
        unit: Id,
        /// The name of the variant, as a string id.
        name: StrId,
    }
);

table!(
    /// Direct edges: module edges first, then component, then package.
    Edges {
        /// The level of the node or the edge.
        level: Code<NodeLevel>,
        /// The node where the edge starts.
        from: Id,
        /// The node where the edge ends.
        to: Id,
        /// How many names cross.
        names: u64,
        /// How many sites use it.
        sites: u64,
        /// True when the contract has a target.
        target: Code<EdgeTarget>,
        /// Why it exists, as the contract states it.
        rationale: OptStr,
        /// How many crossings the row omits.
        omitted: u64,
        /// The end of the via list of the edge.
        via_end: u64,
    }
);

table!(
    /// The names that cross a module edge.
    Crossings {
        /// The index of the edge.
        edge: Id,
        /// The crossing name, as a string id.
        name: StrId,
        /// The kind of the row.
        kind: Code<Kind>,
        /// The index of the definition.
        unit: OptId,
        /// How many sites use it.
        sites: u64,
        /// The line of the use, or -1.
        line: i64,
        /// True when the name is published again.
        reexport: Flag,
    }
);

table!(
    /// The permission of each ordered pair of sibling components.
    Permissions {
        /// The index of the component.
        component: Id,
        /// The sibling that is the target.
        target: Id,
        /// The status.
        status: Code<Permission>,
        /// The id of the rule.
        rule: OptStr,
    }
);

table!(
    /// One row per violation record.
    Violations {
        /// The kind of the violation, as a string id.
        kind: StrId,
        /// The end of the rule list of the row.
        rules_end: u64,
        /// The end of the subject list of the row.
        subjects_end: u64,
        /// The module that holds the import.
        source_module: OptStr,
        /// The module that the import reaches.
        target_module: OptStr,
        /// The imported name.
        symbol: OptStr,
        /// The component of the importing module.
        source_component: OptId,
        /// The component of the imported module.
        target_component: OptId,
        /// The end of the evidence list of the row.
        evidence_end: u64,
        /// The path.
        path: OptStr,
        /// The line of the evidence, or -1.
        line: i64,
        /// The node that the violation is about.
        node: OptId,
    }
);

table!(
    /// Why a fact or a verdict is unknown.
    Unknowns {
        /// The source of the run.
        source: Code<UnknownSource>,
        /// Why.
        reason: Code<UnknownReason>,
        /// The kind of the unknown record, as a string id.
        kind: StrId,
        /// The node that the unknown is about.
        node: Id,
        /// The id of the rule, when the unknown is of a rule.
        rule: OptStr,
        /// The detail text.
        detail: StrId,
    }
);

table!(
    /// Typed findings.
    Findings {
        /// The kind of the row.
        kind: Code<FindingKind>,
        /// The node that the finding is about.
        subject: Id,
        /// The value of the finding.
        value: u64,
        /// The size of the pool that the finding is ranked in.
        pool: i64,
        /// The absolute value.
        absolute: i64,
        /// The share of the pool, in parts per thousand.
        relative_permille: i64,
        /// How the finding is shown.
        disposition: Code<Disposition>,
        /// Why.
        reason: Code<FindingReason>,
        /// The total of the names that carry the finding.
        carrier_total: u64,
        /// The gap that limits the value.
        gap: OptGap,
    }
);

table!(
    /// The names that carry a fan-in hub.
    Carriers {
        /// The index of the finding.
        finding: Id,
        /// The name that carries the hub, as a string id.
        name: StrId,
        /// How many modules import the name.
        importers: u64,
        /// The index of the definition.
        unit: OptId,
    }
);

table!(
    /// Fields of a unit; an absent table means that fields are not collected.
    Fields {
        /// The index of the definition that holds the field.
        unit: Id,
        /// The name of the field, as a string id.
        name: StrId,
        /// The type of the field.
        #[serde(rename = "type")] type_name: StrId,
        /// The index of the definition of the type.
        type_unit: OptId,
    }
);

table!(
    /// Parameters of a unit; an absent table means that signatures are not collected.
    Params {
        /// The index of the definition that has the parameter.
        unit: Id,
        /// The position of the parameter, counted from 0.
        pos: i64,
        /// The name of the parameter, as an optional string id.
        name: OptStr,
        /// The type of the parameter.
        #[serde(rename = "type")] type_name: StrId,
        /// The index of the definition of the type of the parameter.
        type_unit: OptId,
    }
);

/// The gap of an `OptGap` cell, or `None` for -1 and for a value beyond `u32`.
pub fn opt_gap(cell: OptGap) -> Option<Code<Gap>> {
    u32::try_from(cell).ok().map(Code::raw)
}
