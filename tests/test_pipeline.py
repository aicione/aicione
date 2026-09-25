"""Tests for AI.ciOne End-to-End Solving Pipeline."""

import json
from pathlib import Path
import pytest

from aicione.pipeline import CircuitSolution, solve_circuit

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_solve_circuit_bjt_amplifier():
    """Validates complete multi-regime solving on bjt_amplifier.ci."""
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    solution = solve_circuit(ci_path)

    assert isinstance(solution, CircuitSolution)
    assert solution.circuit_id == "bjt_ce_amplifier"
    assert solution.description == "Common-emitter BJT amplifier test fixture"

    # Evaluated specs in find
    assert "Av(Vout, Vin)" in solution.find_results
    assert "Rin(Vin, GND)" in solution.find_results
    assert float(solution.find_results["Av(Vout, Vin)"]) == pytest.approx(-1.7504, rel=1e-3)
    assert float(solution.find_results["Rin(Vin, GND)"]) == pytest.approx(7634.56, rel=1e-3)

    # Sub-solutions present
    assert solution.dc_solution is not None
    assert solution.ac_solution is not None

    # DC Quiescent point
    q1_dc = solution.dc_solution.bjt_operating_points["Q1"]
    assert float(q1_dc.ic) == pytest.approx(1.286e-3, rel=1e-3)
    assert float(q1_dc.vce) == pytest.approx(7.871, rel=1e-3)

    # Warnings collected from validation
    assert len(solution.warnings) >= 1
    assert any("WARN_DEFAULT_RO_INF" in w for w in solution.warnings)


def test_solve_circuit_mixed_dc_and_ac_targets():
    """Validates that a circuit declaring both DC and AC targets in specs.find solves both."""
    raw_ci = """
ceml_version: "0.1"
circuit_id: "ce_mixed_targets"
description: "Amplifier with mixed DC and AC find targets"

nodes:
    - id: GND
      type: ground
    - id: Vin
      type: input
    - id: N1
    - id: VCC
      type: supply
      value: 12
    - id: N2
    - id: N3
    - id: Vout
      type: output

components:
    - id: C1
      type: capacitor
      pins: [Vin, N1]
      ac_behavior: short_circuit
    - id: R1
      type: resistor
      value: 47k
      pins: [VCC, N1]
    - id: R2
      type: resistor
      value: 10k
      pins: [N1, GND]
    - id: Q1
      type: BJT
      polarity: NPN
      pins:
        base: N1
        collector: N2
        emitter: N3
    - id: RC
      type: resistor
      value: 2k2
      pins: [VCC, N2]
    - id: RE
      type: resistor
      value: 1k
      pins: [N3, GND]
    - id: C2
      type: capacitor
      pins: [N2, Vout]
      ac_behavior: short_circuit
    - id: RL
      type: resistor
      value: 10k
      pins: [Vout, GND]

specs:
  given:
    - hfe(Q1): 100
  find:
    - Ic(Q1)
    - Vce(Q1)
    - Av(Vout, Vin)
    - Rin(Vin, GND)
"""
    solution = solve_circuit(raw_ci)

    # All 4 targets must be evaluated
    assert "Ic(Q1)" in solution.find_results
    assert "Vce(Q1)" in solution.find_results
    assert "Av(Vout, Vin)" in solution.find_results
    assert "Rin(Vin, GND)" in solution.find_results

    # Check DC results
    assert float(solution.find_results["Ic(Q1)"]) == pytest.approx(1.286e-3, rel=1e-3)
    assert float(solution.find_results["Vce(Q1)"]) == pytest.approx(7.871, rel=1e-3)

    # Check AC results
    assert float(solution.find_results["Av(Vout, Vin)"]) == pytest.approx(-1.7504, rel=1e-3)
    assert float(solution.find_results["Rin(Vin, GND)"]) == pytest.approx(7634.56, rel=1e-3)


def test_solve_circuit_to_dict_json_serializable():
    """Validates that solution.to_dict() can be serialized to JSON without error."""
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    solution = solve_circuit(ci_path)
    sol_dict = solution.to_dict()

    # Must serialize to JSON without throwing TypeError
    json_str = json.dumps(sol_dict)
    assert isinstance(json_str, str)
    assert "bjt_ce_amplifier" in json_str
    assert "-1.750" in json_str
