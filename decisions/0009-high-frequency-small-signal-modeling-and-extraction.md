# ADR 0009: High-Frequency Small-Signal Modeling, Internal Capacitances, and AC Extraction

## Status
Accepted

## Context
In ADR 0005 and ADR 0006, `aicione` established the linearized small-signal AST and extractor for the **mid-band frequency regime**. Under mid-band assumptions:
- Large external coupling and bypass capacitors ($C_{\text{coupling}}, C_{\text{bypass}}$) are treated as perfect AC short-circuits, collapsing connected nodes into canonical equivalence sets.
- High-frequency internal junction capacitances ($C_\pi, C_\mu$ in BJTs; $C_{gs}, C_{gd}, C_{ds}$ in MOSFETs) and discrete load/compensation capacitors ($C_L, C_{\text{ext}}$) are assumed to be open circuits ($Z_C \to \infty$).

To determine frequency response limits—specifically upper cutoff frequencies ($f_H, \omega_H$), dominant poles ($F_p, W_p$), and zeros ($F_z, W_z$) as formalized in CEML Decision #30—the small-signal graph must retain and systematically model all capacitive branches active at high frequencies.

Furthermore, internal transistor capacitances can be declared explicitly in `specs.given` (e.g., `Cpi(Q1): 87p`), deduced indirectly from transition frequency ($f_T$) and collector-base capacitance ($C_\mu$), or formulated as symbolic unknowns to be solved in `specs.find` (e.g., sizing a compensation capacitor $C_{\text{ext}}$).

## Decision

1. **AST Representation — `CapacitorBranch` (`aicione/solver/models.py`)**:
   - Define a unified small-signal capacitive branch:
     ```python
     @dataclass
     class CapacitorBranch:
         id: str
         node_a: str
         node_b: str
         capacitance: Union[float, sp.Expr, str]
         is_internal: bool = False
     ```
   - Add `capacitors: list[CapacitorBranch]` to `ACSolverProblem`.
   - Both internal transistor junction capacitances and discrete external capacitors map directly to `CapacitorBranch` between canonical AC nodes.

2. **Extraction of High-Frequency Capacitive Branches (`aicione/solver/extractor.py`)**:
   - **Discrete HF Capacitors**: Parse components of type `capacitor` that do **not** declare `ac_behavior: short_circuit` (e.g., $C_L$, $C_{\text{ext}}$). Map their terminals to canonical AC nodes after coupling/bypass coalescing.
   - **BJT Internal Capacitances**:
     - Base-emitter capacitance $C_\pi$: extract between canonical base and emitter nodes as `Cpi_<device_id>`.
     - Base-collector capacitance $C_\mu$: extract between canonical base and collector nodes as `Cmu_<device_id>`.
     - Support indirect deduction: if $f_T$ and $C_\mu$ are provided but $C_\pi$ is absent, derive $C_\pi = \frac{g_m}{2\pi f_T} - C_\mu$.
   - **MOSFET Internal Capacitances**:
     - Gate-source capacitance $C_{gs}$: extract between canonical gate and source nodes as `Cgs_<device_id>`.
     - Gate-drain capacitance $C_{gd}$: extract between canonical gate and drain nodes as `Cgd_<device_id>`.
     - Drain-source capacitance $C_{ds}$: extract between canonical drain and source nodes when present.
   - **Symbolic Unknowns in `specs.find`**:
     - If a capacitance appears in `specs.find` without a numeric value in `specs.given`, instantiate a SymPy symbol `sp.Symbol(id)` as the capacitance value, enabling symbolic equation formulation and solving.

3. **CLI Inspection (`aicione inspect-ac`)**:
   - Extend `command_inspect_ac` in `aicione/cli.py` to display a dedicated section:
     `[High-Frequency Capacitive Branches (N)]`, detailing the capacitor ID, connected canonical nodes, capacitance value in engineering units (pF, fF), and distinction between discrete and internal devices.

## Consequences

- Fully models the topological and mathematical network required for high-frequency small-signal analysis.
- Unifies discrete capacitors and internal semiconductor capacitances under a single canonical data structure (`CapacitorBranch`).
- Preserves 100% backwards compatibility with mid-band analysis (where capacitive branches are omitted or open).
- Lays the direct foundation for the analytical Open-Circuit Time Constant (OCTC) solver and Laplace-domain ($sC$) nodal analysis in subsequent milestones.
