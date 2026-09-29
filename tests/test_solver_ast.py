"""Tests for AI.ciOne Solver AST & DC Problem Extractor."""

from pathlib import Path
import pytest
from aicione.ingest import ingest
from aicione.solver.extractor import extract_ac_problem, extract_dc_problem
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

    # Unknown AC nodes exclude GND, AC virtual grounds (VCC), and aliased nodes
    unknowns = problem.get_unknown_nodes()
    assert "GND" not in unknowns
    assert "VCC" not in unknowns
    assert set(unknowns) == {"N1", "N2"}


def test_extract_ac_problem_bjt_amplifier():
    """Validates automatic AC problem extraction from bjt_amplifier.ci."""
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    ingested = ingest(ci_path)
    ac_prob = extract_ac_problem(ingested)

    assert isinstance(ac_prob, ACSolverProblem)
    assert ac_prob.circuit_id == "bjt_ce_amplifier"

    # Virtual AC grounds
    assert ac_prob.nodes["GND"].is_fixed
    assert ac_prob.nodes["VCC"].is_fixed
    assert ac_prob.nodes["VCC"].fixed_voltage == 0.0

    # Node aliasing via coupling capacitors
    assert ac_prob.canonical_node("N1") == "Vin"
    assert ac_prob.canonical_node("N2") == "Vout"

    # Active BJT with linearized parameters
    assert len(ac_prob.bjts) == 1
    q1 = ac_prob.bjts[0]
    assert q1.id == "Q1"
    assert q1.base_node == "Vin"
    assert q1.collector_node == "Vout"
    assert q1.emitter_node == "N3"

    # gm ~ 49.47 mS, rpi ~ 2021 Ohm
    assert isinstance(q1.gm, float)
    assert q1.gm == pytest.approx(49.47e-3, rel=1e-2)
    assert q1.rpi == pytest.approx(2021.3, rel=1e-2)
    assert q1.ro is None

    # Resistors present in AC
    resistor_map = {r.id: (r.node_a, r.node_b, r.resistance) for r in ac_prob.resistors}
    assert "R1" in resistor_map
    assert "R2" in resistor_map
    assert "RC" in resistor_map
    assert "RE" in resistor_map
    assert "RL" in resistor_map

    # Unknown AC nodes (canonical variables to solve for)
    unknowns = set(ac_prob.get_unknown_nodes())
    assert unknowns == {"Vin", "N3", "Vout"}

    # Input test source automatically connected to input node
    assert len(ac_prob.sources) == 1
    src = ac_prob.sources[0]
    assert src.node_p == "Vin"
    assert src.node_n == "GND"
    assert src.value == 1.0

    # Targets
    assert ac_prob.find_targets == ["Av(Vout, Vin)", "Rin(Vin, GND)"]


def test_extract_ac_problem_bypassed_emitter_resistor():
    """Validates that a resistor bypassed by a shorted capacitor is dropped from AC branches."""
    raw_ci = """
ceml_version: "0.1"
circuit_id: "ce_bypassed"
description: "Common-emitter with fully bypassed RE"

nodes:
    - id: GND
      type: ground
    - id: Vin
      type: input
    - id: VCC
      type: supply
      value: 12
    - id: Vout
      type: output
    - id: N3

components:
    - id: RE
      type: resistor
      value: 1k
      pins: [N3, GND]
    - id: CE
      type: capacitor
      pins: [N3, GND]
      ac_behavior: short_circuit
    - id: RC
      type: resistor
      value: 2k
      pins: [VCC, Vout]

specs:
  find:
    - Av(Vout, Vin)
"""
    ingested = ingest(raw_ci)
    ac_prob = extract_ac_problem(ingested)

    # N3 must coalesce with GND
    assert ac_prob.canonical_node("N3") == "GND"

    # RE is in parallel with shorted CE, so both its terminals are GND -> must be dropped
    resistor_ids = {r.id for r in ac_prob.resistors}
    assert "RE" not in resistor_ids
    assert "RC" in resistor_ids


def test_extract_ac_problem_high_frequency_capacitors():
    """Validates that internal junction capacitances and discrete HF capacitors are extracted."""
    ci_path = FIXTURES_DIR / "cg_nmos_freq_response.ci"
    ingested = ingest(ci_path)
    ac_prob = extract_ac_problem(ingested)

    assert len(ac_prob.capacitors) == 2
    cap_map = {c.id: c for c in ac_prob.capacitors}

    # Cgs between GND (gate) and N1 (source)
    assert "Cgs_M1" in cap_map
    cgs = cap_map["Cgs_M1"]
    assert cgs.node_a == "GND"
    assert cgs.node_b == "N1"
    assert cgs.capacitance == pytest.approx(1.1e-12)
    assert cgs.is_internal is True

    # Cgd between GND (gate) and Vout (drain)
    assert "Cgd_M1" in cap_map
    cgd = cap_map["Cgd_M1"]
    assert cgd.node_a == "GND"
    assert cgd.node_b == "Vout"
    assert cgd.capacitance == pytest.approx(4e-12)
    assert cgd.is_internal is True


def test_extract_ac_problem_cascade_discrete_and_internal_capacitors():
    """Validates extraction of discrete load capacitor CL alongside BJT Cpi and Cmu."""
    raw_ci = """
ceml_version: "0.1"
circuit_id: "bjt_with_cl"
description: "BJT amplifier with discrete load capacitor and internal capacitances"

nodes:
    - id: GND
      type: ground
    - id: Vin
      type: input
    - id: VCC
      type: supply
      value: 12
    - id: Vout
      type: output

components:
    - id: Q1
      type: BJT
      polarity: NPN
      pins:
        base: Vin
        collector: Vout
        emitter: GND
    - id: RC
      type: resistor
      value: 2k
      pins: [VCC, Vout]
    - id: CL
      type: capacitor
      value: 15p
      pins: [Vout, GND]

specs:
  given:
    - hie(Q1): 1k
    - hfe(Q1): 100
    - Cpi(Q1): 50p
    - Cmu(Q1): 5p
  find:
    - Av(Vout, Vin)
"""
    ingested = ingest(raw_ci)
    ac_prob = extract_ac_problem(ingested)

    # 3 capacitive branches: CL, Cpi_Q1, Cmu_Q1
    assert len(ac_prob.capacitors) == 3
    cap_map = {c.id: c for c in ac_prob.capacitors}

    assert "CL" in cap_map
    assert cap_map["CL"].is_internal is False
    assert cap_map["CL"].capacitance == pytest.approx(15e-12)

    assert "Cpi_Q1" in cap_map
    assert cap_map["Cpi_Q1"].is_internal is True
    assert cap_map["Cpi_Q1"].capacitance == pytest.approx(50e-12)

    assert "Cmu_Q1" in cap_map
    assert cap_map["Cmu_Q1"].is_internal is True
    assert cap_map["Cmu_Q1"].capacitance == pytest.approx(5e-12)

    # gm deduced from hfe / hie = 100 / 1000 = 0.1 S
    assert ac_prob.bjts[0].gm == pytest.approx(0.1)


