# AD-321 One owner for the scope label and module membership

**Decision.** `archkeel.ir.ownership` is the one owner of two rules. It belongs to the `architecture`
owner of AD-315 and imports only `architecture_graph` and `dependency`. This is step S2 of issue
#880.

1. **The scope label.** A nested component has the key `parent:label`. `scope_key` writes it and
   `scope_names` maps each component id to its key. A missing label uses the component id.
2. **Membership.** A module belongs to a component when one component claims it at each level,
   from the root down. Two claimants own nothing, and a child owns nothing below a parent that
   owns nothing. `sole`, `owner_of`, `partition`, `scope_owners`, `containing` and
   `deepest_owners` apply this rule. `module_in_ownership` stays in `dependency` as the one
   matcher of a package or an exact module.

**Copies removed.** The key `parent:label` was written in thirteen places and the label in three
(`report_graph`, `report_projection`, `module_explore`). The same membership was computed twice
in `report_graph` and `report_projection`, and a third time in `module_explore`. `decisions` held
the walk over the enclosing components twice. `owner_of` moves from `interfaces` to `ownership`.
`levels`, `view_spec`, `report_graph`, `report_projection`, `module_explore`, `decisions` and
`check.validation.observation` now call it.

**Two copies disagreed. This decision chooses the rule.**
- `report_graph` used the entity name for a missing label. The others used the component id. The
  entity name is `namespace or label`, so it matched only by accident. The component id is the
  rule. A contract always writes a label, so only a constructed or an old graph has no label.
- `report_graph` gave a module to a child although the parent was ambiguous: two root components
  claimed it. `report_projection` did not. The contract rule is that overlapping ownership owns
  nothing, so the child gets no module. A member of a child must be a member of its parent.
  Only a contract with overlapping root claims and an inside can see this.

`module_explore` no longer builds its own owner table from the inside levels. It reads the
Target intents, as the projection does. An inside level without an intent can no longer raise
`KeyError` there.

`ArchitectureContract.component_for` calls `sole`, so the contract and the observation share the
one-claimant rule.

**Not changed.** The ownership rules in `check.evaluation.rules` count claimants per module and
add the blank `__init__.py` exception. They stay. `inside_levels` still reads the declaration
records and its tests stay. Only tests call it now, because the report reads the Target intents.
Whether to delete it is a later decision.

**Reason.** One rule with three spellings gives three answers on the first edge case. The
characterization tests of #882 pinned each copy and showed where they differ. A reader of the
contract needs one answer.

**Result.** Same rule status for every rule on `make self-validate` and on the demo fixtures. The
saved-format tests are the same. The self-observation counts 9 fewer unresolved calls (981 to 972),
because the removed code held them. The baseline of `calls_unresolved` is lowered.

**Check.** `tests/test_ownership.py` pins the API, the two chosen rules and the absence of the old
definitions. `tests/test_architecture_owner_characterization.py` keeps the other pinned cases.
`tests/test_ir_owners.py` checks the owner direction. The amendment
`ad-321-ownership-amendment.json` binds the new public module in both contracts.
