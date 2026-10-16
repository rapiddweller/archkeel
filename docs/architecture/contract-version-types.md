# Contract version ownership

ContractVersion and ContractFeature belong to the pure ir.contract_version component. The model converts valid legacy constructor input into a real ContractVersion. The JSON codec retains its existing ContractVersionError for unsupported or nontext wire input. Serialized spelling, supported versions, key ordering and canonical bytes remain unchanged.

One introduction table governs existing read and write feature gates. The codec no longer repeats growing version-string sets. Supported declaration order is the version evolution order; adding a version also updates that explicit owner, without editing every older feature branch.

The independent IR Target binds ArchitectureContract.schema_version, both enum owners, and supports(feature: ContractFeature) -> bool. Native source mutations check those annotations under fixed intent. A whole-module construct policy protects the pure version component. Remaining rule-tag, role and allowance grammar in codec_contract is a separate pending #542 responsibility; this increment does not claim that broader module is string-free.

JSON keys and supplied names remain open data. There is no parallel key enum, observation-derived Target, runtime alias-proof extension or increased debt allowance.

Verification: the integrated version/graph source passed 429 tests, Ruff and strict mypy in [the version job](https://github.com/rapiddweller/archkeel/actions/runs/38948588690/job/117133922877). Native validation and the normal amendment against the actual graph predecessor passed with 918 unresolved calls, 52 typing positions, 58 UNKNOWN and zero violations. The baseline is unchanged. Existing unsupported UML write-version behavior is not expanded by this increment.
