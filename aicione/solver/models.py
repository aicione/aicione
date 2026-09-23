"""Solver AST Models.

Defines the mathematical structures representing circuits in the analytical solver domain,
independent of YAML syntax and markup specifics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class SolverNode:
    """Represents an electric node with its potential state."""
    id: str
    is_ground: bool = False
    fixed_voltage: Optional[Union[float, str]] = None

    @property
    def is_fixed(self) -> bool:
        return self.is_ground or self.fixed_voltage is not None


@dataclass
class ResistorBranch:
    """A resistive branch between two nodes."""
    id: str
    node_a: str
    node_b: str
    resistance: Union[float, str]  # Numeric ohms or literal symbol


@dataclass
class DCSourceBranch:
    """An independent DC source."""
    id: str
    node_p: str
    node_n: str
    value: Union[float, str]
    is_voltage: bool = True  # True: voltage source, False: current source


@dataclass
class BJTDCDevice:
    """BJT representation for DC quiescent operating-point analysis."""
    id: str
    base_node: str
    collector_node: str
    emitter_node: str
    polarity: str = "NPN"
    hfe: float = 100.0
    vbe: float = 0.7
    va: Optional[float] = None  # Early voltage (None -> ro infinite)


@dataclass
class MOSFETDCDevice:
    """MOSFET representation for DC quiescent operating-point analysis."""
    id: str
    gate_node: str
    drain_node: str
    source_node: str
    polarity: str = "NMOS"
    vt: float = 1.0
    kn: Optional[float] = None


@dataclass
class DCSolverProblem:
    """A complete, self-contained DC analytical problem ready for equation formulation."""
    circuit_id: str
    nodes: dict[str, SolverNode] = field(default_factory=dict)
    resistors: list[ResistorBranch] = field(default_factory=list)
    sources: list[DCSourceBranch] = field(default_factory=list)
    bjts: list[BJTDCDevice] = field(default_factory=list)
    mosfets: list[MOSFETDCDevice] = field(default_factory=list)
    find_targets: list[str] = field(default_factory=list)

    def get_unknown_nodes(self) -> list[str]:
        """Returns node IDs whose voltages are unknown variables to solve for."""
        return [node_id for node_id, node in self.nodes.items() if not node.is_fixed]


@dataclass
class ACSourceBranch:
    """An independent AC small-signal source."""
    id: str
    node_p: str
    node_n: str
    value: Union[float, str] = 1.0  # Normalized test signal or symbolic (e.g., 'vin', 'iin')
    is_voltage: bool = True  # True: voltage source, False: current source


@dataclass
class BJTHybridPiDevice:
    """Linearized hybrid-pi small-signal model for a BJT.

    Constitutive equations in AC:
      - Control voltage: v_pi = v_base - v_emitter
      - Base-emitter branch: i_b = v_pi / rpi
      - Collector-emitter branch: i_c = gm * v_pi + (v_collector - v_emitter) / ro
      - Emitter current: i_e = i_b + i_c
    """
    id: str
    base_node: str
    collector_node: str
    emitter_node: str
    gm: Union[float, str]  # Transconductance (Ic / Vt)
    rpi: Union[float, str]  # Small-signal input resistance (beta / gm)
    ro: Optional[Union[float, str]] = None  # Output resistance (VA / Ic); None implies infinite
    cpi: Optional[Union[float, str]] = None  # High-frequency base-emitter capacitance
    cmu: Optional[Union[float, str]] = None  # High-frequency base-collector capacitance


@dataclass
class MOSFETSmallSignalDevice:
    """Linearized small-signal model for a MOSFET.

    Constitutive equations in AC:
      - Gate current: i_g = 0 (infinite input impedance at mid-band)
      - Control voltage: v_gs = v_gate - v_source
      - Drain-source branch: i_d = gm * v_gs + (v_drain - v_source) / ro
    """
    id: str
    gate_node: str
    drain_node: str
    source_node: str
    gm: Union[float, str]  # Transconductance
    ro: Optional[Union[float, str]] = None  # Drain-source resistance (1 / (lambda * Id))
    cgs: Optional[Union[float, str]] = None  # Gate-source capacitance
    cgd: Optional[Union[float, str]] = None  # Gate-drain capacitance


@dataclass
class ACSolverProblem:
    """A complete, self-contained AC small-signal problem ready for equation formulation."""
    circuit_id: str
    nodes: dict[str, SolverNode] = field(default_factory=dict)
    node_aliases: dict[str, str] = field(default_factory=dict)  # Maps coalesced nodes to canonical node ID
    resistors: list[ResistorBranch] = field(default_factory=list)
    sources: list[ACSourceBranch] = field(default_factory=list)
    bjts: list[BJTHybridPiDevice] = field(default_factory=list)
    mosfets: list[MOSFETSmallSignalDevice] = field(default_factory=list)
    find_targets: list[str] = field(default_factory=list)

    def canonical_node(self, node_id: str) -> str:
        """Resolves node aliases to their canonical electrical node ID."""
        curr = node_id
        visited = set()
        while curr in self.node_aliases and curr not in visited:
            visited.add(curr)
            curr = self.node_aliases[curr]
        return curr

    def get_unknown_nodes(self) -> list[str]:
        """Returns canonical node IDs whose AC potentials are unknown variables to solve for."""
        return [
            node_id for node_id, node in self.nodes.items()
            if not node.is_fixed and node_id not in self.node_aliases
        ]
