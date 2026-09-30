"""Unit tests for High-Frequency Analytical Solver and Open-Circuit Time Constants (OCTC)."""

import math
from pathlib import Path
import pytest

from aicione.ingest import ingest
from aicione.pipeline import solve_circuit
from aicione.solver.extractor import extract_ac_problem
from aicione.solver.octc import OCTCSolver, solve_octc


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).parent.parent.parent / "ceml-lang" / "examples"


def test_octc_cg_nmos_analytical_solution(fixtures_dir: Path):
    """Verifies OCTC calculation on common-gate NMOS amplifier (cg_nmos_freq_response.ci).

    Expected theoretical hand calculation:
    - Rth(Cgs) = Rgen // RS // (1/gm) = 50 // 3300 // 250 ~= 41.15 Ohm
    - tau(Cgs) = 41.15 Ohm * 1.1 pF ~= 4.526e-11 s
    - Rth(Cgd) = RD // RL = 3300 // 10000 ~= 2481.20 Ohm
    - tau(Cgd) = 2481.20 Ohm * 4.0 pF ~= 9.925e-9 s
    - sum(tau) ~= 9.970e-9 s
    - f_H = 1 / (2*pi*sum(tau)) ~= 15.963 MHz
    """
    ci_file = fixtures_dir / "cg_nmos_freq_response.ci"
    assert ci_file.exists()

    ingested = ingest(ci_file)
    ac_prob = extract_ac_problem(ingested)

    solver = OCTCSolver(ac_prob)
    solution = solver.solve()

    assert "Cgs_M1" in solution.time_constants
    assert "Cgd_M1" in solution.time_constants

    tc_gs = solution.time_constants["Cgs_M1"]
    tc_gd = solution.time_constants["Cgd_M1"]

    assert pytest.approx(float(tc_gs.rth), rel=1e-3) == 41.15
    assert pytest.approx(float(tc_gs.tau), rel=1e-3) == 4.526e-11

    assert pytest.approx(float(tc_gd.rth), rel=1e-3) == 2481.20
    assert pytest.approx(float(tc_gd.tau), rel=1e-3) == 9.9248e-9

    assert pytest.approx(float(solution.total_tau), rel=1e-3) == 9.9701e-9
    assert pytest.approx(float(solution.f_h) / 1e6, rel=1e-3) == 15.963
    assert pytest.approx(float(solution.w_h), rel=1e-3) == 1.003e8


def test_pipeline_evaluates_fp_target(fixtures_dir: Path):
    """Verifies that the end-to-end pipeline resolves Fp(Vout, Vs) and Av(Vout, Vs)."""
    ci_file = fixtures_dir / "cg_nmos_freq_response.ci"
    solution = solve_circuit(ci_file)

    assert "Av(Vout, Vs)" in solution.find_results
    assert "Fp(Vout, Vs)" in solution.find_results

    av_val = float(solution.find_results["Av(Vout, Vs)"])
    fp_val = float(solution.find_results["Fp(Vout, Vs)"])

    assert pytest.approx(av_val, rel=1e-3) == 8.1676
    assert pytest.approx(fp_val / 1e6, rel=1e-3) == 15.963


def test_octc_cascade_bjt_two_stage(examples_dir: Path):
    """Verifies OCTC on two-stage CC-NPN CB-PNP cascade with discrete CL (cc_npn_cb_pnp_cascade.ci)."""
    ci_file = examples_dir / "cc_npn_cb_pnp_cascade.ci"
    if not ci_file.exists():
        pytest.skip(f"Cascade example not found at {ci_file}")

    ingested = ingest(ci_file)
    ac_prob = extract_ac_problem(ingested)

    assert len(ac_prob.capacitors) == 5
    octc_sol = solve_octc(ac_prob)

    assert len(octc_sol.time_constants) == 5

    # Cmu_Q1 connects Vin and VCC, both AC-shorted to GND -> Rth must be 0
    assert "Cmu_Q1" in octc_sol.time_constants
    assert float(octc_sol.time_constants["Cmu_Q1"].rth) == 0.0

    # CL and Cmu_Q2 both connect between Vout and GND -> same Rth
    rth_cl = float(octc_sol.time_constants["CL"].rth)
    rth_cmu2 = float(octc_sol.time_constants["Cmu_Q2"].rth)
    assert pytest.approx(rth_cl, rel=1e-4) == rth_cmu2

    # Total tau and f_H check (~2.98 MHz)
    assert pytest.approx(float(octc_sol.f_h) / 1e6, rel=1e-2) == 2.979


def test_circuit_json_serialization_with_octc(fixtures_dir: Path):
    """Verifies that CircuitSolution.to_dict() serializes the OCTC section correctly."""
    ci_file = fixtures_dir / "cg_nmos_freq_response.ci"
    solution = solve_circuit(ci_file)
    sol_dict = solution.to_dict()

    assert "ac_solution" in sol_dict
    assert "octc" in sol_dict["ac_solution"]
    octc_data = sol_dict["ac_solution"]["octc"]

    assert "total_tau" in octc_data
    assert "f_h" in octc_data
    assert "time_constants" in octc_data
    assert "Cgs_M1" in octc_data["time_constants"]
    assert "Cgd_M1" in octc_data["time_constants"]
    assert octc_data["time_constants"]["Cgs_M1"]["is_internal"] is True
