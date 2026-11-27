# AD-1264: The section list has no second copy

Status: accepted. Part of the drift-gates audit of 2026-11-27 (family C).

## Why

`Section::ALL` in `native/model/src/section.rs` lists the sections of `architecture.json` that the model
owns or compares. A test compared it with a second ordered list, `tools/dual_run_schema.json`, which a
string search read out of the file (`find("\"sections\": [")` and a split on quotes). The second list
came from the dual-run harness of the Python engine (AD-360). The harness is deleted (AD-432). Nothing
else read the file. A new section had to be written in two places, and the test only told the author
that the copies differed.

## Decision

The file `tools/dual_run_schema.json` and the equality test are deleted. The test that stays checks the
properties of `Section::ALL` itself: each name is unique, and each name maps back to its section.

## The truth the equality asserted, and where it is tested

Truth: no section name is lost or doubled, and a name that the model does not know is refused. The model
has two readers of the names. The frozen replies carry the names of the collector sections (`SectionName`
in `facts`, which refuses an unknown name). `Section::of_name` is read by the dual-run request
(`core/src/request.rs`, compiled in test and `harness` builds only). Now: the unique-and-round-trip test
(each name maps back to its section, an unknown name gives none) and `dual_run_tests.rs`
(`unknown section transitive_paths` is refused by name). The second list added no check that either
reader lacks.

## Checks

`native/model/src/model_tests.rs` (`each_section_has_a_unique_name_that_names_it_back`,
`slice_s3_owns_the_four_topology_sections`), `native/core/src/dual_run_tests.rs`.
