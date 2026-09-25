"""AI.ciOne Command Line Interface.

Provides tools to inspect ingested circuits and view the extracted solver AST.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aicione.ingest import ingest
from aicione.pipeline import solve_circuit
from aicione.solver import extract_ac_problem, extract_dc_problem, solve_ac, solve_dc


def command_inspect_dc(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: File not found: {args.path}", file=sys.stderr)
        return 1

    try:
        ingested = ingest(path)
        dc_problem = extract_dc_problem(ingested)
    except Exception as exc:
        print(f"Error ingesting circuit: {exc}", file=sys.stderr)
        return 1

    print(f"============================================================")
    print(f"  AI.ciOne DC Solver Problem: {dc_problem.circuit_id}")
    print(f"============================================================")

    # Nodes
    print("\n[Nodes & Potentials]")
    for n_id, n in dc_problem.nodes.items():
        if n.is_ground:
            status = "0.0 V (Ground Reference)"
        elif n.fixed_voltage is not None:
            status = f"{n.fixed_voltage} V (Fixed Supply)"
        else:
            status = "Unknown Potential (Variable to solve)"
        print(f"  - {n_id:8s} -> {status}")

    unknown_nodes = dc_problem.get_unknown_nodes()
    print(f"\n  Total Unknown Node Potentials to Solve: {len(unknown_nodes)} {unknown_nodes}")

    # Resistors
    print(f"\n[DC Resistive Branches ({len(dc_problem.resistors)})]")
    for r in dc_problem.resistors:
        print(f"  - {r.id:6s} between {r.node_a:<6s} and {r.node_b:<6s} | R = {r.resistance}")

    # Sources
    if dc_problem.sources:
        print(f"\n[DC Independent Sources ({len(dc_problem.sources)})]")
        for s in dc_problem.sources:
            kind = "Voltage Source" if s.is_voltage else "Current Source"
            print(f"  - {s.id:6s} from {s.node_p} to {s.node_n} | {kind} = {s.value}")

    # BJTs
    if dc_problem.bjts:
        print(f"\n[BJT Active Devices ({len(dc_problem.bjts)})]")
        for q in dc_problem.bjts:
            print(f"  - {q.id:6s} ({q.polarity}): Base={q.base_node}, Collector={q.collector_node}, Emitter={q.emitter_node}")
            print(f"           Parameters: hfe (beta) = {q.hfe}, Vbe = {q.vbe} V, VA = {q.va or 'inf'}")

    # MOSFETs
    if dc_problem.mosfets:
        print(f"\n[MOSFET Active Devices ({len(dc_problem.mosfets)})]")
        for m in dc_problem.mosfets:
            print(f"  - {m.id:6s} ({m.polarity}): Gate={m.gate_node}, Drain={m.drain_node}, Source={m.source_node}")

    # Target
    if dc_problem.find_targets:
        print(f"\n[Specs to Find in DC Analysis]")
        for t in dc_problem.find_targets:
            print(f"  - {t}")

    print("\n-> Status: Ready for equation formulation and SymPy symbolic solver.\n")
    return 0


def command_inspect_ac(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: File not found: {args.path}", file=sys.stderr)
        return 1

    try:
        ingested = ingest(path)
        ac_problem = extract_ac_problem(ingested)
    except Exception as exc:
        print(f"Error extracting AC circuit: {exc}", file=sys.stderr)
        return 1

    print(f"============================================================")
    print(f"  AI.ciOne AC Small-Signal Problem: {ac_problem.circuit_id}")
    print(f"============================================================")

    # 1. Nodes & Potentials
    print("\n[AC Nodes & Incremental Potentials]")
    for n_id, n in ac_problem.nodes.items():
        if n_id in ac_problem.node_aliases:
            canon = ac_problem.canonical_node(n_id)
            status = f"Coalesced/Aliased -> {canon}"
        elif n.is_ground:
            status = "0.0 V (Circuit Ground Reference)"
        elif n.fixed_voltage is not None:
            status = f"{n.fixed_voltage:.1f} V (AC Virtual Ground)"
        else:
            status = "Unknown Small-Signal Potential (Variable to solve)"
        print(f"  - {n_id:8s} -> {status}")

    unknown_nodes = ac_problem.get_unknown_nodes()
    print(f"\n  Canonical Unknown Node Potentials to Solve: {len(unknown_nodes)} {unknown_nodes}")

    # 2. Resistors
    print(f"\n[AC Resistive Branches ({len(ac_problem.resistors)})]")
    for r in ac_problem.resistors:
        print(f"  - {r.id:6s} between {r.node_a:<6s} and {r.node_b:<6s} | R = {r.resistance}")

    # 3. BJTs (Hybrid-pi models)
    if ac_problem.bjts:
        print(f"\n[BJT Linearized Hybrid-pi Models ({len(ac_problem.bjts)})]")
        for q in ac_problem.bjts:
            gm_str = f"{q.gm * 1e3:.2f} mS" if isinstance(q.gm, (int, float)) else str(q.gm)
            rpi_str = f"{q.rpi / 1e3:.2f} kOhm" if isinstance(q.rpi, (int, float)) else str(q.rpi)
            ro_str = f"{q.ro / 1e3:.2f} kOhm" if isinstance(q.ro, (int, float)) else (str(q.ro) if q.ro else "inf")
            print(f"  - {q.id:6s} Hybrid-pi: Base={q.base_node}, Collector={q.collector_node}, Emitter={q.emitter_node}")
            print(f"           Parameters: gm = {gm_str}, rpi = {rpi_str}, ro = {ro_str}")

    # 4. MOSFETs
    if ac_problem.mosfets:
        print(f"\n[MOSFET Small-Signal Models ({len(ac_problem.mosfets)})]")
        for m in ac_problem.mosfets:
            print(f"  - {m.id:6s}: Gate={m.gate_node}, Drain={m.drain_node}, Source={m.source_node}")
            print(f"           Parameters: gm = {m.gm}, ro = {m.ro or 'inf'}")

    # 5. Sources
    if ac_problem.sources:
        print(f"\n[AC Test/Signal Sources ({len(ac_problem.sources)})]")
        for s in ac_problem.sources:
            kind = "Voltage Source" if s.is_voltage else "Current Source"
            print(f"  - {s.id:6s} from {s.node_p} to {s.node_n} | {kind} = {s.value}")

    # 6. Target specs
    if ac_problem.find_targets:
        print(f"\n[Specs to Solve in AC Analysis]")
        for t in ac_problem.find_targets:
            print(f"  - {t}")

    print("\n-> Status: Ready for AC small-signal equation formulation.\n")
    return 0


def command_solve_dc(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: File not found: {args.path}", file=sys.stderr)
        return 1

    try:
        ingested = ingest(path)
        dc_problem = extract_dc_problem(ingested)
        solution = solve_dc(dc_problem)
    except Exception as exc:
        print(f"Error solving DC circuit: {exc}", file=sys.stderr)
        return 1

    print(f"============================================================")
    print(f"  AI.ciOne DC Operating Point Solution: {solution.circuit_id}")
    print(f"============================================================")

    # 1. Node Voltages
    print("\n[Solved DC Node Voltages]")
    for n_id, v in solution.node_voltages.items():
        is_num = isinstance(v, (int, float)) or (hasattr(v, "is_number") and v.is_number)
        if is_num:
            print(f"  - V({n_id:6s}) = {float(v):10.4f} V")
        else:
            print(f"  - V({n_id:6s}) = {v}")

    # 2. BJT Quiescent Points
    if solution.bjt_operating_points:
        print("\n[BJT Quiescent Bias Points (Active Region)]")
        for q_id, q_pt in solution.bjt_operating_points.items():
            print(f"  --- Transistor {q_id} ---")
            is_ic_num = isinstance(q_pt.ic, (int, float)) or (hasattr(q_pt.ic, "is_number") and q_pt.ic.is_number)
            if is_ic_num:
                ib_f = float(q_pt.ib)
                ic_f = float(q_pt.ic)
                ie_f = float(q_pt.ie)
                vbe_f = float(q_pt.vbe)
                vce_f = float(q_pt.vce)
                vcb_f = float(q_pt.vcb)
                print(f"    IB  = {ib_f * 1e6:10.3f} uA")
                print(f"    IC  = {ic_f * 1e3:10.3f} mA")
                print(f"    IE  = {ie_f * 1e3:10.3f} mA")
                print(f"    VBE = {vbe_f:10.3f} V")
                print(f"    VCE = {vce_f:10.3f} V")
                print(f"    VCB = {vcb_f:10.3f} V")
                if q_pt.gm is not None:
                    print(f"    gm  = {q_pt.gm * 1e3:10.2f} mA/V (mS)")
                if q_pt.rpi is not None:
                    print(f"    rpi = {q_pt.rpi / 1e3:10.2f} kOhm")
                if q_pt.ro is not None:
                    print(f"    ro  = {q_pt.ro / 1e3:10.2f} kOhm")
            else:
                print(f"    IB  = {q_pt.ib}")
                print(f"    IC  = {q_pt.ic}")
                print(f"    IE  = {q_pt.ie}")
                print(f"    VBE = {q_pt.vbe}")
                print(f"    VCE = {q_pt.vce}")

    print("\n-> DC Operating Point analysis completed successfully.\n")
    return 0


def command_solve_ac(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: File not found: {args.path}", file=sys.stderr)
        return 1

    try:
        ingested = ingest(path)
        ac_problem = extract_ac_problem(ingested)
        solution = solve_ac(ac_problem)
    except Exception as exc:
        print(f"Error solving AC circuit: {exc}", file=sys.stderr)
        return 1

    print(f"============================================================")
    print(f"  AI.ciOne AC Small-Signal Solution: {solution.circuit_id}")
    print(f"============================================================")

    # 1. Evaluated Specs
    if solution.evaluated_specs:
        print("\n[Evaluated Target Specifications (specs.find)]")
        for target, val in solution.evaluated_specs.items():
            is_num = isinstance(val, (int, float)) or (hasattr(val, "is_number") and val.is_number)
            if is_num:
                v_float = float(val)
                if target.startswith(("Rin", "Zin", "Rout", "Zout")):
                    if abs(v_float) >= 1e3:
                        unit_str = f"{v_float / 1e3:10.3f} kOhm"
                    else:
                        unit_str = f"{v_float:10.2f} Ohm"
                    print(f"  - {target:25s} = {unit_str}")
                else:
                    print(f"  - {target:25s} = {v_float:10.4f}")
            else:
                print(f"  - {target:25s} = {val}")

    # 2. Node Voltages
    print("\n[Solved AC Incremental Node Potentials]")
    for n_id, v in solution.node_voltages.items():
        is_num = isinstance(v, (int, float)) or (hasattr(v, "is_number") and v.is_number)
        if is_num:
            print(f"  - v({n_id:6s}) = {float(v):10.4f} V")
        else:
            print(f"  - v({n_id:6s}) = {v}")

    # 3. Source Currents
    if solution.source_currents:
        print("\n[Solved AC Source Currents]")
        for s_id, i_val in solution.source_currents.items():
            is_num = isinstance(i_val, (int, float)) or (hasattr(i_val, "is_number") and i_val.is_number)
            if is_num:
                print(f"  - i({s_id:6s}) = {float(i_val) * 1e3:10.4f} mA")
            else:
                print(f"  - i({s_id:6s}) = {i_val}")

    print("\n-> AC Small-Signal analysis completed successfully.\n")
    return 0


def command_solve(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"Error: File not found: {args.path}", file=sys.stderr)
        return 1

    try:
        solution = solve_circuit(path)
    except Exception as exc:
        print(f"Error solving circuit: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        import json
        print(json.dumps(solution.to_dict(), indent=2))
        return 0

    print("============================================================")
    print(f"  AI.ciOne Solution: {solution.circuit_id}")
    if solution.description:
        print(f"  {solution.description}")
    print("============================================================")

    # 1. Target Results (specs.find)
    if solution.find_results:
        print("\n============================================================")
        print("  TARGET RESULTS (specs.find)")
        print("============================================================")
        for target, val in solution.find_results.items():
            is_num = isinstance(val, (int, float)) or (hasattr(val, "is_number") and val.is_number)
            if is_num:
                v_float = float(val)
                if target.startswith(("Rin", "Zin", "Rout", "Zout", "rpi", "ro", "hie")):
                    if abs(v_float) >= 1e3:
                        formatted = f"{v_float / 1e3:10.3f} kOhm"
                    else:
                        formatted = f"{v_float:10.2f} Ohm"
                elif target.startswith(("Ic", "Ib", "Ie", "Id", "Is", "Iac", "Idc")):
                    if abs(v_float) < 1e-3:
                        formatted = f"{v_float * 1e6:10.3f} uA"
                    else:
                        formatted = f"{v_float * 1e3:10.3f} mA"
                elif target.startswith(("gm",)):
                    formatted = f"{v_float * 1e3:10.2f} mS"
                elif target.startswith(("V", "Vac", "Vdc", "Vbe", "Vce", "Vcb", "Vbc")):
                    formatted = f"{v_float:10.3f} V"
                else:
                    formatted = f"{v_float:10.4f}"
                print(f"  - {target:25s} = {formatted}")
            else:
                print(f"  - {target:25s} = {val}")

    # 2. DC Quiescent Operating Point Summary
    if solution.dc_solution and solution.dc_solution.bjt_operating_points:
        print("\n------------------------------------------------------------")
        print("  DC Quiescent Operating Point Summary")
        print("------------------------------------------------------------")
        for q_id, q_pt in solution.dc_solution.bjt_operating_points.items():
            is_ic_num = isinstance(q_pt.ic, (int, float)) or (hasattr(q_pt.ic, "is_number") and q_pt.ic.is_number)
            if is_ic_num:
                ib_str = f"{float(q_pt.ib) * 1e6:7.2f} uA"
                ic_str = f"{float(q_pt.ic) * 1e3:7.3f} mA"
                ie_str = f"{float(q_pt.ie) * 1e3:7.3f} mA"
                vbe_str = f"{float(q_pt.vbe):6.3f} V"
                vce_str = f"{float(q_pt.vce):6.3f} V"
                gm_str = f"{float(q_pt.gm) * 1e3:6.2f} mS" if q_pt.gm else "N/A"
                rpi_str = f"{float(q_pt.rpi) / 1e3:6.2f} kOhm" if q_pt.rpi else "N/A"
                print(f"  Transistor {q_id}:")
                print(f"    IC  = {ic_str:<12s} IB  = {ib_str:<12s} IE  = {ie_str}")
                print(f"    VCE = {vce_str:<12s} VBE = {vbe_str:<12s} gm  = {gm_str}")
                print(f"    rpi = {rpi_str}")
            else:
                print(f"  Transistor {q_id}: IC={q_pt.ic}, IB={q_pt.ib}, VCE={q_pt.vce}")

    # 3. AC Small-Signal Potentials
    if solution.ac_solution:
        print("\n------------------------------------------------------------")
        print("  AC Small-Signal Incremental Potentials")
        print("------------------------------------------------------------")
        v_items = []
        for n_id, v in solution.ac_solution.node_voltages.items():
            if n_id in ("GND", "VCC", "VDD") or float(v) == 0.0:
                continue
            is_num = isinstance(v, (int, float)) or (hasattr(v, "is_number") and v.is_number)
            if is_num:
                v_items.append(f"v({n_id}) = {float(v):.3f} V")
            else:
                v_items.append(f"v({n_id}) = {v}")
        if v_items:
            print("  " + ", ".join(v_items))

    # 4. Warnings
    if solution.warnings:
        print("\n[Validation Warnings]")
        for w in solution.warnings:
            print(f"  - {w}")

    print("\n-> Circuit solved successfully.\n")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aicione",
        description="AI.ciOne Analytical Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # solve (unified end-to-end)
    solve_unified_parser = subparsers.add_parser(
        "solve",
        help="Solve the circuit end-to-end (DC operating point + AC small-signal + specs.find evaluation).",
    )
    solve_unified_parser.add_argument("path", help="Path to the .ci file")
    solve_unified_parser.add_argument("--json", action="store_true", help="Output solution in JSON format")
    solve_unified_parser.set_defaults(func=command_solve)

    # inspect-dc
    inspect_parser = subparsers.add_parser(
        "inspect-dc",
        help="Inspect the extracted DC analytical solver problem from a .ci file.",
    )
    inspect_parser.add_argument("path", help="Path to the .ci file")
    inspect_parser.set_defaults(func=command_inspect_dc)

    # inspect-ac
    inspect_ac_parser = subparsers.add_parser(
        "inspect-ac",
        help="Inspect the extracted AC small-signal analytical problem from a .ci file.",
    )
    inspect_ac_parser.add_argument("path", help="Path to the .ci file")
    inspect_ac_parser.set_defaults(func=command_inspect_ac)

    # solve-dc
    solve_parser = subparsers.add_parser(
        "solve-dc",
        help="Solve the DC quiescent operating point analytically with SymPy.",
    )
    solve_parser.add_argument("path", help="Path to the .ci file")
    solve_parser.set_defaults(func=command_solve_dc)

    # solve-ac
    solve_ac_parser = subparsers.add_parser(
        "solve-ac",
        help="Solve the AC small-signal transfer functions and impedances analytically with SymPy.",
    )
    solve_ac_parser.add_argument("path", help="Path to the .ci file")
    solve_ac_parser.set_defaults(func=command_solve_ac)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

