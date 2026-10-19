# Declaration and report reuse

DRY/SPOT decisions take priority; split only along coherent responsibilities.
The narrow audit found no additional duplicated rule implementation: Interface
and Requires consumers share their verdict owners; rendering consumes Core decisions.
This is a bounded observation, not proof of repository-wide absence.

Thirteen unchanged facade-declaration functions now have one cohesive owner,
separate from mount-specific type assessment. Seven unchanged Atlas evidence
functions have one projection owner. Both moves preserve ASTs and import facades.
The two graph-test modules were separated into coherent API, permission,
authentication, coverage and ownership tests: all 218 cases are preserved.
No additional size-driven splitting is planned by this checkpoint.

A broad facade memo was tested and removed. It saved 1.307 Core CPU seconds
while retaining 313,047 negative and 7,262 positive entries. Its lifetime and
plumbing were unnecessary complexity for that gain. The 58 MB difference in
the first full CLI pair was not attributable to the memo; an unchanged baseline
also varied by roughly 57 MB between runs.

The retained optimization derives module exploration once per report invocation
and shares it between the two HTML pages. Matching Core projection validation
still precedes this work. Standalone APIs remain compatible; repeated report
invocations recompute their own exploration.

LOCAL VERIFIED: frozen 1,174-file / 37-contract EE input; checkpoint `002bac4e`
versus the final working tree, Python 3.11.12, identical installed metadata,
no bytecode caches and unchanged 300-second / 256-MiB collector limits.

| Actual full CLI | Checkpoint | Final |
| --- | ---: | ---: |
| Wall, including shutdown | 82.484 s | 80.755 s |
| CPU, including waited children | 82.051 s | 80.303 s |
| OS wait4 peak RSS | 2,140,471,296 B | 2,151,727,104 B |

Wall reduction is 2.10%, a small incremental gain. RSS is not aggregate concurrent
process-tree memory; the 0.53% difference has no established cause. This is one
fresh pair, not a stability or tail-latency result. Both HTML files are byte-identical.
Reports match after only analyzer-code-digest normalization; stdout matches after
only output-path normalization. Normalized report SHA-256:
`966f02ec270b51a647209ae7fa501453a9fd3a28bd14c8a32cf6c6ee90e8aee6`.

LOCAL VERIFIED: 336 integration cases and 83 facade cases pass; lint, typing,
build and wheel/sdist smoke checks pass. The exact Contract/baseline amendment
binding passes. Native validation has 126 passing rule assessments and one
failure: 145 maintained files exceed 500 lines. It also reports 854 unresolved
calls against the unchanged 838 budget and two file-inventory gaps. The baseline
accepts none of these findings. The corrected Atlas definition mapping passes.

Astra reviewed maintainability, reliability, performance and extensibility,
including the final Contract mapping, without material findings in this package.
CI-ONLY VERIFICATION: not run. Global source-size and baseline acceptance remain open.
