"""Tests for AI.ciOne Solver AST & DC Problem Extractor."""

from pathlib import Path
from aicione.ingest import ingest
from aicione.solver.extractor import extract_dc_problem
from aicione.solver.models import DCSolverProblem

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_dc_problem_bjt():
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    ingested = ingest(ci_path)
    dc_problem = extract_dc_problem(ingested)

    assert isinstance(dc_problem, DCSolverProblem)
    assert dc_problem.circuit_id == "bjt_ce_amplifier"

    # Fixed vs unknown nodes
    assert dc_problem.nodes["GND"].is_ground
    assert dc_problem.nodes["GND"].fixed_voltage == 0.0
    assert dc_problem.nodes["VCC"].fixed_voltage == 12.0
    assert dc_problem.nodes["N1"].fixed_voltage is None

    unknowns = dc_problem.get_unknown_nodes()
    assert "N1" in unknowns
    assert "N2" in unknowns
    assert "N3" in unknowns

    # Resistors in DC
    resistor_ids = {r.id for r in dc_problem.resistors}
    assert {"R1", "R2", "RC", "RE", "RL"}.issubset(resistor_ids)

    # Capacitors must NOT be in DC resistors/branches
    assert "C1" not in resistor_ids
    assert "C2" not in resistor_ids

    # BJT
    assert len(dc_problem.bjts) == 1
    q1 = dc_problem.bjts[0]
    assert q1.id == "Q1"
    assert q1.base_node == "N1"
    assert q1.collector_node == "N2"
    assert q1.emitter_node == "N3"
    assert q1.hfe == 100.0
    assert q1.vbe == 0.7


def test_extract_dc_problem_nmos():
    ci_path = FIXTURES_DIR / "nmos_follower.ci"
    ingested = ingest(ci_path)
    dc_problem = extract_dc_problem(ingested)

    assert len(dc_problem.mosfets) == 1
    m1 = dc_problem.mosfets[0]
    assert m1.id == "Q1"
    assert m1.gate_node == "N1"
    assert m1.drain_node == "VDD"
    assert m1.source_node == "N2"

    # Capacitors C1, C2, Cext must NOT be in DC elements
    resistor_ids = {r.id for r in dc_problem.resistors}
    assert "Cext" not in resistor_ids
    assert "C1" not in resistor_ids
