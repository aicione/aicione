"""AC Small-Signal Analytical Solver Engine using SymPy.

Formulates and solves Kirchhoff's Current Law (KCL) nodal equations in the mid-band
small-signal regime using linearized active device models (hybrid-pi for BJT, gm-ro for MOSFET).
Evaluates transfer functions (Av) and driving-point impedances (Rin, Rout).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Optional, Union

import sympy as sp

from aicione.solver.models import (
    ACSourceBranch,
    ACSolverProblem,
    BJTHybridPiDevice,
    MOSFETSmallSignalDevice,
    ResistorBranch,
    SolverNode,
)


@dataclass
class ACSolution:
    """Complete analytical solution for the AC small-signal regime."""
    circuit_id: str
    node_voltages: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)
    source_currents: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)
    evaluated_specs: dict[str, Union[float, sp.Expr]] = field(default_factory=dict)
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


class ACSolver:
    """Formulates AC small-signal nodal circuit equations and evaluates target specs."""

    def __init__(self, problem: ACSolverProblem):
        self.problem = problem
        self.voltages: dict[str, Union[float, sp.Symbol, sp.Expr]] = {}
        self.equations: list[sp.Equality] = []
        self.unknowns: list[sp.Symbol] = []
        self.source_current_symbols: dict[str, sp.Symbol] = {}

    def _setup_node_voltages(self) -> None:
        """Assigns 0 for ground & virtual supply nodes, and symbols for canonical unknown nodes."""
        # 1. Fixed potentials (GND reference and DC virtual supply rails)
        for node_id, node in self.problem.nodes.items():
            if node.is_ground or node.fixed_voltage is not None:
                fixed_val = _to_sympy_value(node.fixed_voltage if node.fixed_voltage is not None else 0.0)
                self.voltages[node_id] = fixed_val

        # 2. Assign canonical unknown potential symbols
        for node_id in self.problem.nodes:
            canon = self.problem.canonical_node(node_id)
            if canon in self.voltages:
                self.voltages[node_id] = self.voltages[canon]
            else:
                sym = sp.Symbol(f"v_{canon}")
                self.voltages[canon] = sym
                self.voltages[node_id] = sym

    def solve(self) -> ACSolution:
        """Formulates equations and solves the small-signal operating state."""
        self._setup_node_voltages()

        # Dictionary tracking currents leaving each canonical node
        node_leaving_currents: dict[str, list[sp.Expr]] = {n: [] for n in self.problem.nodes}

        # 1. Resistors (Ohm's Law: i = (va - vb) / R)
        for r in self.problem.resistors:
            ca = self.problem.canonical_node(r.node_a)
            cb = self.problem.canonical_node(r.node_b)
            if ca == cb:
                continue
            r_val = _to_sympy_value(r.resistance)
            va = self.voltages[ca]
            vb = self.voltages[cb]

            i_branch = (va - vb) / r_val
            node_leaving_currents[ca].append(i_branch)
            node_leaving_currents[cb].append(-i_branch)

        # 2. BJTs (Linearized Hybrid-pi model)
        for q in self.problem.bjts:
            cb = self.problem.canonical_node(q.base_node)
            cc = self.problem.canonical_node(q.collector_node)
            ce = self.problem.canonical_node(q.emitter_node)

            vb = self.voltages[cb]
            vc = self.voltages[cc]
            ve = self.voltages[ce]

            gm_val = _to_sympy_value(q.gm)
            rpi_val = _to_sympy_value(q.rpi)

            # Control voltage v_pi = vb - ve
            v_pi = vb - ve

            # Base current ib = v_pi / rpi
            i_b = v_pi / rpi_val
            node_leaving_currents[cb].append(i_b)
            node_leaving_currents[ce].append(-i_b)

            # Collector controlled current gm * v_pi
            i_gm = gm_val * v_pi
            node_leaving_currents[cc].append(i_gm)
            node_leaving_currents[ce].append(-i_gm)

            # Output resistance ro (if finite)
            if q.ro is not None and str(q.ro).lower() not in ("inf", "none"):
                ro_val = _to_sympy_value(q.ro)
                i_ro = (vc - ve) / ro_val
                node_leaving_currents[cc].append(i_ro)
                node_leaving_currents[ce].append(-i_ro)

        # 3. MOSFETs (Small-signal model)
        for m in self.problem.mosfets:
            cg = self.problem.canonical_node(m.gate_node)
            cd = self.problem.canonical_node(m.drain_node)
            cs = self.problem.canonical_node(m.source_node)

            vg = self.voltages[cg]
            vd = self.voltages[cd]
            vs = self.voltages[cs]

            gm_val = _to_sympy_value(m.gm)
            v_gs = vg - vs

            # Drain controlled current gm * v_gs
            i_gm = gm_val * v_gs
            node_leaving_currents[cd].append(i_gm)
            node_leaving_currents[cs].append(-i_gm)

            # ro (if finite)
            if m.ro is not None and str(m.ro).lower() not in ("inf", "none"):
                ro_val = _to_sympy_value(m.ro)
                i_ro = (vd - vs) / ro_val
                node_leaving_currents[cd].append(i_ro)
                node_leaving_currents[cs].append(-i_ro)

        # 4. Independent AC Sources
        for s in self.problem.sources:
            cp = self.problem.canonical_node(s.node_p)
            cn = self.problem.canonical_node(s.node_n)
            s_val = _to_sympy_value(s.value)

            if s.is_voltage:
                vp = self.voltages[cp]
                vn = self.voltages[cn]
                self.equations.append(sp.Eq(vp - vn, s_val))

                i_src = sp.Symbol(f"i_{s.id}")
                self.unknowns.append(i_src)
                self.source_current_symbols[s.id] = i_src
                node_leaving_currents[cp].append(i_src)
                node_leaving_currents[cn].append(-i_src)
            else:
                node_leaving_currents[cp].append(s_val)
                node_leaving_currents[cn].append(-s_val)

        # 5. Formulate KCL for canonical unknown nodes
        unknown_nodes = self.problem.get_unknown_nodes()
        for node_id in unknown_nodes:
            canon = self.problem.canonical_node(node_id)
            if canon in self.problem.nodes and self.problem.nodes[canon].is_fixed:
                continue
            currents = node_leaving_currents[canon]
            if currents:
                kcl_eq = sp.Eq(sp.Add(*currents), 0)
                self.equations.append(kcl_eq)
                v_sym = self.voltages[canon]
                if isinstance(v_sym, sp.Symbol) and v_sym not in self.unknowns:
                    self.unknowns.append(v_sym)

        # 6. Solve system with SymPy
        solution_dict = sp.solve(self.equations, self.unknowns, dict=True)
        if not solution_dict:
            sol_set = sp.linsolve(self.equations, self.unknowns)
            sol_list = list(sol_set)
            if sol_list:
                solution_map = dict(zip(self.unknowns, sol_list[0]))
            else:
                raise RuntimeError(
                    f"SymPy could not find a consistent solution for AC circuit '{self.problem.circuit_id}'. "
                    f"Equations: {self.equations}"
                )
        else:
            solution_map = solution_dict[0]

        # 7. Map solved voltages
        solved_voltages: dict[str, Union[float, sp.Expr]] = {}
        for node_id, v_val in self.voltages.items():
            if isinstance(v_val, sp.Symbol) and v_val in solution_map:
                solved_voltages[node_id] = solution_map[v_val]
            else:
                solved_voltages[node_id] = v_val

        # Map source currents
        solved_currents: dict[str, Union[float, sp.Expr]] = {}
        for s_id, s_sym in self.source_current_symbols.items():
            if s_sym in solution_map:
                solved_currents[s_id] = solution_map[s_sym]

        # 8. Evaluate target specs
        evaluated_specs = self._evaluate_specs(solved_voltages, solved_currents)

        return ACSolution(
            circuit_id=self.problem.circuit_id,
            node_voltages=solved_voltages,
            source_currents=solved_currents,
            evaluated_specs=evaluated_specs,
            equations_solved=self.equations,
            unknown_symbols=self.unknowns,
        )

    def _evaluate_specs(
        self,
        voltages: dict[str, Union[float, sp.Expr]],
        currents: dict[str, Union[float, sp.Expr]],
    ) -> dict[str, Union[float, sp.Expr]]:
        """Evaluates specs requested in find_targets (Av, Rin, Rout, Vac, etc.)."""
        results: dict[str, Union[float, sp.Expr]] = {}

        fn_pattern = re.compile(r"([A-Za-z0-9_]+)\(([^)]*)\)")

        for target in self.problem.find_targets:
            match = fn_pattern.match(target.strip())
            if not match:
                # Bare node potential e.g. 'Vout'
                canon = self.problem.canonical_node(target.strip())
                if canon in voltages:
                    results[target] = voltages[canon]
                continue

            fn_name, args_str = match.groups()
            args = [a.strip() for a in args_str.split(",") if a.strip()]

            # 1. Voltage Gain Av(out, in)
            if fn_name == "Av" and len(args) >= 2:
                out_node = self.problem.canonical_node(args[0])
                in_node = self.problem.canonical_node(args[1])
                v_out = voltages.get(out_node, 0.0)
                v_in = voltages.get(in_node, 0.0)

                if v_in != 0:
                    ratio = sp.simplify(v_out / v_in)
                    is_num = isinstance(ratio, (int, float)) or (hasattr(ratio, "is_number") and ratio.is_number)
                    results[target] = float(ratio) if is_num else ratio
                else:
                    results[target] = sp.nan

            # 2. Input Resistance Rin(in, ref) or Zin(in, ref)
            elif fn_name in ("Rin", "Zin") and len(args) >= 2:
                in_node = self.problem.canonical_node(args[0])
                ref_node = self.problem.canonical_node(args[1])
                v_in = voltages.get(in_node, 0.0)
                v_ref = voltages.get(ref_node, 0.0)
                v_diff = v_in - v_ref

                # Find source connected between in_node and ref_node
                src_found = None
                for s in self.problem.sources:
                    if self.problem.canonical_node(s.node_p) == in_node:
                        src_found = s
                        break

                if src_found and src_found.id in currents:
                    # Current supplied into in_node is -i_src (leaves positive terminal into circuit)
                    i_src = currents[src_found.id]
                    i_in = -i_src
                    if i_in != 0:
                        rin_val = sp.simplify(v_diff / i_in)
                        is_num = isinstance(rin_val, (int, float)) or (hasattr(rin_val, "is_number") and rin_val.is_number)
                        results[target] = float(rin_val) if is_num else rin_val
                    else:
                        results[target] = sp.oo
                else:
                    results[target] = sp.nan

            # 3. Incremental Voltage Vac(a, b)
            elif fn_name == "Vac" and len(args) >= 2:
                na = self.problem.canonical_node(args[0])
                nb = self.problem.canonical_node(args[1])
                va = voltages.get(na, 0.0)
                vb = voltages.get(nb, 0.0)
                diff = sp.simplify(va - vb)
                is_num = isinstance(diff, (int, float)) or (hasattr(diff, "is_number") and diff.is_number)
                results[target] = float(diff) if is_num else diff

        return results


def solve_ac(problem: ACSolverProblem) -> ACSolution:
    """Convenience function to solve an ACSolverProblem."""
    solver = ACSolver(problem)
    return solver.solve()
