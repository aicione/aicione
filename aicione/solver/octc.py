"""Open-Circuit Time Constant (OCTC) Analytical Solver Engine using SymPy.

Calculates high-frequency Thévenin resistances (Rth), individual open-circuit time constants
(tau_k = Rth_k * C_k), total sum of time constants, dominant upper cutoff frequency
(f_H = 1 / (2*pi*sum(tau))), and small-signal zeros according to ADR 0010 and CEML Decision #30.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Optional, Union

import sympy as sp

from aicione.solver.ac import _to_sympy_value
from aicione.solver.models import ACSolverProblem, CapacitorBranch


@dataclass
class OCTCTimeConstant:
    """Represents the open-circuit time constant associated with a single capacitive branch."""
    capacitor_id: str
    node_a: str
    node_b: str
    rth: Union[float, sp.Expr]
    capacitance: Union[float, sp.Expr]
    tau: Union[float, sp.Expr]
    is_internal: bool = False


@dataclass
class OCTCSolution:
    """Consolidated high-frequency solution using the OCTC method."""
    circuit_id: str
    time_constants: dict[str, OCTCTimeConstant] = field(default_factory=dict)
    total_tau: Union[float, sp.Expr] = 0.0
    f_h: Union[float, sp.Expr] = 0.0
    w_h: Union[float, sp.Expr] = 0.0
    zeros: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)


class OCTCSolver:
    """Computes Open-Circuit Time Constants and high-frequency poles/zeros."""

    def __init__(self, problem: ACSolverProblem):
        self.problem = problem

    def compute_rth(self, node_a: str, node_b: str) -> Union[float, sp.Expr]:
        """Calculates the open-circuit Thévenin resistance seen between two canonical AC nodes.

        All independent AC sources are de-energized (voltage sources shorted, current sources opened),
        all other capacitors remain open-circuits, and a 1 A test current is applied between node_b and node_a.
        """
        ca = self.problem.canonical_node(node_a)
        cb = self.problem.canonical_node(node_b)

        if ca == cb:
            return 0.0

        # 1. Setup nodal voltage variables
        voltages: dict[str, Union[float, sp.Symbol, sp.Expr]] = {}

        # Ground and fixed supply nodes are 0 V in small-signal
        for node_id, node in self.problem.nodes.items():
            if node.is_ground or node.fixed_voltage is not None:
                voltages[node_id] = _to_sympy_value(node.fixed_voltage if node.fixed_voltage is not None else 0.0)

        for node_id in self.problem.nodes:
            canon = self.problem.canonical_node(node_id)
            if canon in voltages:
                voltages[node_id] = voltages[canon]
            else:
                sym = sp.Symbol(f"v_{canon}")
                voltages[canon] = sym
                voltages[node_id] = sym

        equations: list[sp.Equality] = []
        unknowns: list[sp.Symbol] = []
        node_leaving_currents: dict[str, list[sp.Expr]] = {n: [] for n in self.problem.nodes}

        # 2. Resistors (Ohm's law)
        for r in self.problem.resistors:
            ra = self.problem.canonical_node(r.node_a)
            rb = self.problem.canonical_node(r.node_b)
            if ra == rb:
                continue
            r_val = _to_sympy_value(r.resistance)
            va = voltages[ra]
            vb = voltages[rb]
            i_branch = (va - vb) / r_val
            node_leaving_currents[ra].append(i_branch)
            node_leaving_currents[rb].append(-i_branch)

        # 3. BJTs (Linearized hybrid-pi active model)
        for q in self.problem.bjts:
            c_base = self.problem.canonical_node(q.base_node)
            c_coll = self.problem.canonical_node(q.collector_node)
            c_emit = self.problem.canonical_node(q.emitter_node)

            vb = voltages[c_base]
            vc = voltages[c_coll]
            ve = voltages[c_emit]

            gm_val = _to_sympy_value(q.gm)
            rpi_val = _to_sympy_value(q.rpi)

            v_pi = vb - ve
            i_b = v_pi / rpi_val
            node_leaving_currents[c_base].append(i_b)
            node_leaving_currents[c_emit].append(-i_b)

            i_gm = gm_val * v_pi
            node_leaving_currents[c_coll].append(i_gm)
            node_leaving_currents[c_emit].append(-i_gm)

            if q.ro is not None and str(q.ro).lower() not in ("inf", "none"):
                ro_val = _to_sympy_value(q.ro)
                i_ro = (vc - ve) / ro_val
                node_leaving_currents[c_coll].append(i_ro)
                node_leaving_currents[c_emit].append(-i_ro)

        # 4. MOSFETs (Linearized small-signal active model)
        for m in self.problem.mosfets:
            c_gate = self.problem.canonical_node(m.gate_node)
            c_drain = self.problem.canonical_node(m.drain_node)
            c_src = self.problem.canonical_node(m.source_node)

            vg = voltages[c_gate]
            vd = voltages[c_drain]
            vs = voltages[c_src]

            gm_val = _to_sympy_value(m.gm)
            v_gs = vg - vs

            i_gm = gm_val * v_gs
            node_leaving_currents[c_drain].append(i_gm)
            node_leaving_currents[c_src].append(-i_gm)

            if m.ro is not None and str(m.ro).lower() not in ("inf", "none"):
                ro_val = _to_sympy_value(m.ro)
                i_ro = (vd - vs) / ro_val
                node_leaving_currents[c_drain].append(i_ro)
                node_leaving_currents[c_src].append(-i_ro)

        # 5. De-energize Independent Sources
        for s in self.problem.sources:
            cp = self.problem.canonical_node(s.node_p)
            cn = self.problem.canonical_node(s.node_n)
            if s.is_voltage:
                # Short circuit: vp - vn = 0, with unknown current i_src
                vp = voltages[cp]
                vn = voltages[cn]
                equations.append(sp.Eq(vp - vn, 0))
                i_src = sp.Symbol(f"i_{s.id}_rth")
                unknowns.append(i_src)
                node_leaving_currents[cp].append(i_src)
                node_leaving_currents[cn].append(-i_src)
            else:
                # Open circuit: no current injected
                pass

        # 6. Apply 1 A virtual test current from cb to ca
        # (enters node ca -> -1 leaving; leaves node cb -> +1 leaving)
        if ca in node_leaving_currents:
            node_leaving_currents[ca].append(-1)
        if cb in node_leaving_currents:
            node_leaving_currents[cb].append(+1)

        # 7. Formulate KCL for canonical unknown nodes
        unknown_nodes = self.problem.get_unknown_nodes()
        for node_id in unknown_nodes:
            canon = self.problem.canonical_node(node_id)
            if canon in self.problem.nodes and self.problem.nodes[canon].is_fixed:
                continue
            currents = node_leaving_currents[canon]
            if currents:
                equations.append(sp.Eq(sp.Add(*currents), 0))
                v_sym = voltages[canon]
                if isinstance(v_sym, sp.Symbol) and v_sym not in unknowns:
                    unknowns.append(v_sym)

        # 8. Solve linear system
        solution_dict = sp.solve(equations, unknowns, dict=True)
        if not solution_dict:
            sol_set = sp.linsolve(equations, unknowns)
            sol_list = list(sol_set)
            if sol_list:
                solution_map = dict(zip(unknowns, sol_list[0]))
            else:
                raise RuntimeError(
                    f"SymPy could not solve for Thévenin resistance between '{ca}' and '{cb}'. "
                    f"Equations: {equations}"
                )
        else:
            solution_map = solution_dict[0]

        va_sol = solution_map.get(voltages[ca], voltages[ca])
        vb_sol = solution_map.get(voltages[cb], voltages[cb])
        v_diff = sp.simplify(va_sol - vb_sol)

        is_num = isinstance(v_diff, (int, float)) or (hasattr(v_diff, "is_number") and v_diff.is_number)
        if is_num:
            return abs(float(v_diff))
        return sp.Abs(v_diff)

    def solve(self) -> OCTCSolution:
        """Computes all open-circuit time constants and dominant frequency characteristics."""
        time_constants: dict[str, OCTCTimeConstant] = {}
        total_tau: Union[float, sp.Expr] = 0.0
        is_symbolic = False

        for cap in self.problem.capacitors:
            rth = self.compute_rth(cap.node_a, cap.node_b)
            c_val = _to_sympy_value(cap.capacitance)

            tau = sp.simplify(rth * c_val)
            is_num = isinstance(tau, (int, float)) or (hasattr(tau, "is_number") and tau.is_number)
            tau_val = float(tau) if is_num else tau

            if not is_num:
                is_symbolic = True

            rth_val = float(rth) if (isinstance(rth, (int, float)) or (hasattr(rth, "is_number") and rth.is_number)) else rth
            c_num = float(c_val) if (isinstance(c_val, (int, float)) or (hasattr(c_val, "is_number") and c_val.is_number)) else c_val

            tc = OCTCTimeConstant(
                capacitor_id=cap.id,
                node_a=cap.node_a,
                node_b=cap.node_b,
                rth=rth_val,
                capacitance=c_num,
                tau=tau_val,
                is_internal=cap.is_internal,
            )
            time_constants[cap.id] = tc
            total_tau = total_tau + tau_val

        # Dominant upper cutoff pole
        if total_tau != 0:
            w_h = sp.simplify(1 / total_tau)
            f_h = sp.simplify(w_h / (2 * sp.pi))
            if not is_symbolic and hasattr(w_h, "is_number") and w_h.is_number:
                w_h = float(w_h)
                f_h = float(f_h)
        else:
            w_h = sp.oo
            f_h = sp.oo

        # Zeros deduction
        zeros = self._deduce_zeros()

        return OCTCSolution(
            circuit_id=self.problem.circuit_id,
            time_constants=time_constants,
            total_tau=float(total_tau) if (hasattr(total_tau, "is_number") and total_tau.is_number) else total_tau,
            f_h=f_h,
            w_h=w_h,
            zeros=zeros,
        )

    def _deduce_zeros(self) -> dict[str, Union[float, sp.Expr]]:
        """Deduces high-frequency transmission zeros from feedforward/bridging capacitors."""
        zeros: dict[str, Union[float, sp.Expr]] = {}

        # 1. Source Followers / Emitter Followers with bridging input-to-output capacitance
        # E.g. Gate-to-Source (Cgs or Cext) where Vout is at Source
        for m in self.problem.mosfets:
            cg = self.problem.canonical_node(m.gate_node)
            cs = self.problem.canonical_node(m.source_node)
            gm = _to_sympy_value(m.gm)

            # Find all capacitors connected between Gate and Source
            c_gs_total: Union[float, sp.Expr] = 0.0
            for cap in self.problem.capacitors:
                ca = self.problem.canonical_node(cap.node_a)
                cb = self.problem.canonical_node(cap.node_b)
                if (ca == cg and cb == cs) or (ca == cs and cb == cg):
                    c_gs_total = c_gs_total + _to_sympy_value(cap.capacitance)

            if c_gs_total != 0:
                w_z = sp.simplify(gm / c_gs_total)
                f_z = sp.simplify(w_z / (2 * sp.pi))
                is_num = hasattr(w_z, "is_number") and w_z.is_number
                w_z_val = float(w_z) if is_num else w_z
                f_z_val = float(f_z) if is_num else f_z
                zeros["w_z_gs"] = w_z_val
                zeros["f_z_gs"] = f_z_val

        # 2. Inverting stages (Common Emitter / Common Source) with Miller bridging capacitance
        # E.g. Gate-to-Drain (Cgd) or Base-to-Collector (Cmu)
        for m in self.problem.mosfets:
            cg = self.problem.canonical_node(m.gate_node)
            cd = self.problem.canonical_node(m.drain_node)
            gm = _to_sympy_value(m.gm)

            c_gd_total: Union[float, sp.Expr] = 0.0
            for cap in self.problem.capacitors:
                ca = self.problem.canonical_node(cap.node_a)
                cb = self.problem.canonical_node(cap.node_b)
                if (ca == cg and cb == cd) or (ca == cd and cb == cg):
                    c_gd_total = c_gd_total + _to_sympy_value(cap.capacitance)

            if c_gd_total != 0:
                w_z = sp.simplify(gm / c_gd_total)
                f_z = sp.simplify(w_z / (2 * sp.pi))
                is_num = hasattr(w_z, "is_number") and w_z.is_number
                zeros["w_z_gd"] = float(w_z) if is_num else w_z
                zeros["f_z_gd"] = float(f_z) if is_num else f_z

        for q in self.problem.bjts:
            c_base = self.problem.canonical_node(q.base_node)
            c_coll = self.problem.canonical_node(q.collector_node)
            gm = _to_sympy_value(q.gm)

            c_mu_total: Union[float, sp.Expr] = 0.0
            for cap in self.problem.capacitors:
                ca = self.problem.canonical_node(cap.node_a)
                cb = self.problem.canonical_node(cap.node_b)
                if (ca == c_base and cb == c_coll) or (ca == c_coll and cb == c_base):
                    c_mu_total = c_mu_total + _to_sympy_value(cap.capacitance)

            if c_mu_total != 0:
                w_z = sp.simplify(gm / c_mu_total)
                f_z = sp.simplify(w_z / (2 * sp.pi))
                is_num = hasattr(w_z, "is_number") and w_z.is_number
                zeros["w_z_mu"] = float(w_z) if is_num else w_z
                zeros["f_z_mu"] = float(f_z) if is_num else f_z

        return zeros


def solve_octc(problem: ACSolverProblem) -> OCTCSolution:
    """Convenience helper to solve OCTC on an ACSolverProblem."""
    solver = OCTCSolver(problem)
    return solver.solve()
