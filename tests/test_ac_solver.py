"""Tests for AI.ciOne AC Small-Signal Analytical Solver (SymPy)."""

from pathlib import Path
import pytest
import sympy as sp

from aicione.ingest import ingest
from aicione.solver.ac import ACSolution, solve_ac
from aicione.solver.extractor import extract_ac_problem
from aicione.solver.models import (
    ACSourceBranch,
    ACSolverProblem,
    BJTHybridPiDevice,
    ResistorBranch,
    SolverNode,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_solve_ac_numerical_bjt_amplifier():
    """Validates AC small-signal solution for bjt_amplifier.ci against hand calculations."""
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    ingested = ingest(ci_path)
    ac_problem = extract_ac_problem(ingested)
    solution = solve_ac(ac_problem)

    assert isinstance(solution, ACSolution)
    assert solution.circuit_id == "bjt_ce_amplifier"

    # Evaluated specs
    assert "Av(Vout, Vin)" in solution.evaluated_specs
    assert "Rin(Vin, GND)" in solution.evaluated_specs

    # Voltage Gain Av = -1.7504
    av_val = float(solution.evaluated_specs["Av(Vout, Vin)"])
    assert av_val == pytest.approx(-1.7504, rel=1e-3)

    # Input resistance Rin = 7.635 kOhm
    rin_val = float(solution.evaluated_specs["Rin(Vin, GND)"])
    assert rin_val == pytest.approx(7634.56, rel=1e-3)

    # Node potentials verification
    assert float(solution.node_voltages["Vin"]) == pytest.approx(1.0, abs=1e-6)
    assert float(solution.node_voltages["N1"]) == pytest.approx(1.0, abs=1e-6)  # Aliased to Vin
    assert float(solution.node_voltages["Vout"]) == pytest.approx(-1.7504, rel=1e-3)
    assert float(solution.node_voltages["N2"]) == pytest.approx(-1.7504, rel=1e-3)  # Aliased to Vout
    assert float(solution.node_voltages["N3"]) == pytest.approx(0.98038, rel=1e-3)
    assert float(solution.node_voltages["GND"]) == 0.0
    assert float(solution.node_voltages["VCC"]) == 0.0  # Virtual AC ground


def test_solve_ac_purely_symbolic_amplifier():
    """Validates that SymPy algebraically derives the exact closed-form formula for an AC amplifier."""
    # Define purely symbolic problem for common-emitter amplifier with RE
    RC, RL, RE, gm, rpi = sp.symbols("RC RL RE gm rpi")

    problem = ACSolverProblem(
        circuit_id="symbolic_ce_amp",
        nodes={
            "GND": SolverNode(id="GND", is_ground=True, fixed_voltage=0.0),
            "Vin": SolverNode(id="Vin", is_ground=False, fixed_voltage=None),
            "Vout": SolverNode(id="Vout", is_ground=False, fixed_voltage=None),
            "N3": SolverNode(id="N3", is_ground=False, fixed_voltage=None),
        },
        resistors=[
            ResistorBranch(id="RC", node_a="Vout", node_b="GND", resistance=RC),
            ResistorBranch(id="RL", node_a="Vout", node_b="GND", resistance=RL),
            ResistorBranch(id="RE", node_a="N3", node_b="GND", resistance=RE),
        ],
        bjts=[
            BJTHybridPiDevice(
                id="Q1",
                base_node="Vin",
                collector_node="Vout",
                emitter_node="N3",
                gm=gm,
                rpi=rpi,
                ro=None,
            )
        ],
        sources=[
            ACSourceBranch(id="V_in", node_p="Vin", node_n="GND", value=1.0, is_voltage=True)
        ],
        find_targets=["Av(Vout, Vin)"],
    )

    solution = solve_ac(problem)
    derived_av = solution.evaluated_specs["Av(Vout, Vin)"]

    # Expected analytical formula:
    # Av = - (RC || RL) * gm * rpi / (rpi + (1 + gm*rpi)*RE)
    #    = - (RC*RL/(RC+RL)) * gm * rpi / (rpi + RE*(1 + gm*rpi))
    expected_av = - (RC * RL * gm * rpi) / ((RC + RL) * (rpi + RE * (1 + gm * rpi)))

    # Prove exact mathematical equivalence (difference simplifies algebraically to 0)
    difference = sp.simplify(derived_av - expected_av)
    assert difference == 0, f"Expected {expected_av}, got {derived_av}"
