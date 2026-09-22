# ADR 0005: AC Small-Signal AST Modeling and Linearized Device Representations

## Status
Accepted

## Context
To formulate and solve linearized AC small-signal circuit equations in the mid-band regime, the solver requires an explicit mathematical AST (`ACSolverProblem`) distinct from the DC quiescent network (`DCSolverProblem`).

In AC small-signal analysis:
1. Constant DC bias supplies ($V_{CC}$, $V_{DD}$) act as AC virtual grounds ($v = 0\text{V}$).
2. Coupling and bypass capacitors marked with `ac_behavior: short_circuit` coalesce bridged DC nodes into a single AC node.
3. Active devices (BJTs, MOSFETs) must be replaced with their linearized equivalents (hybrid-$\pi$ model for BJTs, $g_m$-$r_o$ model for MOSFETs) parametrized by the operating bias point.
4. Both concrete numeric parameters ($g_m = 49.47\text{ mS}, r_\pi = 2.02\text{ k}\Omega$) and literal algebraic symbols (e.g. `"gm"`, `"rpi"`, `"RL"`) must be first-class citizens.

## Decision
1. **BJT Linearized Representation (`BJTHybridPiDevice`)**:
   - Model the classic hybrid-$\pi$ equivalent circuit in `aicione/solver/models.py`.
   - Node connections: `base_node`, `collector_node`, `emitter_node`.
   - Small-signal parameters:
     - `gm`: Transconductance ($g_m = I_C / V_T$).
     - `rpi`: Small-signal base-emitter resistance ($r_\pi = \beta / g_m$).
     - `ro`: Optional collector-emitter resistance ($r_o = V_A / I_C$; `None` denotes infinite resistance).
     - `cpi`, `cmu`: Optional high-frequency internal capacitances ($C_\pi, C_\mu$) for frequency-response analysis.
   - Accept `Union[float, str]` for all parameters to support algebraic derivations.

2. **MOSFET Linearized Representation (`MOSFETSmallSignalDevice`)**:
   - Model gate, drain, and source terminals.
   - Parameters: `gm` (transconductance), `ro` (drain-source channel resistance), and optional capacitances `cgs`, `cgd`.

3. **AC Source Model (`ACSourceBranch`)**:
   - Independent AC excitation source ($v_{\text{in}}$ or $i_{\text{in}}$) used to apply test signals for calculating transfer functions ($A_v$) and driving-point impedances ($R_{\text{in}}, R_{\text{out}}$).

4. **AC Problem Container (`ACSolverProblem`)**:
   - Encapsulate `nodes`, `node_aliases`, `resistors`, `sources`, `bjts`, `mosfets`, and `find_targets`.
   - Incorporate `canonical_node(node_id)` to resolve aliased/shorted nodes transparently through transitive lookup.
   - Provide `get_unknown_nodes()` to return all nodes whose AC potentials are unknown variables to solve for.

## Consequences
- Clean separation between AST mathematical modeling and equation solving.
- Preserves original component names while handling node coalescing via `node_aliases`.
- Seamlessly consumes `BJTQuiescentPoint` parameters produced by `DCSolver`.
