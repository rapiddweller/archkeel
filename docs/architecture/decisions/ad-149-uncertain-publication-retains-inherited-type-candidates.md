# AD-149 Uncertain publication retains inherited type candidates

Retain inherited concrete-type candidates from uncertain facade routes at root
and inside scopes. Dropping them made one level call a type unused while another
reported UNKNOWN.

Only proven publication and inheritance populate `facade_types`. Validation selects
publishers from owned scanned modules, including re-export-only modules. Candidates
produce `interface.usage_unknown`, never publication permission. Existing inheritance,
ownership and mutation limits remain.

[Candidate proof](../../../tests/test_inherited_generic_facade_negative.py) and
[nested publication](../../../tests/test_inside_publication.py).
