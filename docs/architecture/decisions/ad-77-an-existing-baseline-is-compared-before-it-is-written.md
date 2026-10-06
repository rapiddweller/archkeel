# AD-77 An existing baseline is compared before it is written

Compare an existing baseline before writing it. Initial or resolved-only debt can be written; new
fingerprints or increased counts require explicit `--accept-new`. Exit two never produces baseline
bytes. Validation without writing keeps its comparison behavior.

Count changed fingerprints once, independently of occurrence differences. This prevents accidental
debt-budget replacement. Proof: [test_baseline.py](../../../tests/test_baseline.py).
