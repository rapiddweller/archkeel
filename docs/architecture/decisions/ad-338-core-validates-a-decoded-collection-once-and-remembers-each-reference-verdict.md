# AD-338 Core validates a decoded collection once and remembers each reference verdict

**Decision.** `decode_response` validates the facts of a collection. Core does not validate the
same object again. The host remembers each verdict on a reference excerpt. This is a part of
epic #880: the host did the same check many times on the same bytes.

**Problem (measured, one run each).** `evaluate_source` validated again the object that the
decoder had validated. TypeScript on excalidraw: 3 calls, 1 object. Python on fastapi: 4 calls,
2 objects, and the full facts 3 times. `source_reference_context` ran 6 820 times for 1 125
distinct inputs on fastapi, and 16 510 times for 2 817 on pydantic. The calls came from five
validations and from `parse_observation`. The host called `ast.parse` 23 796 times on fastapi.

1. `ir/validated_facts.py` holds the proof. `validate_decoded_facts` validates and then records
   the exact object, as `id` plus a weak reference. `is_decoded` is true only for that object.
2. Only `ir/facts_codec.py` records a proof. A test lists the users of the function.
3. `evaluate_source` calls `ensure_valid_source_facts`. It skips the check for a recorded object.
   It validates every other object: facts that a caller or a test builds, and a copy that
   `dataclasses.replace` makes from a decoded object. The copy shares its parts with the original,
   so the proof belongs to the object and not to its parts.
4. A proof can stay valid because `SourceFacts` is frozen all the way down. Each dataclass that
   it reaches is frozen, and each field is a tuple, a frozenset, a scalar or an enum. A test
   checks the type graph. `SourceFacts` has a weak-reference slot for the registry.
5. `ir/reference_context.py` holds `source_reference_context`. It is a pure function of the
   excerpt, the column and the expression. It returns an enum or `None`, never a parse tree. A
   bounded `lru_cache` of 32 768 entries keeps the verdicts. One entry costs about 350 bytes.
6. An excerpt is a source line without a length limit. The cache keeps only an excerpt and an
   expression of at most 256 characters. The measured distinct excerpt lengths are: fastapi 99.9th
   percentile 91, maximum 111; pydantic 147 and 165. A longer input is computed at each call. So
   the cache holds at most 32 768 x 2 x 256 characters: about 23 MiB.
7. A verdict that came from a `RecursionError` of `ast.parse` depends on the depth of the caller.
   It is returned but never kept. The numeric parser keeps its own older cache; this decision
   does not change it.
8. The collector calls the same pure function in `analyzer/python/references.py`, so it gets the
   same cache. The host calls it on the decoded bytes and does not trust the collector verdict.

**Rejected.**
- **A marker field on `SourceFacts`.** `dataclasses.replace` copies it, so a changed copy would
  keep its proof.
- **A wrapper type for validated facts.** Every caller of `evaluate_source` would change.
- **A cache inside one validation.** It saves little: 1.24 checks per distinct excerpt. The
  repeat is across validations (PR #918).
- **A larger cache for `parse_numeric_evidence_excerpt`.** It returns parse trees, which are
  mutable and large. The numeric parse still repeats 1.55 times on fastapi. This stays open.

**Limit.** The proof covers one process. Code in the process can still break a frozen object
with `object.__setattr__`. The threat model of the decoder is the bytes of the collector.

**Tests.** `tests/test_source_validate_once.py`.
