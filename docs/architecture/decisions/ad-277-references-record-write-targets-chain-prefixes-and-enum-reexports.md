# AD-277 References record the write target, the prefix of an unresolved chain and enum re-exports

**Status.** Proposed. The owner approves it.

**Decision.** The Python reference collector (`references.py`) records more reads (#731).
1. A write target: in `<expr>.attr = x` it visits `<expr>`. `OptionKey('page_size')._value_ = x`
   records the read of `OptionKey`.
2. The prefix of an attribute chain that it does not resolve. `OptionKey.PAGE_SIZE.__dict__`
   records the member read `OptionKey.PAGE_SIZE`.
3. An enum re-export. A unique import binding of an enum class in module `M` makes `M.Name`
   the class. `from .api import OptionKey` and `api.OptionKey` resolve to the catalog owner.
4. A read in an annotation under a call has the context `unknown`, not `annotation`: the call
   runs. Example: `X: Annotated[str, keep(OptionKey.PAGE_SIZE)]`. The validator accepts `unknown`.

The `catalog_argument` policy (AD-251) uses these reads:
- Each non-annotation read of the owner must be exactly one argument of the selected operation.
- An import that the collector cannot follow is an escape: an import of the owner whose binding
  is not unique (outside `TYPE_CHECKING`); a star import of the owner module, of a module that
  imports the owner, or of a holder; a holder's module object by name (`from .api import catalog`);
  and a module import of a holder (`from . import api`, `import sample.api`). A holder is a module
  that imports the owner module as a module object (`from . import catalog`).

**Reason.** The check saw only `Owner.MEMBER`. `Owner(value)` returns the member, so a write
through it, or through a hidden read or a re-export, changed the member and still gave PASS.

**Effect on the rules.**

| Read | Rule | Before | After | Kind |
|---|---|---|---|---|
| `Owner(value)`, bare owner, owner alias | `catalog_argument` | PASS | UNKNOWN | correct |
| `print(Owner.MEMBER.value)` anywhere | `catalog_argument` | PASS | UNKNOWN | correct |
| owner call through a re-export or a star import | `catalog_argument` | PASS | UNKNOWN | correct |
| a rebound owner import in a re-exporting module | `catalog_argument` | PASS | UNKNOWN | strict |
| `api.catalog.Owner(value)` through a holder | `catalog_argument` | PASS | UNKNOWN | correct |
| a module import of a holder, no owner read | `catalog_argument` | PASS | UNKNOWN | strict |
| `keep(Owner.MEMBER)` in an annotation | `catalog_argument` | PASS | UNKNOWN | correct |
| owner annotation on a wrapped signature line | `catalog_argument` | PASS | UNKNOWN | cost |
| `return Owner.MEMBER.value` | `catalog_use` | FAIL | PASS | correct |
| `Owner.MEMBER` through a re-export | `catalog_use` | FAIL | PASS | correct |
| a prefix read on a continuation line | `catalog_use` absence | FAIL | UNKNOWN | cost |
| `NAME.attr = x`, `return NAME.attr` | `source_ownership` retired `read` | PASS | FAIL | correct |

`source_ownership` is owned by AD-249. A wrapped line has a one-line excerpt that does not parse,
so the read has an unknown context. The saved-report validator derives the context from the
same excerpt, so the collector alone cannot repair it.

**Rejected.**
- Check only member reads (the #730 rule). It misses `Owner(value)`.
- Map every import, not only enum classes. It changes more rules, and no case needs it.
- Claim a context for a wrapped line in the collector only. A replay rejects it (see above).
- Count only imports with a re-export chain, without the map. It misses `api.Owner(...)`.

**Limits.** These still give PASS:
- A runtime consumer of an annotation, such as a model field `k: Owner` that converts a value.
- A module reached through a string: `sys.modules[...]`, `importlib.import_module(...)`.
- A selected operation that returns or changes its argument.

A consumer that reads members through a re-export stays UNKNOWN for `catalog_argument`, because
the collector exposes the owner there. Under `from __future__ import annotations` a call in an
annotation does not run, but its reads still give UNKNOWN.

**Check.**
- Tests: `tests/test_catalog_enum_escape_and_keyword.py` (`test_owner_*`, `test_rebound_owner_*`),
  `tests/test_catalog_policy_native.py` (`test_member_read_*`, `test_prefix_read_on_a_*`,
  `test_owner_alias_named_like_a_member_*`), `tests/test_source_ownership_policy.py`
  (`test_retired_read_counts_the_root_of_an_attribute_chain`).
- Demo rows in `fixtures/demo_catalog_entries.py`: `class-a-catalog-argument-value-lookup`,
  `class-a-catalog-argument-star-reexport`, `class-a-catalog-argument-held-module`,
  `class-a-catalog-argument-annotation-call`, `class-a-catalog-use-member-value`, and the cost row
  `class-a-catalog-argument-wrapped-annotation`.
