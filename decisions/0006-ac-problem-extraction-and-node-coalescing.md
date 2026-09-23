# ADR 0006: AC Circuit Problem Extraction and Node Coalescing

## Status
Accepted

## Context
Translating an `IngestedCircuit` into an `ACSolverProblem` requires resolving physical and topological transformations specific to the mid-band small-signal regime:
1. Constant DC bias supply rails ($V_{CC}$, $V_{DD}$) have zero incremental signal variation and must be mapped to AC virtual grounds ($0\text{V}$).
2. Coupling and bypass capacitors specified with `ac_behavior: short_circuit` must coalesce the nodes they bridge into single electrical nodes.
3. Bypass capacitors short out parallel branches (e.g. an emitter resistor $R_E$ in parallel with a bypass capacitor $C_E$ where both terminals coalesce to ground), which must be eliminated from active AC resistive branches.
4. Active transistors must be populated with small-signal hybrid-$\pi$ parameters ($g_m, r_\pi, r_o$) derived either from prior DC operating point analysis or explicit parameters in `specs.given`.
5. The extracted problem must support immediate human verification via CLI inspection (`aicione inspect-ac`).

## Decision
1. **Automated Two-Regime Extraction Workflow**:
   - Implement `extract_ac_problem(ingested, dc_solution=None, vt=0.026)` in `aicione/solver/extractor.py`.
   - If `dc_solution` is omitted and the circuit contains active devices, the extractor automatically invokes `extract_dc_problem` and `solve_dc` to determine the quiescent operating point ($g_m, r_\pi, r_o$).
2. **Disjoint-Set (Union-Find) Node Coalescing**:
   - Maintain a Union-Find structure across all nodes bridged by capacitors with `ac_behavior: short_circuit`.
   - Apply strict root priority during union: fixed references (`GND`, virtual supply rails) dominate, followed by external terminal nodes (`input`, `output`), over internal nodes.
   - Build a `node_aliases` mapping from coalesced nodes to canonical representatives.
   - Automatically eliminate resistors whose canonical terminals are identical ($node_a == node_b$), correctly modeling bypass effects.
3. **Linearized Parameter Precedence**:
   - Precedence: explicit `specs.given` parameters > solved `DCSolution` operating point parameters > symbolic literal fallbacks (`"gm_Q"`, `"rpi_Q"`).
4. **CLI Inspection (`aicione inspect-ac`)**:
   - Add `inspect-ac` subcommand to visualize AC node potentials, coalesced aliases, linearized hybrid-$\pi$ parameters, and test excitations.

## Consequences
- Establishes a seamless, automated bridge from DC operating-point analysis to AC small-signal modeling.
- Correctly collapses bypassed nodes and eliminates redundant shorted branches without manual netlist manipulation.
- Produces a minimal, canonical mathematical network ready for SymPy analytical solving.
