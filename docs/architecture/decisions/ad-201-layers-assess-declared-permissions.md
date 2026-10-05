# AD-201 Layers assess declared permissions

Component `layer` labels are optional authored intent. They neither change
Source ownership nor infer an observed relationship. Both authenticated Target
producers carry the same values; absent fields retain old canonical encodings.

Optional `layer_order` checks declared `requires` permissions, even without an
import. The supplied order runs inner to outer: earlier-to-later fails, equal
and reverse directions are allowed. Missing affected layers remain UNKNOWN.
Existing `complete_requires` still checks actual imports.

The evaluator cites the real root or mounted contract after a digest-bound
reread. Missing or changed bytes leave the assessment UNKNOWN; the existing
trace boundary stays unchanged. Contract 2.3 and layer Graph/Report 1.2 add the
vocabulary. Graph 1.0/1.1 and report 1.0 remain readable; enum and member proofs
keep their existing semantics. Proof: `tests/test_layers.py`.
