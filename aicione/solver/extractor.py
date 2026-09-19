"""DC Problem Extractor.

Transforms an IngestedCircuit into a DCSolverProblem containing pure mathematical
nodes, branches, and active device parameters ready for analytical/symbolic solving.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from aicione.ingest import IngestedCircuit
from aicione.solver.models import (
    BJTDCDevice,
    DCSolverProblem,
    DCSourceBranch,
    MOSFETDCDevice,
    ResistorBranch,
    SolverNode,
)
from ceml.models import ComponentType, NodeType


def _get_given_param(ingested: IngestedCircuit, target_pattern: str) -> Optional[float]:
    """Helper to extract a numeric parameter from specs.given matching a target pattern."""
    if not ingested.circuit.specs or not ingested.circuit.specs.given:
        return None

    for item in ingested.circuit.specs.given:
        if target_pattern in item.raw and item.value and item.value.numeric is not None:
            return item.value.numeric
    return None


def extract_dc_problem(ingested: IngestedCircuit) -> DCSolverProblem:
    """Extracts a self-contained DC analytical problem from an IngestedCircuit.

    Excludes AC-only components (capacitors are open, AC signal sources are zeroed),
    resolves fixed node potentials, and collects device equations.
    """
    nodes: dict[str, SolverNode] = {}

    # 1. Extract Nodes and determine fixed potentials
    for node_id, node in ingested.nodes.items():
        if node.type == NodeType.GROUND or node_id == "GND":
            nodes[node_id] = SolverNode(id=node_id, is_ground=True, fixed_voltage=0.0)
        elif node.type == NodeType.SUPPLY and node.value:
            val = node.value.numeric if node.value.numeric is not None else node.value.raw
            nodes[node_id] = SolverNode(id=node_id, is_ground=False, fixed_voltage=val)
        else:
            nodes[node_id] = SolverNode(id=node_id, is_ground=False, fixed_voltage=None)

    resistors: list[ResistorBranch] = []
    sources: list[DCSourceBranch] = []
    bjts: list[BJTDCDevice] = []
    mosfets: list[MOSFETDCDevice] = []

    # 2. Extract DC active components
    for comp_id, comp in ingested.dc_active_components.items():
        # Resistors
        if comp.type == ComponentType.RESISTOR.value:
            if isinstance(comp.pins, list) and len(comp.pins) == 2:
                na, nb = comp.pins[0], comp.pins[1]
                val: Union[float, str] = comp.value.numeric if (comp.value and comp.value.numeric is not None) else (
                    comp.value.raw if comp.value else comp_id
                )
                resistors.append(ResistorBranch(id=comp_id, node_a=na, node_b=nb, resistance=val))

        # Independent DC Voltage Sources
        elif comp.type == ComponentType.VOLTAGE_SOURCE.value:
            if isinstance(comp.pins, dict) and "p" in comp.pins and "n" in comp.pins:
                val = comp.value.numeric if (comp.value and comp.value.numeric is not None) else 0.0
                sources.append(
                    DCSourceBranch(id=comp_id, node_p=comp.pins["p"], node_n=comp.pins["n"], value=val, is_voltage=True)
                )

        # Independent DC Current Sources
        elif comp.type == ComponentType.CURRENT_SOURCE.value:
            if isinstance(comp.pins, dict) and "p" in comp.pins and "n" in comp.pins:
                val = comp.value.numeric if (comp.value and comp.value.numeric is not None) else 0.0
                sources.append(
                    DCSourceBranch(id=comp_id, node_p=comp.pins["p"], node_n=comp.pins["n"], value=val, is_voltage=False)
                )

        # BJTs
        elif comp.type == ComponentType.BJT.value:
            if isinstance(comp.pins, dict):
                base = comp.pins.get("base", "")
                collector = comp.pins.get("collector", "")
                emitter = comp.pins.get("emitter", "")

                pol = comp.polarity.value if comp.polarity else "NPN"

                # Check parameters in specs.given or default to spec standards
                hfe = _get_given_param(ingested, f"hfe({comp_id})") or 100.0
                vbe = _get_given_param(ingested, f"Vbe({comp_id})") or 0.7
                va = _get_given_param(ingested, "VA")

                bjts.append(
                    BJTDCDevice(
                        id=comp_id,
                        base_node=base,
                        collector_node=collector,
                        emitter_node=emitter,
                        polarity=pol,
                        hfe=hfe,
                        vbe=vbe,
                        va=va,
                    )
                )

        # MOSFETs
        elif comp.type == ComponentType.MOSFET.value:
            if isinstance(comp.pins, dict):
                gate = comp.pins.get("gate", "")
                drain = comp.pins.get("drain", "")
                source = comp.pins.get("source", "")
                pol = comp.polarity.value if comp.polarity else "NMOS"
                mosfets.append(
                    MOSFETDCDevice(
                        id=comp_id,
                        gate_node=gate,
                        drain_node=drain,
                        source_node=source,
                        polarity=pol,
                    )
                )

    return DCSolverProblem(
        circuit_id=ingested.circuit_id,
        nodes=nodes,
        resistors=resistors,
        sources=sources,
        bjts=bjts,
        mosfets=mosfets,
        find_targets=ingested.get_find_targets(),
    )
