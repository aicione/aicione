"""AI.ciOne - Analytical Reasoning & Symbolic Solving Engine for Analog Electronic Circuits.

Intermediary engine of the AI.ciOne project, bridging CEML circuit specifications
to deterministic symbolic equations and solutions.
"""

from aicione.ingest import IngestedCircuit, IngestionError, ingest

__all__ = [
    "ingest",
    "IngestedCircuit",
    "IngestionError",
]

__version__ = "0.1.0"
