"""Problem Extractor for DC and AC Regimes.

Transforms an IngestedCircuit into a DCSolverProblem or ACSolverProblem containing
pure mathematical nodes, branches, and active device parameters ready for analytical/symbolic solving.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from aicione.ingest import IngestedCircuit
from aicione.solver.dc import DCSolution, solve_dc
from aicione.solver.models import (
    ACSourceBranch,
    ACSolverProblem,
    BJTDCDevice,
    BJTHybridPiDevice,
    DCSolverProblem,
    DCSourceBranch,
    MOSFETDCDevice,
    MOSFETSmallSignalDevice,
    ResistorBranch,
    SolverNode,
)
from ceml.models import AcBehavior, ComponentType, NodeType, Regime


def _get_given_param(ingested: IngestedCircuit, target_pattern: str) -> Optional[Union[float, str]]:
    """Helper to extract a numeric or literal parameter from specs.given matching a target pattern."""
    if not ingested.circuit.specs or not ingested.circuit.specs.given:
        return None

    for item in ingested.circuit.specs.given:
        if target_pattern in item.raw and item.value:
            if item.value.numeric is not None:
                return item.value.numeric
            if item.value.raw:
                return item.value.raw
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


def extract_ac_problem(
    ingested: IngestedCircuit,
    dc_solution: Optional[DCSolution] = None,
    vt: float = 0.026,
) -> ACSolverProblem:
    """Extracts a self-contained AC small-signal analytical problem from an IngestedCircuit.

    Steps:
      1. Resolves DC operating point if not provided and active devices are present.
      2. Maps constant DC supplies (VCC, VDD) to AC virtual grounds (0.0 V).
      3. Discovers node coalescing across capacitors with ac_behavior: short_circuit.
      4. Models resistors between canonical nodes (dropping shorted resistors).
      5. Instantiates linearized hybrid-pi BJT models (gm, rpi, ro).
      6. Instantiates small-signal MOSFET models.
      7. Extracts AC sources and find_targets.
    """
    # 1. Resolve DC operating point if needed and not supplied
    has_bjts = any(c.type == ComponentType.BJT.value for c in ingested.components.values())
    if dc_solution is None and has_bjts:
        dc_prob = extract_dc_problem(ingested)
        dc_solution = solve_dc(dc_prob, vt=vt)

    # 2. Extract Nodes and determine fixed AC potentials
    # Constant DC supplies act as AC grounds (0.0 V incremental potential)
    nodes: dict[str, SolverNode] = {}
    for node_id, node in ingested.nodes.items():
        if node.type == NodeType.GROUND or node_id == "GND":
            nodes[node_id] = SolverNode(id=node_id, is_ground=True, fixed_voltage=0.0)
        elif node.type == NodeType.SUPPLY:
            # AC virtual ground
            nodes[node_id] = SolverNode(id=node_id, is_ground=False, fixed_voltage=0.0)
        else:
            nodes[node_id] = SolverNode(id=node_id, is_ground=False, fixed_voltage=None)

    # 3. Disjoint-Set (Union-Find) for node coalescing via short-circuit capacitors
    parent: dict[str, str] = {n: n for n in ingested.nodes}

    def find(u: str) -> str:
        parent.setdefault(u, u)
        if parent[u] != u:
            parent[u] = find(parent[u])
        return parent[u]

    def union(u: str, v: str) -> None:
        root_u = find(u)
        root_v = find(v)
        if root_u == root_v:
            return

        # Fixed reference (GND or AC virtual supply) has highest priority
        u_is_fixed = (root_u == "GND") or (root_u in nodes and nodes[root_u].is_fixed)
        v_is_fixed = (root_v == "GND") or (root_v in nodes and nodes[root_v].is_fixed)

        if u_is_fixed and not v_is_fixed:
            parent[root_v] = root_u
        elif v_is_fixed and not u_is_fixed:
            parent[root_u] = root_v
        elif u_is_fixed and v_is_fixed:
            if root_u == "GND":
                parent[root_v] = root_u
            else:
                parent[root_u] = root_v
        else:
            # Neither is fixed: prefer named terminal nodes (input/output) over internal nodes
            u_node = ingested.nodes.get(root_u)
            v_node = ingested.nodes.get(root_v)
            u_is_term = u_node is not None and u_node.type in (NodeType.INPUT, NodeType.OUTPUT)
            v_is_term = v_node is not None and v_node.type in (NodeType.INPUT, NodeType.OUTPUT)
            if u_is_term and not v_is_term:
                parent[root_v] = root_u
            elif v_is_term and not u_is_term:
                parent[root_u] = root_v
            else:
                parent[root_u] = root_v

    # Identify capacitors with ac_behavior: short_circuit
    for comp in ingested.components.values():
        if comp.type == ComponentType.CAPACITOR.value:
            is_short = (
                comp.ac_behavior == AcBehavior.SHORT_CIRCUIT
                or getattr(comp.ac_behavior, "value", None) == "short_circuit"
                or comp.raw_data.get("ac_behavior") == "short_circuit"
            )
            if is_short:
                if isinstance(comp.pins, list) and len(comp.pins) == 2:
                    union(comp.pins[0], comp.pins[1])
                elif isinstance(comp.pins, dict) and "p" in comp.pins and "n" in comp.pins:
                    union(comp.pins["p"], comp.pins["n"])

    # Build node_aliases map
    node_aliases: dict[str, str] = {}
    for node_id in ingested.nodes:
        canonical = find(node_id)
        if canonical != node_id:
            node_aliases[node_id] = canonical

    # Update nodes dict to reflect coalescing to fixed potentials
    for node_id in ingested.nodes:
        canonical = find(node_id)
        if canonical in nodes and nodes[canonical].is_fixed:
            nodes[node_id].fixed_voltage = nodes[canonical].fixed_voltage
            if nodes[canonical].is_ground:
                nodes[node_id].is_ground = True

    # 4. Extract Resistors (drop resistors shorted out by capacitors, e.g. bypassed RE)
    resistors: list[ResistorBranch] = []
    for comp_id, comp in ingested.components.items():
        if comp.type == ComponentType.RESISTOR.value and isinstance(comp.pins, list) and len(comp.pins) == 2:
            na = find(comp.pins[0])
            nb = find(comp.pins[1])
            if na == nb:
                # Resistor is shorted out in AC by a parallel bypass capacitor
                continue
            val: Union[float, str] = comp.value.numeric if (comp.value and comp.value.numeric is not None) else (
                comp.value.raw if comp.value else comp_id
            )
            resistors.append(ResistorBranch(id=comp_id, node_a=na, node_b=nb, resistance=val))

    # 5. Extract BJTs with linearized Hybrid-pi models
    bjts: list[BJTHybridPiDevice] = []
    for comp_id, comp in ingested.components.items():
        if comp.type == ComponentType.BJT.value and isinstance(comp.pins, dict):
            base = find(comp.pins.get("base", ""))
            collector = find(comp.pins.get("collector", ""))
            emitter = find(comp.pins.get("emitter", ""))

            # Explicit given specs have precedence
            gm = _get_given_param(ingested, f"gm({comp_id})")
            rpi = _get_given_param(ingested, f"rpi({comp_id})") or _get_given_param(ingested, f"hie({comp_id})")
            ro = _get_given_param(ingested, f"ro({comp_id})")
            cpi = _get_given_param(ingested, f"Cpi({comp_id})")
            cmu = _get_given_param(ingested, f"Cmu({comp_id})")

            # Fallback to DC quiescent point solution
            if dc_solution and comp_id in dc_solution.bjt_operating_points:
                q_pt = dc_solution.bjt_operating_points[comp_id]
                if gm is None and q_pt.gm is not None:
                    gm = q_pt.gm
                if rpi is None and q_pt.rpi is not None:
                    rpi = q_pt.rpi
                if ro is None and q_pt.ro is not None:
                    ro = q_pt.ro

            # If still None, fall back to symbolic identifiers
            if gm is None:
                gm = f"gm_{comp_id}"
            if rpi is None:
                rpi = f"rpi_{comp_id}"

            bjts.append(
                BJTHybridPiDevice(
                    id=comp_id,
                    base_node=base,
                    collector_node=collector,
                    emitter_node=emitter,
                    gm=gm,
                    rpi=rpi,
                    ro=ro,
                    cpi=cpi,
                    cmu=cmu,
                )
            )

    # 6. Extract MOSFETs
    mosfets: list[MOSFETSmallSignalDevice] = []
    for comp_id, comp in ingested.components.items():
        if comp.type == ComponentType.MOSFET.value and isinstance(comp.pins, dict):
            gate = find(comp.pins.get("gate", ""))
            drain = find(comp.pins.get("drain", ""))
            source = find(comp.pins.get("source", ""))

            gm = _get_given_param(ingested, f"gm({comp_id})") or f"gm_{comp_id}"
            ro = _get_given_param(ingested, f"ro({comp_id})")
            cgs = _get_given_param(ingested, f"Cgs({comp_id})")
            cgd = _get_given_param(ingested, f"Cgd({comp_id})")

            mosfets.append(
                MOSFETSmallSignalDevice(
                    id=comp_id,
                    gate_node=gate,
                    drain_node=drain,
                    source_node=source,
                    gm=gm,
                    ro=ro,
                    cgs=cgs,
                    cgd=cgd,
                )
            )

    # 7. Extract AC Independent Sources
    sources: list[ACSourceBranch] = []
    for comp_id, comp in ingested.components.items():
        if comp.type in (ComponentType.VOLTAGE_SOURCE.value, ComponentType.CURRENT_SOURCE.value):
            is_ac = comp.regime == Regime.AC or (comp.regime is None and comp.raw_data.get("regime") == "AC")
            if is_ac and isinstance(comp.pins, dict):
                p = find(comp.pins.get("p", ""))
                n = find(comp.pins.get("n", ""))
                val = comp.value.numeric if (comp.value and comp.value.numeric is not None) else (
                    comp.value.raw if comp.value else 1.0
                )
                is_v = comp.type == ComponentType.VOLTAGE_SOURCE.value
                sources.append(ACSourceBranch(id=comp_id, node_p=p, node_n=n, value=val, is_voltage=is_v))

    # If no explicit AC source is declared, connect a normalized AC test source at the input node
    if not sources:
        for node_id, node in ingested.nodes.items():
            if node.type == NodeType.INPUT:
                p_node = find(node_id)
                sources.append(
                    ACSourceBranch(
                        id=f"V_{node_id}",
                        node_p=p_node,
                        node_n="GND",
                        value=1.0,
                        is_voltage=True,
                    )
                )
                break

    return ACSolverProblem(
        circuit_id=ingested.circuit_id,
        nodes=nodes,
        node_aliases=node_aliases,
        resistors=resistors,
        sources=sources,
        bjts=bjts,
        mosfets=mosfets,
        find_targets=ingested.get_find_targets(),
    )
