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
