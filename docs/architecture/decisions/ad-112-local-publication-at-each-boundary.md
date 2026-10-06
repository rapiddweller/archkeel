# AD-112 Public means public at that boundary

The lifecycle limit below was lifted by [AD-115](ad-115-nested-api-lifecycle-uses-local-evidence.md)
for nested contracts with a local `interface_boundary` rule.

Requiring a parent's `public` list to equal all child lists forced internal sibling APIs
onto the outward API. Remove that equality, not the boundary checks (#170).

Each contract level declares its own API. An internal worker may use a child API; an outside
caller still needs the parent to publish that entry or a proven facade reexport. A parent
facade or executable `__init__.py` need not belong to a child. Child permissions never override
ancestor restrictions, and source ownership stays contained and unambiguous.

```mermaid
flowchart LR
    Caller[Outside caller] --> Facade[Parent public facade]
    subgraph Parent
        Facade --> API[Child local API]
        Worker[Sibling worker] --> API
    end
```

Inside validation reuses the existing reference checks for namespace, provenance and
`public`/`planned` ownership and underscore names. A local `interface_boundary` also rejects
public entries whose modules were not scanned. Diagnostics point to the mounted entry.
It does not add general unused-public or unbuilt-package checks. Schema 2.1.0 stays unchanged;
old `inside.public_mismatch` results remain readable, but new validation never emits that code.

Nested unused-public and planned-promotion diagnostics (#182) need level-specific importer and facade
type evidence. Reusing the root's global usage index would misclassify parent facades and leak
unrelated usage. Those lifecycle diagnostics remain root-only; local private imports are still
checked by the declared interface rule. Missing symbol records do not prove a missing constant.

Migration: review copied child entries; keep outward publication explicit. ArchKeel's analyzer
inside listed `archkeel.analyzer` under orchestration, which does not own it. Remove the duplicate;
the root still publishes `archkeel.analyzer`. Ownership and dependency permissions do not widen.

Evidence: `test_inside_publication.py`, `test_inside_rule_parity.py` and the executable
local-publication demo. Recursive loading and rule evaluation remain AD-110/AD-111.
