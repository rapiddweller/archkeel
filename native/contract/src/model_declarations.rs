// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `declarations` object of a contract (`ContractDeclarations` in `ir/model.py`).

use crate::model::{ComponentLabel, ItemId, Package, Selector, SourcePath};
use crate::model_uml::Target;

record!(
    pub(crate),
    /// A capability of the product.
    Capability {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The name as written.
        name: String,
        /// The name that a person reads.
        label: String,
        /// The order in which the capability is reviewed.
        review_order: u64,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A scope of the review.
    ReviewScope {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The name that a person reads.
        label: String,
        /// The id of the parent element.
        parent_id: ItemId,
        /// The subjects that the review scope covers.
        subjects: Vec<String>,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A public command.
    Command {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The command as the user types it.
        command: String,
        /// What the command does.
        description: String,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

closed_enum!(
    /// Whether a path reads or writes.
    PathKind {
        /// The path reads.
        Read,
        /// The path writes.
        Write,
    }
);

record!(
    pub(crate),
    /// A read or write path through the components (`ContractPath`).
    FlowPath {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The name that a person reads.
        label: String,
        /// The kind of the value.
        kind: PathKind,
        /// The steps of the path, in order.
        steps: Vec<String>,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A single point of truth and its owner (`ContractOwner`).
    SpotOwner {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The name that a person reads.
        label: String,
        /// The component or symbol that owns the value.
        owner: Selector,
        /// What the module is responsible for.
        responsibility: String,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

closed_enum!(
    /// How long a compatibility entry stays.
    Lifetime {
        /// The entry stays.
        Permanent,
        /// The entry stays until a migration ends.
        Migration,
    }
);

record!(
    pub(crate),
    /// A compatibility module that forwards to its target (`CompatibilityShim`).
    Compat {
        /// The module that the entry names.
        module: Package,
        /// The selector of the modules that the rule names as the other side.
        target: Package,
        /// Whether the entry is permanent or for a migration.
        lifetime: Lifetime,
    }
);

closed_enum!(
    /// The name of a measure budget.
    BudgetName {
        /// The edges that lie in a cycle.
        CycleEdges,
        /// The imports of a private name across components.
        PrivateCrossings,
        /// The positions without a type.
        TypingPositions,
        /// The calls with no proven target.
        CallsUnresolved,
        /// The accesses to a private member that no type proves.
        UntypedPrivateAccesses,
        /// The positions that the collector does not read.
        UnknownPositions,
    }
);

record!(
    pub(crate),
    /// A budget for one measure.
    MeasurementBudget {
        /// The name as written.
        name: BudgetName,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A budget for the names of one facade.
    FacadeBudget {
        /// The component that is required.
        component: ComponentLabel,
        /// The most names that the budget accepts.
        max_names: u64,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// A budget for the names that one component imports from another.
    CouplingBudget {
        /// The selector of the modules that the rule judges.
        source: ComponentLabel,
        /// The selector of the modules that the rule names as the other side.
        target: ComponentLabel,
        /// The most names that the budget accepts.
        max_names: u64,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// One exact source file and its intended responsibility.
    ModuleTarget {
        /// The path of the value.
        path: SourcePath,
        /// What the module is responsible for.
        responsibility: String,
    }
);

record!(
    pub(crate),
    /// The declarations. `None` keeps a list that the contract does not name out of the bytes.
    Declarations {
        /// The capabilities of the product.
        capabilities: Vec<Capability>,
        /// The scopes of the review.
        review_scopes: Vec<ReviewScope>,
        /// The names of the public API.
        public_api: Vec<Selector>,
        /// Where the public API comes from.
        public_api_provenance: Vec<String>,
        /// The public commands.
        public_commands: Vec<Command>,
        /// The roots that give the context of a run.
        context_roots: Vec<String>,
        /// Where the context roots come from.
        context_roots_provenance: Vec<String>,
        /// The read and write paths.
        paths: Vec<FlowPath>,
        /// The owners of single points of truth.
        spot_owners: Vec<SpotOwner>,
        /// The entries that stay for compatibility.
        compat: Vec<Compat>,
        /// The budgets of the measures.
        measurement_budgets: Vec<MeasurementBudget>,
        /// The budgets of the names of a facade.
        #[serde(skip_serializing_if = "Option::is_none")]
        facade_budgets: Option<Vec<FacadeBudget>>,
        /// The budgets of the coupling between two components.
        #[serde(skip_serializing_if = "Option::is_none")]
        coupling_budgets: Option<Vec<CouplingBudget>>,
        /// The modules that have a responsibility.
        #[serde(skip_serializing_if = "Option::is_none")]
        modules: Option<Vec<ModuleTarget>>,
        /// The declared UML target.
        #[serde(skip_serializing_if = "Option::is_none")]
        uml: Option<Target>,
    }
);
