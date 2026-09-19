"""Tests for AI.ciOne DC Analytical Solver (SymPy)."""

from pathlib import Path
import pytest
import sympy as sp

from aicione.ingest import ingest
from aicione.solver.dc import DCSolution, solve_dc
from aicione.solver.extractor import extract_dc_problem

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_solve_dc_bjt_numerical_amplifier():
    """Validates DC operating point for bjt_amplifier.ci against hand calculations."""
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    ingested = ingest(ci_path)
    dc_problem = extract_dc_problem(ingested)
    solution = solve_dc(dc_problem, vt=0.026)

    assert isinstance(solution, DCSolution)
    assert solution.circuit_id == "bjt_ce_amplifier"

    # Node voltages verification
    # V(N1) = Base voltage ~ 1.999 V
    v_base = float(solution.node_voltages["N1"])
    assert v_base == pytest.approx(1.9992, rel=1e-3)

    # V(N3) = Emitter voltage ~ 1.299 V
    v_emitter = float(solution.node_voltages["N3"])
    assert v_emitter == pytest.approx(1.2992, rel=1e-3)

    # V(N2) = Collector voltage ~ 9.170 V
    v_collector = float(solution.node_voltages["N2"])
    assert v_collector == pytest.approx(9.1701, rel=1e-3)

    # BJT operating point verification
    assert "Q1" in solution.bjt_operating_points
    q1 = solution.bjt_operating_points["Q1"]

    # IB ~ 12.86 uA, IC ~ 1.286 mA, IE ~ 1.299 mA
    assert float(q1.ib) == pytest.approx(12.863e-6, rel=1e-3)
    assert float(q1.ic) == pytest.approx(1.2863e-3, rel=1e-3)
    assert float(q1.ie) == pytest.approx(1.2992e-3, rel=1e-3)

    # VBE = 0.7 V, VCE ~ 7.871 V
    assert float(q1.vbe) == pytest.approx(0.7, abs=1e-6)
    assert float(q1.vce) == pytest.approx(7.8709, rel=1e-3)

    # Small-signal parameters: gm = Ic / Vt ~ 49.47 mS, rpi = beta / gm ~ 2.02 kOhm
    assert q1.gm == pytest.approx(49.47e-3, rel=1e-3)
    assert q1.rpi == pytest.approx(2021.3, rel=1e-2)


def test_solve_dc_purely_symbolic_divider():
    """Validates that SymPy algebraically derives the exact symbolic formula for literal variables."""
    raw_ci = """
ceml_version: "0.1"
circuit_id: "symbolic_divider"
description: "Symbolic voltage divider"

nodes:
    - id: GND
      type: ground
    - id: Vin
      type: supply
      value: Vin
    - id: Vout
      type: output

components:
    - id: R1
      type: resistor
      value: R1
      pins: [Vin, Vout]
    - id: R2
      type: resistor
      value: R2
      pins: [Vout, GND]

specs:
  find:
    - Vout
"""
    ingested = ingest(raw_ci)
    dc_problem = extract_dc_problem(ingested)
    solution = solve_dc(dc_problem)

    v_out_expr = solution.node_voltages["Vout"]

    # Define symbolic expected formula: Vout = Vin * R2 / (R1 + R2)
    R1, R2, Vin = sp.symbols("R1 R2 Vin")
    expected_expr = Vin * R2 / (R1 + R2)

    # Prove exact mathematical equivalence (difference simplifies to 0)
    difference = sp.simplify(v_out_expr - expected_expr)
    assert difference == 0, f"Expected {expected_expr}, got {v_out_expr}"
