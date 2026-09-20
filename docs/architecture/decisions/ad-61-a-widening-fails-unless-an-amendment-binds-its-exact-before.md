# AD-61 A widening fails unless an amendment binds its exact before and after digest

`archkeel validate --against <ref>` reads the contract at that Git revision with
`check/git.py`'s `read_blob`, and `ir.widening.contract_widenings` (before, after) - a pure
function over two `ArchitectureContract` values, beside AD-52's baseline derivation - classifies
every difference as widening or narrowing. Widening is a new permission or a dropped
restriction: an `allowed_dependency` rule added, a `forbidden_dependency`, `forbidden_construct`,
`external_dependency_scope`, `complete_assignment`, `complete_external_scope`,
`complete_requires`, `no_component_cycles`, `interface_boundary` or `sibling_isolation` rule
removed; an `allowed_sources` or `exact_sources` entry gained; a `forbidden_construct` losing a
forbidden kind; `include_type_checking` relaxed from true to false; a component's `public` or
`requires` gaining an entry; a component added or removed. Narrowing is each reverse, and passes
without question. Only a rule's or a `requires` entry's `rationale`, and every `provenance`, are
neutral - free text the design calls out as such, not architecture. Everything else this module
does not name - an unrecognised rule kind's presence in either direction, a field no classifier
enumerates such as `target_symbol` or a `requires` entry's `through`, the whole of
`declarations`, the `$schema` pointer, a component's `label` or `role` - is reported as a
widening rather than passed over, because a silent "neutral" here is the exact hole issue #11
was filed against: the easiest way to make a target-first refactor "pass" is to widen the target
in the same change. `--against` composes with `--baseline` (AD-52): when both are given, the
baseline file at the compared revision is read the same way, and `ir.widening.baseline_widenings`
compares it against the one being validated (or, with `--write-baseline`, the violations about
to be written) by fingerprint - a higher count or a new fingerprint is a widening, a lower or
removed one passes silently. A baseline is exactly the file an agent would pad to make a new
violation disappear, so it is checked, not assumed clean. A widening is reported in `failures`
with exit 1, exactly the way AD-52's baseline drift is, unless `--amendment <path>` names a file
that binds this exact before/after pair: `schema/contract-amendment.schema.json`'s
`before_digest` and `after_digest`, each a SHA-256 of `ir.codec.contract_bytes`' canonical form
via the new `ir.codec.contract_digest`, the way the lock binds its own inputs. `decided_by` and
`rationale` are free text, checked for non-emptiness only, the way a rule's own `rationale` is.
`--write-amendment`, with `--decided-by` and `--rationale`, writes that file instead of checking
it, the way `--write-baseline` does; an amendment written for one change does not verify against
a different one, because its digests will not match. A missing or malformed `--amendment` file,
or an `--against` revision or its contract that cannot be read, is exit 2 with a diagnostic -
`amendment.invalid` or `against.invalid` - the way an unreadable baseline is `baseline.invalid`.
`validate` without `--against` is unchanged.

Reason: a contract that states the target architecture is only a specification for as long as it
cannot quietly move toward the code. In the target-first workflow this repository already
supports - a baseline freezes today's violations while the contract states tomorrow's shape - the
easiest way for an agent to "fix" a violation is to widen the rule that names it, or the
component field it crosses, in the same change that touches the code; today only review
convention catches that, and review convention is exactly what an agent under time pressure, or
a reviewer skimming a large diff, is worst at holding. Classifying the difference itself, against
the branch's own base, moves that judgement into the tool. Binding the amendment to both digests,
not only the contract being validated, is what AD-52's baseline does not do for itself and says
so: the baseline is compared, never authenticated, and nothing stops a change from widening it
silently; an amendment for a five-line exemption must not also authorise an unrelated
hundred-line one two commits later, so it names the exact shape of what it approved.

Rejected: modeling every rule kind and component field's narrowing direction exhaustively before
shipping, because the fail-closed default already makes an unmodeled field behave safely - as a
widening - and the cost of getting a narrowing direction wrong is only ever an amendment asked
for that a narrower reading would not have needed, never a widening let through. Hashing the
whole contract into one opaque "changed" flag instead of enumerating findings, because a reviewer
approving an amendment needs to see what it is approving, the same reason AD-52 rejected hashing
the violation fingerprint. Authenticating the amendment against `--against`'s Git revision
itself (a commit trailer, a signed tag), because the digest binding already proves it answers
this exact contract pair without adding a second, host-specific trust mechanism `check`'s Git
predicate does not need for this question. Comparing `--baseline` only when `--against` also
compares a baseline path outside the repository root, because that file has no Git history in
this repository to compare against, and refusing the run over a file `--against` cannot see would
make `--baseline` and `--against` unusable together in that one configuration for no gain; it is
simply not checked there instead. Threading the widening check through `check`'s M -> B -> E -> H
protocol, because that protocol already rejects a contract change between the accepted commit and
the candidate; this answers a different question, a branch against its base, that the protocol
was never asked.

Limit: only rationale and provenance text are neutral; a component's `label`, `role` or `inside`
changing, or any change inside `declarations`, is reported even when it is plainly cosmetic,
because this module has no classifier that could tell cosmetic from architectural there and
fail-closed forbids guessing. `through` on a `requires` entry is never modeled directionally
either, so narrowing it to fewer modules still asks for an amendment. Renaming a rule or a
component's `id` reads as one entity removed and a different one added, at whatever cost that
kind implies, rather than as the same entity renamed. The amendment carries no expiry and no
scope narrower than "this exact before/after pair": one valid amendment covers every widening
finding between those two contracts, not each finding individually.

Check: `tests/test_widening.py::test_rule_kind_widening_table`,
`tests/test_widening.py::test_component_field_widening_table`,
`tests/test_widening.py::test_rationale_and_provenance_are_neutral`,
`tests/test_widening.py::test_an_unenumerated_difference_is_treated_as_widening`,
`tests/test_widening.py::test_a_widening_with_a_valid_amendment_passes`,
`tests/test_widening.py::test_the_same_amendment_against_a_different_change_fails`,
`tests/test_widening.py::test_a_padded_baseline_entry_widens_the_contract`,
`tests/test_widening.py::test_a_shrunk_baseline_entry_is_narrowing_and_passes`,
`tests/test_widening.py::test_validate_without_against_is_unchanged` and
`tests/test_architecture_demo.py::test_against_variant_produces_the_catalogued_verdict`.
