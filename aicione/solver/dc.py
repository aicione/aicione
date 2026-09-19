"""DC Analytical Solver Engine using SymPy.

Formulates and solves Kirchhoff's Current Law (KCL) nodal equations and active
transistor constitutive relations. Supports both numeric values and literal
symbolic expressions (e.g., 'RX', 'RS', 'beta').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

import sympy as sp

from aicione.solver.models import (
    BJTDCDevice,
    DCSolverProblem,
    DCSourceBranch,
    MOSFETDCDevice,
    ResistorBranch,
    SolverNode,
)


@dataclass
class BJTQuiescentPoint:
    """Calculated DC operating point for a BJT."""
    id: str
    ib: Union[float, sp.Expr]
    ic: Union[float, sp.Expr]
    ie: Union[float, sp.Expr]
    vbe: Union[float, sp.Expr]
    vce: Union[float, sp.Expr]
    vcb: Union[float, sp.Expr]
    gm: Optional[Union[float, sp.Expr]] = None  # Transconductance (Ic / Vt)
    rpi: Optional[Union[float, sp.Expr]] = None  # Small-signal input resistance (beta / gm)
    ro: Optional[Union[float, sp.Expr]] = None   # Output resistance (VA / Ic)


@dataclass
class DCSolution:
    """Complete analytical solution for the DC regime."""
    circuit_id: str
    node_voltages: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)
    bjt_operating_points: dict[str, BJTQuiescentPoint] = field(default_factory=dict)
    equations_solved: list[sp.Equality] = field(default_factory=list)
    unknown_symbols: list[sp.Symbol] = field(default_factory=list)


def _to_sympy_value(val: Union[float, int, str]) -> Union[float, sp.Symbol, sp.Expr]:
    """Converts a branch value (number or literal string) into a SymPy numeric or symbol."""
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    try:
        return float(val_str)
    except ValueError:
        return sp.Symbol(val_str)


class DCSolver:
    """Formulates nodal circuit equations and solves for quiescent operating points."""

    def __init__(self, problem: DCSolverProblem):
        self.problem = problem
        self.voltages: dict[str, Union[float, sp.Symbol, sp.Expr]] = {}
        self.equations: list[sp.Equality] = []
        self.unknowns: list[sp.Symbol] = []

    def _setup_node_voltages(self) -> None:
        """Assigns 0 for ground, fixed values for supply nodes, and symbols for unknowns."""
        for node_id, node in self.problem.nodes.items():
            if node.is_ground:
                self.voltages[node_id] = 0.0
            elif node.fixed_voltage is not None:
                self.voltages[node_id] = _to_sympy_value(node.fixed_voltage)
            else:
                sym = sp.Symbol(f"V_{node_id}")
                self.voltages[node_id] = sym

    def solve(self, vt: float = 0.026) -> DCSolution:
        """Formulates equations and solves the DC operating point.

        Args:
            vt: Thermal voltage in Volts (default 26mV at room temperature).
        """
        self._setup_node_voltages()

        # Dictionary tracking currents leaving each node: node_id -> list of current expressions
        node_leaving_currents: dict[str, list[sp.Expr]] = {n: [] for n in self.problem.nodes}

        # 1. Resistor branch currents (Ohm's Law: I = (V_a - V_b) / R)
        for r in self.problem.resistors:
            r_val = _to_sympy_value(r.resistance)
            va = self.voltages[r.node_a]
            vb = self.voltages[r.node_b]

            i_branch = (va - vb) / r_val
            node_leaving_currents[r.node_a].append(i_branch)
            node_leaving_currents[r.node_b].append(-i_branch)

        # 2. Independent DC Sources
        for s in self.problem.sources:
            s_val = _to_sympy_value(s.value)
            if s.is_voltage:
                # Constrains potential: V_p - V_n = value
                vp = self.voltages[s.node_p]
                vn = self.voltages[s.node_n]
                self.equations.append(sp.Eq(vp - vn, s_val))
                # Current through voltage source is an additional unknown
                i_src = sp.Symbol(f"I_{s.id}")
                self.unknowns.append(i_src)
                node_leaving_currents[s.node_p].append(i_src)
                node_leaving_currents[s.node_n].append(-i_src)
            else:
                # Current source injects s_val from p to n
                node_leaving_currents[s.node_p].append(s_val)
                node_leaving_currents[s.node_n].append(-s_val)

        # 3. BJT Active Devices (Active Mode DC Model)
        bjt_current_symbols: dict[str, tuple[sp.Symbol, sp.Symbol, sp.Symbol]] = {}
        for q in self.problem.bjts:
            ib = sp.Symbol(f"I_B_{q.id}")
            ic = sp.Symbol(f"I_C_{q.id}")
            ie = sp.Symbol(f"I_E_{q.id}")
            self.unknowns.extend([ib, ic, ie])
            bjt_current_symbols[q.id] = (ib, ic, ie)

            # Node connections
            # Current leaves base node into transistor (+ib)
            node_leaving_currents[q.base_node].append(ib)
            # Current leaves collector node into transistor (+ic)
            node_leaving_currents[q.collector_node].append(ic)
            # Current enters emitter node from transistor (-ie)
            node_leaving_currents[q.emitter_node].append(-ie)

            # Constitutive Active Region Equations:
            # 1. V_B - V_E = V_BE
            vb = self.voltages[q.base_node]
            ve = self.voltages[q.emitter_node]
            vbe_val = _to_sympy_value(q.vbe)
            self.equations.append(sp.Eq(vb - ve, vbe_val))

            # 2. I_C = beta * I_B
            hfe_val = _to_sympy_value(q.hfe)
            self.equations.append(sp.Eq(ic, hfe_val * ib))

            # 3. I_E = I_C + I_B
            self.equations.append(sp.Eq(ie, ic + ib))

        # 4. Formulate KCL for all unknown potential nodes
        for node_id, node in self.problem.nodes.items():
            if not node.is_fixed and node_id in self.problem.get_unknown_nodes():
                currents = node_leaving_currents[node_id]
                if currents:
                    kcl_eq = sp.Eq(sp.Add(*currents), 0)
                    self.equations.append(kcl_eq)
                    v_sym = self.voltages[node_id]
                    if isinstance(v_sym, sp.Symbol) and v_sym not in self.unknowns:
                        self.unknowns.append(v_sym)

        # 5. Solve System of Equations with SymPy
        solution_dict = sp.solve(self.equations, self.unknowns, dict=True)

        if not solution_dict:
            # Fallback to linsolve if linear
            sol_set = sp.linsolve(self.equations, self.unknowns)
            sol_list = list(sol_set)
            if sol_list:
                solution_map = dict(zip(self.unknowns, sol_list[0]))
            else:
                raise RuntimeError(
                    f"SymPy could not find a consistent solution for DC circuit '{self.problem.circuit_id}'. "
                    f"Equations: {self.equations}"
                )
        else:
            solution_map = solution_dict[0]

        # 6. Map solved voltages
        solved_voltages: dict[str, Union[float, sp.Expr]] = {}
        for node_id, v_val in self.voltages.items():
            if isinstance(v_val, sp.Symbol) and v_val in solution_map:
                solved_voltages[node_id] = solution_map[v_val]
            else:
                solved_voltages[node_id] = v_val

        # 7. Map solved BJT operating points
        bjt_points: dict[str, BJTQuiescentPoint] = {}
        for q in self.problem.bjts:
            ib_sym, ic_sym, ie_sym = bjt_current_symbols[q.id]
            ib_val = solution_map.get(ib_sym, 0.0)
            ic_val = solution_map.get(ic_sym, 0.0)
            ie_val = solution_map.get(ie_sym, 0.0)

            vb = solved_voltages[q.base_node]
            vc = solved_voltages[q.collector_node]
            ve = solved_voltages[q.emitter_node]

            vbe = vb - ve
            vce = vc - ve
            vcb = vc - vb

            # Small-signal parameters (gm = Ic / Vt, rpi = beta / gm)
            gm = None
            rpi = None
            ro = None

            is_ic_num = isinstance(ic_val, (int, float)) or (hasattr(ic_val, "is_number") and ic_val.is_number)
            if is_ic_num:
                ic_float = float(ic_val)
                if ic_float > 0:
                    gm = float(ic_float / vt)
                    hfe_val = q.hfe
                    is_hfe_num = isinstance(hfe_val, (int, float)) or (hasattr(hfe_val, "is_number") and hfe_val.is_number)
                    if is_hfe_num:
                        rpi = float(float(hfe_val) / gm)
                    if q.va:
                        is_va_num = isinstance(q.va, (int, float)) or (hasattr(q.va, "is_number") and q.va.is_number)
                        if is_va_num:
                            ro = float(float(q.va) / ic_float)

            bjt_points[q.id] = BJTQuiescentPoint(
                id=q.id,
                ib=ib_val,
                ic=ic_val,
                ie=ie_val,
                vbe=vbe,
                vce=vce,
                vcb=vcb,
                gm=gm,
                rpi=rpi,
                ro=ro,
            )

        return DCSolution(
            circuit_id=self.problem.circuit_id,
            node_voltages=solved_voltages,
            bjt_operating_points=bjt_points,
            equations_solved=self.equations,
            unknown_symbols=self.unknowns,
        )


def solve_dc(problem: DCSolverProblem, vt: float = 0.026) -> DCSolution:
    """Convenience function to solve a DCSolverProblem."""
    solver = DCSolver(problem)
    return solver.solve(vt=vt)
