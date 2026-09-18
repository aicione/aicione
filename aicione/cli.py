"""AI.ciOne Command Line Interface.

Provides tools to inspect ingested circuits and view the extracted solver AST.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aicione.ingest import ingest
from aicione.solver.extractor import extract_dc_problem


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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="aicione",
        description="AI.ciOne Analytical Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect-dc",
        help="Inspect the extracted DC analytical solver problem from a .ci file.",
    )
    inspect_parser.add_argument("path", help="Path to the .ci file")
    inspect_parser.set_defaults(func=command_inspect_dc)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
