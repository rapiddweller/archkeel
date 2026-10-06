# AD-84 `boundary_types` follows declared facade re-exports and one field level

Follow declared facade re-exports to proven definitions. Multiple paths to one origin count once;
distinct origins remain ambiguous UNKNOWN. Check exported methods and overload surfaces with the
same proof, omitting receivers by method kind. Unknown custom bases do not justify guessed MROs.

[AD-93](ad-93-boundary-types-follow-owned-dto-fields.md) extends the original one-field-depth read.
Proof: [test_boundary_types_facades.py](../../../tests/test_boundary_types_facades.py).
