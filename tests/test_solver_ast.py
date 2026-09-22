"""Tests for AI.ciOne Solver AST & DC Problem Extractor."""

from pathlib import Path
from aicione.ingest import ingest
from aicione.solver.extractor import extract_dc_problem
from aicione.solver.models import (
    ACSourceBranch,
    ACSolverProblem,
    BJTHybridPiDevice,
    DCSolverProblem,
    MOSFETSmallSignalDevice,
    SolverNode,
)

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


def test_bjt_hybrid_pi_device_model():
    """Tests BJTHybridPiDevice instantiation with numeric and symbolic parameters."""
    # Numeric instantiation
    bjt_num = BJTHybridPiDevice(
        id="Q1",
        base_node="N1",
        collector_node="N2",
        emitter_node="N3",
        gm=0.04947,
        rpi=2021.3,
        ro=100e3,
        cpi=10e-12,
        cmu=2e-12,
    )
    assert bjt_num.id == "Q1"
    assert bjt_num.gm == 0.04947
    assert bjt_num.rpi == 2021.3
    assert bjt_num.ro == 100000.0
    assert bjt_num.cpi == 10e-12
    assert bjt_num.cmu == 2e-12

    # Symbolic instantiation
    bjt_sym = BJTHybridPiDevice(
        id="Q_sym",
        base_node="B",
        collector_node="C",
        emitter_node="E",
        gm="gm",
        rpi="rpi",
        ro=None,
    )
    assert bjt_sym.gm == "gm"
    assert bjt_sym.rpi == "rpi"
    assert bjt_sym.ro is None


def test_mosfet_small_signal_device_model():
    """Tests MOSFETSmallSignalDevice instantiation."""
    fet_num = MOSFETSmallSignalDevice(
        id="M1",
        gate_node="G",
        drain_node="D",
        source_node="S",
        gm=2.5e-3,
        ro=50e3,
        cgs=5e-12,
    )
    assert fet_num.id == "M1"
    assert fet_num.gm == 2.5e-3
    assert fet_num.ro == 50000.0
    assert fet_num.cgs == 5e-12
    assert fet_num.cgd is None


def test_ac_solver_problem_and_node_aliasing():
    """Tests ACSolverProblem container, virtual AC grounds, and canonical node resolution."""
    problem = ACSolverProblem(
        circuit_id="test_ac_amp",
        nodes={
            "GND": SolverNode(id="GND", is_ground=True, fixed_voltage=0.0),
            "VCC": SolverNode(id="VCC", is_ground=False, fixed_voltage=0.0),  # AC virtual ground
            "Vin": SolverNode(id="Vin", is_ground=False, fixed_voltage=None),
            "N1": SolverNode(id="N1", is_ground=False, fixed_voltage=None),
            "N2": SolverNode(id="N2", is_ground=False, fixed_voltage=None),
            "Vout": SolverNode(id="Vout", is_ground=False, fixed_voltage=None),
        },
        node_aliases={
            "Vin": "N1",   # Shorted by input coupling capacitor
            "Vout": "N2",  # Shorted by output coupling capacitor
        },
        sources=[
            ACSourceBranch(id="Vin_src", node_p="Vin", node_n="GND", value=1.0, is_voltage=True),
        ],
        find_targets=["Av(Vout, Vin)", "Rin(Vin, GND)"],
    )

    assert problem.circuit_id == "test_ac_amp"

    # Canonical node resolution (coalesced nodes)
    assert problem.canonical_node("Vin") == "N1"
    assert problem.canonical_node("N1") == "N1"
    assert problem.canonical_node("Vout") == "N2"
    assert problem.canonical_node("GND") == "GND"

    # Chained aliasing
    problem.node_aliases["N0"] = "Vin"
    assert problem.canonical_node("N0") == "N1"

    # Unknown AC nodes exclude GND and AC virtual grounds (VCC)
    unknowns = problem.get_unknown_nodes()
    assert "GND" not in unknowns
    assert "VCC" not in unknowns
    assert set(unknowns) == {"Vin", "N1", "N2", "Vout"}

