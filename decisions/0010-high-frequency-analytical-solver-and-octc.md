# ADR 0010: High-Frequency Analytical Solver and Open-Circuit Time Constants (OCTC)

## Status
Accepted

## Context
In ADR 0009, `aicione` established the data structures and AC extraction logic for high-frequency small-signal capacitors (`CapacitorBranch`), mapping discrete HF capacitors ($C_L, C_{\text{ext}}$) and semiconductor internal junction capacitances ($C_\pi, C_\mu$ in BJTs; $C_{gs}, C_{gd}, C_{ds}$ in MOSFETs) between canonical AC nodes.

In analog circuit analysis, especially in standard university textbooks (Sedra & Smith, Gray & Meyer) and Brazilian "Eletrônica III" exam problems, finding the upper cutoff frequency ($f_H$) and dominant poles ($F_p, W_p$) is traditionally performed using the **Open-Circuit Time Constant (OCTC)** method (also known as the Cochrun-Simpson method).

The OCTC method provides an analytical, numerically stable, and exact first-order approximation of the dominant upper pole without the high computational complexity, numerical ill-conditioning, and high degree polynomial factoring that full Laplace-domain transfer functions $H(s)$ require for multi-stage feedback circuits.

Furthermore, CEML Decision #30 formalizes the reserved functions:
- `Fp(Vout, Vin)`: dominant pole frequency in Hertz ($f = \omega / 2\pi$)
- `Wp(Vout, Vin)`: dominant pole angular frequency in radians per second ($\omega$)
- `Fz(Vout, Vin)`: dominant zero frequency in Hertz
- `Wz(Vout, Vin)`: dominant zero angular frequency in radians per second

## Decision

1. **Analytical OCTC Engine (`aicione/solver/octc.py`)**:
   - Introduce an analytical solver class `OCTCSolver` operating on `ACSolverProblem`.
   - For each capacitive branch $k \in \text{problem.capacitors}$:
     - **De-energize independent signal sources**:
       - Independent AC voltage sources are replaced by short circuits ($v_p - v_n = 0$), adding a branch current variable $i_{\text{src}}$ to preserve KCL.
       - Independent AC current sources are replaced by open circuits ($i = 0$).
     - **Open all other capacitive branches**: All capacitors $j \neq k$ remain open-circuit branches.
     - **Inject a virtual unit test current**: Connect a test current $I_{\text{test}} = 1\text{ A}$ from canonical terminal $B_k$ to canonical terminal $A_k$.
     - **Formulate linearized nodal equations with SymPy**: Solve the linear network of resistors, active controlled sources ($g_m v_\pi, g_m v_{gs}, r_\pi, r_o$), and test source.
     - **Extract Thévenin resistance**: Calculate $R_{Th, k} = |v(A_k) - v(B_k)|$.
     - **Calculate individual time constant**: $\tau_k = R_{Th, k} \cdot C_k$.
   - Compute total sum of open-circuit time constants:
     $$\tau_{\text{sum}} = \sum_{k=1}^M \tau_k$$
   - Calculate dominant upper pole:
     $$\omega_H = \frac{1}{\tau_{\text{sum}}} \quad (\text{rad/s})$$
     $$f_H = \frac{\omega_H}{2\pi} = \frac{1}{2\pi \tau_{\text{sum}}} \quad (\text{Hz})$$

2. **Data Structures (`OCTCTimeConstant` and `OCTCSolution`)**:
   ```python
   @dataclass
   class OCTCTimeConstant:
       capacitor_id: str
       node_a: str
       node_b: str
       rth: Union[float, sp.Expr]
       capacitance: Union[float, sp.Expr]
       tau: Union[float, sp.Expr]

   @dataclass
   class OCTCSolution:
       time_constants: dict[str, OCTCTimeConstant]
       total_tau: Union[float, sp.Expr]
       f_h: Union[float, sp.Expr]
       w_h: Union[float, sp.Expr]
       zeros: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)
   ```

3. **High-Frequency Zero Extraction (`Fz`, `Wz`)**:
   - Identify bridging/feedforward capacitors across input and output nodes (such as $C_{gs}$ in source followers or $C_\mu / C_{gd}$ in common-emitter / common-source stages).
   - For source followers with gate-source capacitance $C_{gs}^*$, compute $\omega_z = \frac{g_m}{C_{gs}^*}$ and $f_z = \frac{\omega_z}{2\pi}$.
   - For inverting stages with bridging capacitance $C_{gd}$ or $C_\mu$, compute the right-half plane zero $\omega_z = \frac{g_m}{C_{\mu}}$ and $f_z = \frac{\omega_z}{2\pi}$.

4. **Integration into AC Solver and Evaluation Pipeline**:
   - `ACSolution` incorporates an optional `octc_solution: Optional[OCTCSolution]`.
   - `ACSolver` automatically invokes `OCTCSolver` whenever `problem.capacitors` contains capacitive branches.
   - `_evaluate_specs` maps:
     - `Fp(out, in)` $\to f_H$
     - `Wp(out, in)` $\to \omega_H$
     - `Fz(out, in)` $\to f_z$
     - `Wz(out, in)` $\to \omega_z$

5. **CLI and Output Formatting**:
   - `aicione solve` prints a formatted table of high-frequency time constants showing capacitor ID, terminals, $R_{Th}$, capacitance, and $\tau$, followed by $\sum \tau$ and dominant pole $f_H$ in engineering units (kHz, MHz).

## Consequences

- Delivers exact matching against textbook analytical calculations for high-frequency frequency response.
- Numerically robust and fast (each $R_{Th}$ solve is a linear DC-like system with no non-linearities or matrix polynomial factoring).
- Fully supports both numeric circuits and symbolic networks via SymPy.
- Automatically resolves `Fp` and `Wp` in `specs.find` for both single-stage and cascade multi-stage amplifiers.
