# Regular Git blob protocol ownership

The existing `archkeel.check.snapshot` owner recognizes the regular-file metadata
consumed by both immutable Git readers. `RegularGitBlobKind` owns exactly
`(100644, blob)` and `(100755, blob)` as byte pairs. The optional
`regular_git_blob_kind(mode: bytes, kind: bytes)` port recognizes those pairs once;
the readers keep their own path selection, payload reading and error policy.

`check.git` already depends on `check.snapshot`; the shared port follows that
existing direction. No global Git object vocabulary or new component is needed.
Paths, revisions and object IDs remain open data.

The enum placement rule authorizes only the existing snapshot module. Putting the
same enum in the Git consumer still violates the rule. Authored UML protects the
enum owner and the exact parameter/return types. Function-scoped construct rules
protect the ingress and both readers; they do not claim that every comparison in
these modules is a closed control. Tuple-valued enum members are validated by
runtime pair tests, not claimed as observed UML member-value evidence.
