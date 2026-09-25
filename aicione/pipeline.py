"""AI.ciOne End-to-End Solving Pipeline.

Orchestrates circuit ingestion, DC quiescent analysis, AC small-signal linearization,
and consolidated evaluation of user-requested specifications (specs.find).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Optional, Union

import sympy as sp

from aicione.ingest import IngestedCircuit, ingest
from aicione.solver.ac import ACSolution, solve_ac
from aicione.solver.dc import DCSolution, solve_dc
from aicione.solver.extractor import extract_ac_problem, extract_dc_problem
from ceml.models import ComponentType, NodeType


@dataclass
class CircuitSolution:
    """Consolidated end-to-end analytical solution for an analog circuit."""
    circuit_id: str
    description: Optional[str] = None
    find_results: dict[str, Union[float, sp.Expr, str]] = field(default_factory=dict)
    dc_solution: Optional[DCSolution] = None
    ac_solution: Optional[ACSolution] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializes the solution to a JSON-compatible dictionary."""
        def _val_to_num_or_str(v: Any) -> Any:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if hasattr(v, "is_number") and v.is_number:
                return float(v)
            return str(v)

        res: dict[str, Any] = {
            "circuit_id": self.circuit_id,
            "description": self.description,
            "find_results": {k: _val_to_num_or_str(v) for k, v in self.find_results.items()},
            "warnings": self.warnings,
        }

        if self.dc_solution:
            res["dc_solution"] = {
                "node_voltages": {k: _val_to_num_or_str(v) for k, v in self.dc_solution.node_voltages.items()},
                "bjt_operating_points": {
                    q_id: {
                        "ib": _val_to_num_or_str(q.ib),
                        "ic": _val_to_num_or_str(q.ic),
                        "ie": _val_to_num_or_str(q.ie),
                        "vbe": _val_to_num_or_str(q.vbe),
                        "vce": _val_to_num_or_str(q.vce),
                        "vcb": _val_to_num_or_str(q.vcb),
                        "gm": _val_to_num_or_str(q.gm),
                        "rpi": _val_to_num_or_str(q.rpi),
                        "ro": _val_to_num_or_str(q.ro),
                    }
                    for q_id, q in self.dc_solution.bjt_operating_points.items()
                },
            }

        if self.ac_solution:
            res["ac_solution"] = {
                "node_voltages": {k: _val_to_num_or_str(v) for k, v in self.ac_solution.node_voltages.items()},
                "source_currents": {k: _val_to_num_or_str(v) for k, v in self.ac_solution.source_currents.items()},
                "evaluated_specs": {k: _val_to_num_or_str(v) for k, v in self.ac_solution.evaluated_specs.items()},
            }

        return res


def evaluate_find_targets(
    ingested: IngestedCircuit,
    dc_solution: Optional[DCSolution] = None,
    ac_solution: Optional[ACSolution] = None,
) -> dict[str, Union[float, sp.Expr, str]]:
    """Evaluates all target items declared in specs.find across DC and AC regimes."""
    results: dict[str, Union[float, sp.Expr, str]] = {}
    if not ingested.circuit.specs or not ingested.circuit.specs.find:
        return results

    fn_pattern = re.compile(r"([A-Za-z0-9_]+)\(([^)]*)\)")

    for item in ingested.circuit.specs.find:
        target_raw = item.raw.strip()
        match = fn_pattern.match(target_raw)

        if not match:
            # 1. Bare node potential (e.g. 'Vout', 'Vin')
            target_node = target_raw
            if ac_solution and target_node in ac_solution.node_voltages:
                results[target_raw] = ac_solution.node_voltages[target_node]
            elif dc_solution and target_node in dc_solution.node_voltages:
                results[target_raw] = dc_solution.node_voltages[target_node]
            continue

        fn_name, args_str = match.groups()
        args = [a.strip() for a in args_str.split(",") if a.strip()]

        # 2. AC specifications (Av, Rin, Zin, Rout, Zout, Vac, Iac)
        if ac_solution and target_raw in ac_solution.evaluated_specs:
            results[target_raw] = ac_solution.evaluated_specs[target_raw]
            continue

        # 3. Transistor DC quiescent parameters (Ic, Ib, Ie, Vbe, Vce, Vcb, Vbc, gm, rpi, ro)
        if dc_solution and len(args) >= 1:
            dev_id = args[0]
            if dev_id in dc_solution.bjt_operating_points:
                q = dc_solution.bjt_operating_points[dev_id]
                fn_lower = fn_name.lower()
                if fn_lower == "ic":
                    results[target_raw] = q.ic
                elif fn_lower == "ib":
                    results[target_raw] = q.ib
                elif fn_lower == "ie":
                    results[target_raw] = q.ie
                elif fn_lower == "vbe":
                    results[target_raw] = q.vbe
                elif fn_lower == "vce":
                    results[target_raw] = q.vce
                elif fn_lower in ("vcb", "vbc"):
                    results[target_raw] = q.vcb
                elif fn_lower == "gm":
                    results[target_raw] = q.gm if q.gm is not None else "gm"
                elif fn_lower in ("rpi", "hie"):
                    results[target_raw] = q.rpi if q.rpi is not None else "rpi"
                elif fn_lower in ("ro", "hoe"):
                    results[target_raw] = q.ro if q.ro is not None else "inf"
                continue

        # 4. DC quiescent voltages between nodes Vdc(A, B)
        if fn_name == "Vdc" and len(args) >= 2 and dc_solution:
            na, nb = args[0], args[1]
            va = dc_solution.node_voltages.get(na, 0.0)
            vb = dc_solution.node_voltages.get(nb, 0.0)
            results[target_raw] = va - vb
            continue

        # 5. Incremental AC voltages Vac(A, B)
        if fn_name == "Vac" and len(args) >= 2 and ac_solution:
            na, nb = args[0], args[1]
            va = ac_solution.node_voltages.get(na, 0.0)
            vb = ac_solution.node_voltages.get(nb, 0.0)
            results[target_raw] = va - vb
            continue

    return results


def solve_circuit(
    circuit_source: Union[Path, str],
    vt: float = 0.026,
) -> CircuitSolution:
    """Executes the full multi-regime solving pipeline on a CEML circuit.

    Args:
        circuit_source: Path to a .ci file or a raw YAML/CEML string.
        vt: Thermal voltage in Volts (default 26mV at room temperature).

    Returns:
        A CircuitSolution object containing evaluated target specifications,
        DC operating points, and AC small-signal results.
    """
    ingested = ingest(circuit_source)

    # 1. Solve DC regime
    dc_prob = extract_dc_problem(ingested)
    dc_sol = solve_dc(dc_prob, vt=vt)

    # 2. Solve AC small-signal regime (consuming DC solution)
    ac_prob = extract_ac_problem(ingested, dc_solution=dc_sol, vt=vt)
    ac_sol = solve_ac(ac_prob)

    # 3. Consolidate find results
    find_results = evaluate_find_targets(ingested, dc_solution=dc_sol, ac_solution=ac_sol)

    # Format warnings
    warning_msgs = [f"[{w.code}] {w.message}" for w in ingested.warnings]

    return CircuitSolution(
        circuit_id=ingested.circuit_id,
        description=ingested.circuit.description,
        find_results=find_results,
        dc_solution=dc_sol,
        ac_solution=ac_sol,
        warnings=warning_msgs,
    )
