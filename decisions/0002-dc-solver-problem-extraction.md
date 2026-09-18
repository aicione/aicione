# ADR 0002: DC Solver Problem Extraction and Mathematical Representation

## Status
Accepted

## Context
Once a CEML circuit is ingested and validated, the mathematical solver needs a clean, unambiguous representation of the circuit in the DC regime. The solver should not be burdened with YAML parsing details, non-DC elements (e.g. open capacitors), or general markup artifacts.

## Decision
1. **Mathematical Solver AST**:
   - Model the analytical problem in `aicione/solver/models.py` as a `DCSolverProblem`.
   - Classify nodes into fixed potentials (Ground = 0V, DC supplies = fixed voltage) and unknown potentials (variables to solve for).
   - Represent components as typed electrical branches (`ResistorBranch`, `DCSourceBranch`, `BJTDCDevice`, `MOSFETDCDevice`).
2. **Deterministic Extraction**:
   - Implement `extract_dc_problem(ingested: IngestedCircuit)` in `aicione/solver/extractor.py`.
   - Exclude AC-only components (capacitors are treated as open circuits; AC sources are zeroed).
   - Resolve transistor default parameters ($V_{BE} = 0.7\text{V}, h_{fe} = 100$) unless explicitly overridden in `specs.given`.
3. **Ergonomic CLI Inspection**:
   - Provide `aicione inspect-dc <circuit.ci>` to visualize the exact mathematical network extracted for DC analysis.

## Consequences
- The SymPy symbolic solver can formulate node voltage equations (KCL) directly from `DCSolverProblem` without knowing about CEML markup.
- Both numerical values and symbolic literal resistances (e.g. `R = RY`) are natively preserved and supported.
