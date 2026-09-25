# ADR 0008: Unified Multi-Regime Pipeline and Target Specification Dispatch

## Status
Accepted

## Context
Previously, `aicione` provided separate subcommands and solvers for each physical regime: `solve-dc` for quiescent bias points (ADR 0003) and `solve-ac` for small-signal linear analysis (ADR 0007).

However, real-world analog circuit analysis is inherently multi-regime:
1. Small-signal hybrid-$\pi$ device parameters ($g_m, r_\pi, r_o$) depend directly on the DC collector/drain current ($I_C, I_D$) determined during DC quiescent analysis.
2. A single CEML circuit file (`.ci`) often declares target quantities in `specs.find` spanning both regimes (e.g., finding quiescent bias $I_C(Q1), V_{CE}(Q1)$ alongside mid-band AC performance $A_v(V_{\text{out}}, V_{\text{in}}), R_{\text{in}}(V_{\text{in}}, \text{GND})$).
3. Users and external tools require a single top-level entry point to solve an entire circuit end-to-end, producing both a formatted human-readable summary and machine-readable JSON output.

## Decision
1. **Consolidated Pipeline (`aicione.pipeline.solve_circuit`)**:
   - Ingest and validate the circuit specification using `ceml.parser` and `ceml.validator`.
   - Extract and solve the DC quiescent problem via `extract_dc_problem` and `solve_dc`.
   - Extract the AC small-signal equivalent problem via `extract_ac_problem`, automatically injecting the computed operating point parameters ($g_m = I_C / V_T$, $r_\pi = \beta / g_m$, $r_o = V_A / I_C$) into active device models.
   - Solve incremental node potentials, source currents, and AC specs via `solve_ac`.
   - Dispatch and evaluate all targets declared in `specs.find` across both regimes.
   - Encapsulate the result in a structured `CircuitSolution` dataclass.

2. **Multi-Regime Spec Dispatcher (`evaluate_find_targets`)**:
   - Parse each entry in `specs.find` by regex pattern:
     - **AC Transfer Functions & Impedances**: $A_v, R_{\text{in}}, Z_{\text{in}}, R_{\text{out}}, Z_{\text{out}}, V_{ac}$ dispatched to the AC solution.
     - **Transistor DC Bias Parameters**: $I_C(Q), I_B(Q), I_E(Q), V_{BE}(Q), V_{CE}(Q), V_{CB}(Q), g_m(Q), r_\pi(Q), r_o(Q)$ dispatched to the DC operating point record of device $Q$.
     - **DC Node Differential Potentials**: $V_{dc}(A, B) = V_A - V_B$ evaluated from DC node potentials.
     - **Bare Node Identifiers**: resolved to incremental AC potentials $v(node)$ if available, falling back to DC potentials $V(node)$.

3. **Unified CLI & Serialization (`aicione solve`)**:
   - Expose `aicione solve <circuit.ci>` as the primary user command.
   - Print an executive summary detailing:
     - Target specifications evaluated from `specs.find`.
     - DC quiescent operating points for active devices ($I_C, I_B, I_E, V_{CE}, V_{BE}, g_m, r_\pi$).
     - Non-zero AC incremental potentials.
     - Any semantic warnings emitted by the validator.
   - Add `--json` flag to emit a complete JSON dictionary (`CircuitSolution.to_dict()`) with safe conversion of SymPy numeric and symbolic expressions.

## Consequences
- Provides a seamless end-to-end user experience: a single CLI command or Python function call solves multi-stage, multi-regime electronic circuits.
- Cleanly decouples regime-specific solvers while maintaining an automated data-flow pipeline from DC bias to AC small-signal linearization.
- Completes Stage 4 of the AC Small-Signal Roadmap (ADR 0004), readying the engine for Stage 5 real-world exam circuit verification.
