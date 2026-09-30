"""AI.ciOne Solver Package.

Contains mathematical problem models and equation extractors for DC and AC analysis.
"""

from aicione.solver.ac import ACSolution, ACSolver, solve_ac
from aicione.solver.dc import BJTQuiescentPoint, DCSolution, DCSolver, solve_dc
from aicione.solver.extractor import extract_ac_problem, extract_dc_problem
from aicione.solver.models import (
    ACSourceBranch,
    ACSolverProblem,
    BJTDCDevice,
    BJTHybridPiDevice,
    CapacitorBranch,
    DCSolverProblem,
    DCSourceBranch,
    MOSFETDCDevice,
    MOSFETSmallSignalDevice,
    ResistorBranch,
    SolverNode,
)
from aicione.solver.octc import (
    OCTCSolution,
    OCTCSolver,
    OCTCTimeConstant,
    solve_octc,
)

__all__ = [
    "extract_dc_problem",
    "extract_ac_problem",
    "solve_dc",
    "solve_ac",
    "solve_octc",
    "DCSolver",
    "ACSolver",
    "OCTCSolver",
    "DCSolution",
    "ACSolution",
    "OCTCSolution",
    "OCTCTimeConstant",
    "BJTQuiescentPoint",
    "DCSolverProblem",
    "SolverNode",
    "ResistorBranch",
    "CapacitorBranch",
    "DCSourceBranch",
    "BJTDCDevice",
    "MOSFETDCDevice",
    "ACSourceBranch",
    "BJTHybridPiDevice",
    "MOSFETSmallSignalDevice",
    "ACSolverProblem",
]

