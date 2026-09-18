"""Tests for AI.ciOne Circuit Ingestion Module."""

from pathlib import Path
import pytest
from aicione.ingest import IngestedCircuit, IngestionError, ingest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_ingest_bjt_ce_amplifier():
    ci_path = FIXTURES_DIR / "bjt_amplifier.ci"
    assert ci_path.exists(), f"Fixture path not found: {ci_path}"

    ingested = ingest(ci_path)
    assert isinstance(ingested, IngestedCircuit)
    assert ingested.circuit_id == "bjt_ce_amplifier"

    # Verify component categories
    assert "Q1" in ingested.semiconductors
    assert "RC" in ingested.passives
    assert "C1" in ingested.passives

    # Verify DC vs AC regime partitioning:
    # Capacitors must NOT be in DC active components (they block DC)
    assert "C1" not in ingested.dc_active_components
    assert "C2" not in ingested.dc_active_components

    # Capacitors MUST be in AC active components
    assert "C1" in ingested.ac_active_components
    assert "C2" in ingested.ac_active_components

    # Resistors and BJT active in both
    assert "RC" in ingested.dc_active_components
    assert "RC" in ingested.ac_active_components
    assert "Q1" in ingested.dc_active_components
    assert "Q1" in ingested.ac_active_components

    # Check find targets
    targets = ingested.get_find_targets()
    assert len(targets) == 2
    assert "Av(Vout, Vin)" in targets


def test_ingest_nmos_circuit():
    ci_path = FIXTURES_DIR / "nmos_follower.ci"
    assert ci_path.exists(), f"Fixture path not found: {ci_path}"

    ingested = ingest(ci_path)
    assert ingested.circuit_id == "nmos_source_follower"
    assert "Q1" in ingested.semiconductors
    assert "Cext" in ingested.ac_active_components
    assert "Cext" not in ingested.dc_active_components
    assert "Cext" in ingested.get_find_targets()


def test_ingest_from_raw_string():
    raw_ci = """
ceml_version: "0.1"
circuit_id: "voltage_divider"
description: "Simple resistive divider"

nodes:
    - id: GND
      type: ground
    - id: Vin
      type: input
    - id: Vout
      type: output

components:
    - id: R1
      type: resistor
      value: 10k
      pins: [Vin, Vout]
    - id: R2
      type: resistor
      value: 10k
      pins: [Vout, GND]

specs:
  find:
    - Vout
"""
    ingested = ingest(raw_ci)
    assert ingested.circuit_id == "voltage_divider"
    assert len(ingested.nodes) == 3
    assert len(ingested.passives) == 2
    assert "R1" in ingested.dc_active_components
    assert "R2" in ingested.dc_active_components


def test_ingest_failing_circuit_raises_ingestion_error():
    ci_path = FIXTURES_DIR / "invalid_circuit.ci"
    with pytest.raises(IngestionError) as exc_info:
        ingest(ci_path)

    assert "failed CEML validation" in str(exc_info.value)
    assert len(exc_info.value.errors) > 0
    assert any(e.code == "ERR_MISSING_VALUE_NOT_IN_FIND" for e in exc_info.value.errors)
