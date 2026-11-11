// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `declarations` object of a contract (`ContractDeclarations` in `ir/model.py`).

use crate::model::{ComponentLabel, ItemId, Package, Selector, SourcePath};
use crate::model_uml::Target;

record!(pub(crate), Capability {
    id: ItemId,
    name: String,
    label: String,
    review_order: u64,
    provenance: Vec<String>,
});

record!(pub(crate), ReviewScope {
    id: ItemId,
    label: String,
    parent_id: ItemId,
    subjects: Vec<String>,
    provenance: Vec<String>,
});

record!(pub(crate), Command {
    id: ItemId,
    command: String,
    description: String,
    provenance: Vec<String>,
});

closed_enum!(PathKind { Read, Write });

record!(
    pub(crate),
    /// A read or write path through the components (`ContractPath`).
    FlowPath {
        id: ItemId,
        label: String,
        kind: PathKind,
        steps: Vec<String>,
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A single point of truth and its owner (`ContractOwner`).
    SpotOwner {
        id: ItemId,
        label: String,
        owner: Selector,
        responsibility: String,
        provenance: Vec<String>,
    }
);

closed_enum!(Lifetime {
    Permanent,
    Migration
});

record!(
    pub(crate),
    /// A compatibility module that forwards to its target (`CompatibilityShim`).
    Compat {
        module: Package,
        target: Package,
        lifetime: Lifetime,
    }
);

closed_enum!(BudgetName {
    CycleEdges,
    PrivateCrossings,
    TypingPositions,
    CallsUnresolved,
    UntypedPrivateAccesses,
    UnknownPositions,
});

record!(pub(crate), MeasurementBudget {
    name: BudgetName,
    provenance: Vec<String>,
});

record!(pub(crate), FacadeBudget {
    component: ComponentLabel,
    max_names: u64,
    provenance: Vec<String>,
});

record!(pub(crate), CouplingBudget {
    source: ComponentLabel,
    target: ComponentLabel,
    max_names: u64,
    provenance: Vec<String>,
});

record!(
    pub(crate),
    /// One exact source file and its intended responsibility.
    ModuleTarget {
        path: SourcePath,
        responsibility: String,
    }
);

record!(
    pub(crate),
    /// The declarations. `None` keeps a list that the contract does not name out of the bytes.
    Declarations {
        capabilities: Vec<Capability>,
        review_scopes: Vec<ReviewScope>,
        public_api: Vec<Selector>,
        public_api_provenance: Vec<String>,
        public_commands: Vec<Command>,
        context_roots: Vec<String>,
        context_roots_provenance: Vec<String>,
        paths: Vec<FlowPath>,
        spot_owners: Vec<SpotOwner>,
        compat: Vec<Compat>,
        measurement_budgets: Vec<MeasurementBudget>,
        #[serde(skip_serializing_if = "Option::is_none")]
        facade_budgets: Option<Vec<FacadeBudget>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        coupling_budgets: Option<Vec<CouplingBudget>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        modules: Option<Vec<ModuleTarget>>,
        #[serde(skip_serializing_if = "Option::is_none")]
        uml: Option<Target>,
    }
);
