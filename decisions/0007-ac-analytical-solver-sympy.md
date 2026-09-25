# ADR 0007: AC Analytical Solver using SymPy Nodal Analysis and Small-Signal Linearization

## Status
Accepted

## Context
Following the mathematical extraction of the AC small-signal network into an `ACSolverProblem` (ADR 0006), the engine needs to solve for the incremental node potentials and evaluate the behavioral transfer functions and impedances declared in `specs.find` (such as voltage gain $A_v$ and input resistance $R_{\text{in}}$).

In the mid-band frequency regime, all small-signal equivalent circuits are strictly linear. Consequently, modified nodal analysis produces an exact system of linear algebraic equations solvable deterministically and in closed form via SymPy.

## Decision
1. **Nodal Formulation with Dependent Controlled Sources**:
   - Assign fixed potentials ($0.0\text{V}$) to circuit ground and virtual supply rails.
   - Formulate Kirchhoff's Current Law (KCL) $\sum I_{\text{leaving}} = 0$ for all canonical unknown nodes.
   - Model active BJT hybrid-$\pi$ terminal currents:
     - Base: $i_b = (v_b - v_e) / r_\pi$
     - Collector: $i_c = g_m (v_b - v_e) + (v_c - v_e) / r_o$
     - Emitter: $-(i_b + i_c)$
   - Model active MOSFET small-signal terminal currents:
     - Gate: $i_g = 0$
     - Drain: $i_d = g_m (v_g - v_s) + (v_d - v_s) / r_o$
     - Source: $-i_d$
   - Formulate independent AC voltage source branch relations ($v_p - v_n = v_{\text{src}}$), introducing branch currents as linear unknowns.

2. **SymPy Linear Solving & Spec Evaluation**:
   - Solve linear equation system via `sp.solve` with fallback to `sp.linsolve`.
   - Dispatch and evaluate target functions requested in `specs.find`:
     - $A_v(V_{\text{out}}, V_{\text{in}}) = v_{\text{out}} / v_{\text{in}}$
     - $R_{\text{in}}(V_{\text{in}}, \text{GND}) = (v_{\text{in}} - v_{\text{gnd}}) / I_{\text{in}}$
     - $V_{ac}(A, B) = v_A - v_B$
   - Support both concrete numerical parameters and symbolic literals (e.g., deriving closed-form formula $A_v = -\frac{\beta (R_C \parallel R_L)}{r_\pi + (\beta + 1) R_E}$).

3. **CLI Integration**:
   - Implement `aicione solve-ac <circuit.ci>` to solve and format target specifications, node potentials, and source currents.

## Consequences
- Yields exact analytical solutions for both numeric circuits ($A_v = -1.7504$, $R_{\text{in}} = 7.635\text{ k}\Omega$) and symbolic topologies without numerical approximation errors.
- Connects the entire end-to-end pipeline: `.ci` $\to$ Validation $\to$ Ingest $\to$ DC bias $\to$ AC small-signal $\to$ Spec evaluation.
