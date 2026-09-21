# ADR 0004: AC Small-Signal Solver Strategy and Implementation Roadmap

## Status
Accepted

## Context
With the DC quiescent operating point solver completed and verified (ADR 0002, ADR 0003), AI.ciOne is able to compute quiescent bias currents and voltages ($I_C, I_B, I_E, V_{CE}$) as well as small-signal hybrid-$\pi$ linearized parameters ($g_m, r_\pi, r_o$).

The next milestone is to implement the AC small-signal analytical solver in the mid-band frequency regime. This engine must resolve behavioral transfer functions and driving-point impedances requested in `specs.find`, such as voltage gain $A_v(V_{\text{out}}, V_{\text{in}})$ and input resistance $R_{\text{in}}(V_{\text{in}}, \text{GND})$.

To maintain steady momentum and strict test coverage within focused daily 30-minute development windows, the implementation is structured into five atomic, verifiable milestones.

## Decision
Adopt a 5-stage sequential roadmap for the mid-band AC solver:

1. **Stage 1 (Day 1) — AC Mathematical AST Models**:
   - Define `ACSolverProblem` and supporting mathematical structures in `aicione/solver/models.py`.
   - Model AC virtual ground nodes (mapping constant DC supply rails $V_{CC}, V_{DD}$ to $0\text{V}$).
   - Model linearized transistor subcircuits:
     - Voltage-controlled current source $g_m v_\pi$ (where $v_\pi = v_b - v_e$).
     - Small-signal input resistance $r_\pi$.
     - Output resistance $r_o$ (when finite).
   - Add unit tests verifying AC AST model instantiation and properties.

2. **Stage 2 (Day 2) — AC Circuit Problem Extractor**:
   - Implement `extract_ac_problem(ingested: IngestedCircuit, dc_solution: Optional[DCSolution] = None)` in `aicione/solver/extractor.py`.
   - Automatically solve or consume DC operating points to instantiate linearized hybrid-$\pi$ parameters.
   - Deactivate independent DC sources (voltage sources $\to$ short-circuit to ground; current sources $\to$ open-circuit).
   - Apply `ac_behavior: short_circuit` to coupling and bypass capacitors by node coalescing.
   - Add unit tests verifying extracted AC topological graphs.

3. **Stage 3 (Day 3) — SymPy Analytical AC Solver**:
   - Implement `ACSolver` and `solve_ac()` in `aicione/solver/ac.py`.
   - Formulate nodal/KCL equations incorporating active dependent current sources ($g_m v_\pi$).
   - Apply test signal excitations ($v_{\text{in}}$ or $i_{\text{test}}$) to symbolically solve:
     - Voltage gain: $A_v = v_{\text{out}} / v_{\text{in}}$
     - Input resistance: $R_{\text{in}} = v_{\text{in}} / i_{\text{in}}$
     - Output resistance: $R_{\text{out}} = v_{\text{test}} / i_{\text{test}}$ with $v_{\text{in}} = 0$.
   - Verify exact analytical formulas against `tests/fixtures/bjt_amplifier.ci`.

4. **Stage 4 (Day 4) — CLI Integration & Spec Evaluation**:
   - Add CLI subcommands in `aicione/cli.py`:
     - `aicione inspect-ac <circuit.ci>`
     - `aicione solve <circuit.ci>` (unified end-to-end execution: DC $\to$ AC $\to$ `specs.find` evaluation).
   - Implement spec dispatchers that evaluate targets in `specs.find` (e.g., `Av(Vout, Vin)`, `Rin(Vin, GND)`).
   - Add CLI test coverage in `tests/test_cli.py`.

5. **Stage 5 (Day 5) — Real-World Exam Ground-Truth Validation**:
   - Transcribe an authentic problem from Brazilian "Eletrônica III" university course material into a new `.ci` fixture.
   - Solve the circuit completely by hand as the analytical ground truth ($I_C, V_E, V_C, g_m, r_\pi, A_v, R_{\text{in}}$).
   - Execute `aicione solve` against the fixture and prove exact mathematical equivalence.
   - Finalize cycle documentation.

## Consequences
- Ensures each increment delivers functional code with 100% passing tests within a 30-minute scope.
- Decouples mid-band small-signal analysis from high-frequency capacitance effects ($C_\pi, C_\mu$), which will be tackled in subsequent frequency-response milestones.
- Validates the entire compiler/solver stack directly against real-world exam benchmarks.
