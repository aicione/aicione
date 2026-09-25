"""Tests for AI.ciOne CLI commands."""

from pathlib import Path
import pytest
from aicione.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_cli_inspect_dc_success(capsys):
    fixture_path = str(FIXTURES_DIR / "bjt_amplifier.ci")
    exit_code = main(["inspect-dc", fixture_path])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "AI.ciOne DC Solver Problem: bjt_ce_amplifier" in captured.out
    assert "Q1" in captured.out
    assert "Unknown Potential" in captured.out


def test_cli_solve_dc_success(capsys):
    fixture_path = str(FIXTURES_DIR / "bjt_amplifier.ci")
    exit_code = main(["solve-dc", fixture_path])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "AI.ciOne DC Operating Point Solution: bjt_ce_amplifier" in captured.out
    assert "Transistor Q1" in captured.out
    assert "IB  =" in captured.out
    assert "IC  =" in captured.out
    assert "gm  =" in captured.out
    assert "rpi =" in captured.out


def test_cli_file_not_found(capsys):
    exit_code = main(["solve-dc", "non_existent.ci"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: File not found" in captured.err


def test_cli_inspect_ac_success(capsys):
    fixture_path = str(FIXTURES_DIR / "bjt_amplifier.ci")
    exit_code = main(["inspect-ac", fixture_path])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "AI.ciOne AC Small-Signal Problem: bjt_ce_amplifier" in captured.out
    assert "Coalesced/Aliased -> Vin" in captured.out
    assert "AC Virtual Ground" in captured.out
    assert "Hybrid-pi: Base=Vin, Collector=Vout, Emitter=N3" in captured.out
    assert "gm = 49.47 mS" in captured.out
    assert "rpi = 2.02 kOhm" in captured.out
    assert "Av(Vout, Vin)" in captured.out


def test_cli_solve_ac_success(capsys):
    fixture_path = str(FIXTURES_DIR / "bjt_amplifier.ci")
    exit_code = main(["solve-ac", fixture_path])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "AI.ciOne AC Small-Signal Solution: bjt_ce_amplifier" in captured.out
    assert "Av(Vout, Vin)" in captured.out
    assert "-1.7504" in captured.out
    assert "Rin(Vin, GND)" in captured.out
    assert "7.635 kOhm" in captured.out
    assert "v(Vin   ) =     1.0000 V" in captured.out
    assert "v(Vout  ) =    -1.7504 V" in captured.out


