# ADR 0003: DC Analytical Solver using SymPy Nodal Analysis and Device Models

## Status
Accepted

## Context
Following the mathematical extraction of the circuit into a `DCSolverProblem` (ADR 0002), the system requires an analytical engine capable of computing exact DC quiescent operating points ($V_i$, $I_B$, $I_C$, $I_E$, $V_{CE}$, $V_{BE}$) and small-signal hybrid-$\pi$ parameters ($g_m$, $r_\pi$, $r_o$). The engine must seamlessly support both concrete numeric values and symbolic literals (e.g., `Vin`, `R1`, `R2`, `RX`) to produce closed-form expressions.

## Decision
1. **Equation Formulation via Nodal Analysis (KCL)**:
   - Formulate Kirchhoff's Current Law (KCL) equations $\sum I_{\text{leaving}} = 0$ for all connected, non-fixed nodes.
   - Model resistor currents using Ohm's Law $I = (V_a - V_b) / R$.
   - Support independent DC voltage sources by constraining potentials ($V_p - V_n = V_{\text{src}}$) and treating branch currents as unknowns.
   - Incorporate active-region BJT device constraints:
     - $V_B - V_E = V_{BE}$
     - $I_C = \beta \cdot I_B$
     - $I_E = I_C + I_B$
2. **SymPy Symbolic Solving Engine**:
   - Convert values into SymPy expressions or symbols (`_to_sympy_value`).
   - Solve equation systems symbolically using `sp.solve` (with fallback to `sp.linsolve`).
   - Compute hybrid-$\pi$ small-signal parameters ($g_m = I_C / V_T$, $r_\pi = \beta / g_m$, $r_o = V_A / I_C$) when numerical bias points are present ($V_T = 26\text{mV}$ room temperature default).
3. **CLI Integration**:
   - Provide `aicione solve-dc <circuit.ci>` to solve circuits and output human-readable voltages and transistor operating points.

## Consequences
- Enables exact algebraic solving for both symbolic and numerical circuits without numerical approximation errors.
- Unconnected floating nodes in the DC regime remain unconstrained symbols without over-constraining the linear solver.
- Produces a structured `DCSolution` that feeds directly into subsequent AC small-signal analysis stages.
