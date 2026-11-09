# IR owners

[AD-315](decisions/ad-315-ir-owners-are-inner-components-of-core.md) splits the `ir` component of
Core into inner components. The four owners `architecture`, `evidence`, `wire` and `views` are new.
The other six inner components existed before.

An arrow points from the importing component to the imported component. Each arrow is a `requires`
entry in [`ir.json`](contracts/ir.json). The module count is the number of modules that the
component lists in `ir.json`.

The section between the two markers is generated from `ir.json`. Do not edit it by hand.
`tests/test_ir_owners.py` fails when the section differs from the contract. To write it again, run:

```bash
ARCHKEEL_WRITE_IR_OWNER_PAGE=1 uv run python -m pytest tests/test_ir_owners.py -k owner_page_shows
```

The marked-graph check of `archkeel validate` reads the root contract only. This page uses its own
markers, so that check does not read it.

<!-- archkeel-ir-owner-graph:begin -->
| Name | Kind | Modules | Responsibility | Requires |
| --- | --- | --- | --- | --- |
| `architecture` | owner | 27 | Own the typed architecture model, contract and target graphs, structure, interfaces, lock, baseline, widening and diagnostics. | `facts`, `profiles`, `dependency-policy`, `contract-version` |
| `evidence` | owner | 6 | Own rule decisions, the trace of evidence, digests, phase timings and collection features. | `architecture`, `facts`, `facts-codec`, `dependency-policy` |
| `wire` | owner | 13 | Own strict wire conversion of contracts, baselines, observations, deltas, results and graphs. | `architecture`, `facts`, `facts-codec`, `profiles`, `contract-version`, `dependency-policy` |
| `views` | owner | 7 | Own pure projections of checked results: report graph, report projection, explore, findings, flow graph, story and view spec. | `architecture`, `evidence`, `wire`, `facts`, `dependency-policy` |
| `contract-version` | inner component | 1 | Own contract versions and the features available in each version. | none |
| `dependency-policy` | inner component | 1 | Match owned dependency selectors and exact import-port permissions. | `facts` |
| `facts` | inner component | 8 | Own language-neutral source facts, evidence identities, state, type values and typed IR vocabularies. | none |
| `facts-codec` | inner component | 8 | Strictly decode, validate and encode source facts and process envelopes. Own the bounded source path grammar shared by collection and guarded-effect replay. Intern lossless JSON strings for source and observation wire encodings. | `facts`, `protocol` |
| `profiles` | inner component | 1 | Describe language capabilities, source requirements and comparable measurements. | `facts` |
| `protocol` | inner component | 2 | Own typed request and response envelopes for collector processes. | `facts` |

```mermaid
graph TD
    n_0["architecture (27 modules)"]
    n_1["contract-version (1 module)"]
    n_2["dependency-policy (1 module)"]
    n_3["evidence (6 modules)"]
    n_4["facts (8 modules)"]
    n_5["facts-codec (8 modules)"]
    n_6["profiles (1 module)"]
    n_7["protocol (2 modules)"]
    n_8["views (7 modules)"]
    n_9["wire (13 modules)"]
    n_0 --> n_1
    n_0 --> n_2
    n_0 --> n_4
    n_0 --> n_6
    n_2 --> n_4
    n_3 --> n_0
    n_3 --> n_2
    n_3 --> n_4
    n_3 --> n_5
    n_5 --> n_4
    n_5 --> n_7
    n_6 --> n_4
    n_7 --> n_4
    n_8 --> n_0
    n_8 --> n_2
    n_8 --> n_3
    n_8 --> n_4
    n_8 --> n_9
    n_9 --> n_0
    n_9 --> n_1
    n_9 --> n_2
    n_9 --> n_4
    n_9 --> n_5
    n_9 --> n_6
```
<!-- archkeel-ir-owner-graph:end -->
