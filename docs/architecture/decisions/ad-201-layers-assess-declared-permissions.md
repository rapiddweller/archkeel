# AD-201 Layers assess declared permissions

Treat component layers as authored intent, separate from ownership and observed
relationships. `layer_order` evaluates declared permissions, even without imports:
inner-to-outer fails; equal and reverse directions are allowed. Missing affected
layers remain UNKNOWN. `complete_requires` still evaluates actual imports.

Authenticate root or mounted declaration bytes before assessment; missing or changed
bytes retain UNKNOWN. Absent fields preserve old encodings, and older graph/report
formats remain readable without the new vocabulary.

[Layer proof](../../../tests/test_layers.py).
