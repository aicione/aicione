"""AI.ciOne - Analytical Reasoning & Symbolic Solving Engine for Analog Electronic Circuits.

Intermediary engine of the AI.ciOne project, bridging CEML circuit specifications
to deterministic symbolic equations and solutions.
"""

from aicione.ingest import IngestedCircuit, IngestionError, ingest
from aicione.pipeline import CircuitSolution, solve_circuit

__all__ = [
    "ingest",
    "IngestedCircuit",
    "IngestionError",
    "solve_circuit",
    "CircuitSolution",
]

__version__ = "0.1.0"
