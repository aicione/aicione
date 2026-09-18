"""Circuit Ingestion Module.

Loads and validates .ci files using ceml-lang, performing initial categorization
into electrical component groups and analytical regimes (DC bias vs AC small-signal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import ceml
from ceml.models import (
    AcBehavior,
    Circuit,
    Component,
    ComponentType,
    Node,
    NodeType,
    Regime,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)


class IngestionError(Exception):
    """Raised when a circuit fails validation or cannot be ingested by AI.ciOne."""

    def __init__(self, message: str, errors: Optional[list[ValidationError]] = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class IngestedCircuit:
    """Enriched circuit representation prepared for the analytical solver."""

    circuit: Circuit
    validation: ValidationResult

    # Categorized components
    passives: dict[str, Component] = field(default_factory=dict)
    semiconductors: dict[str, Component] = field(default_factory=dict)
    sources: dict[str, Component] = field(default_factory=dict)
    opamps: dict[str, Component] = field(default_factory=dict)

    # Regime decomposition
    dc_active_components: dict[str, Component] = field(default_factory=dict)
    ac_active_components: dict[str, Component] = field(default_factory=dict)

    @property
    def circuit_id(self) -> str:
        return self.circuit.circuit_id

    @property
    def nodes(self) -> dict[str, Node]:
        return self.circuit.nodes

    @property
    def components(self) -> dict[str, Component]:
        return self.circuit.components

    @property
    def warnings(self) -> list[ValidationWarning]:
        return self.validation.warnings

    def get_component(self, comp_id: str) -> Optional[Component]:
        return self.circuit.components.get(comp_id)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.circuit.nodes.get(node_id)

    def get_find_targets(self) -> list[str]:
        """Returns the list of raw targets requested in specs.find."""
        if not self.circuit.specs or not self.circuit.specs.find:
            return []
        targets = []
        for item in self.circuit.specs.find:
            targets.append(item.raw if item.raw else str(item.target))
        return targets


def _categorize_circuit(circuit: Circuit, validation: ValidationResult) -> IngestedCircuit:
    """Categorizes circuit components and partitions them by analytical regime."""
    passives: dict[str, Component] = {}
    semiconductors: dict[str, Component] = {}
    sources: dict[str, Component] = {}
    opamps: dict[str, Component] = {}

    dc_active: dict[str, Component] = {}
    ac_active: dict[str, Component] = {}

    for comp_id, comp in circuit.components.items():
        # Category classification
        if comp.type in (
            ComponentType.RESISTOR.value,
            ComponentType.CAPACITOR.value,
            ComponentType.INDUCTOR.value,
        ):
            passives[comp_id] = comp
        elif comp.type in (
            ComponentType.BJT.value,
            ComponentType.MOSFET.value,
            ComponentType.JFET.value,
            ComponentType.DIODE.value,
        ):
            semiconductors[comp_id] = comp
        elif comp.type in (
            ComponentType.VOLTAGE_SOURCE.value,
            ComponentType.CURRENT_SOURCE.value,
            ComponentType.VCVS.value,
            ComponentType.VCCS.value,
            ComponentType.CCVS.value,
            ComponentType.CCCS.value,
        ):
            sources[comp_id] = comp
        elif comp.type == ComponentType.OPAMP.value:
            opamps[comp_id] = comp

        # Regime decomposition
        # 1. Resistors: active in both DC and AC
        if comp.type == ComponentType.RESISTOR.value:
            dc_active[comp_id] = comp
            ac_active[comp_id] = comp

        # 2. Capacitors: open circuit in DC by physical definition; active in AC
        elif comp.type == ComponentType.CAPACITOR.value:
            ac_active[comp_id] = comp

        # 3. Inductors: short circuit in DC; active in AC
        elif comp.type == ComponentType.INDUCTOR.value:
            ac_active[comp_id] = comp

        # 4. Independent Sources: active exclusively in their declared regime (Decision #20)
        elif comp.type in (ComponentType.VOLTAGE_SOURCE.value, ComponentType.CURRENT_SOURCE.value):
            if comp.regime == Regime.DC:
                dc_active[comp_id] = comp
            elif comp.regime == Regime.AC:
                ac_active[comp_id] = comp

        # 5. Semiconductors: active in DC (quiescent bias point) and in AC (small-signal linear model)
        elif comp.type in (
            ComponentType.BJT.value,
            ComponentType.MOSFET.value,
            ComponentType.JFET.value,
            ComponentType.DIODE.value,
        ):
            dc_active[comp_id] = comp
            ac_active[comp_id] = comp

        # 6. OpAmps & Dependent sources: active in both
        elif comp.type in (
            ComponentType.OPAMP.value,
            ComponentType.VCVS.value,
            ComponentType.VCCS.value,
            ComponentType.CCVS.value,
            ComponentType.CCCS.value,
        ):
            dc_active[comp_id] = comp
            ac_active[comp_id] = comp

    return IngestedCircuit(
        circuit=circuit,
        validation=validation,
        passives=passives,
        semiconductors=semiconductors,
        sources=sources,
        opamps=opamps,
        dc_active_components=dc_active,
        ac_active_components=ac_active,
    )


def ingest(source: Union[str, Path]) -> IngestedCircuit:
    """Ingests a CEML circuit from a file path or raw YAML string.

    Args:
        source: Path to a .ci file, or a raw YAML string containing a CEML circuit.

    Returns:
        IngestedCircuit: Enriched circuit representation partitioned by regime.

    Raises:
        IngestionError: If the circuit has fatal validation errors.
    """
    path = Path(source) if isinstance(source, (str, Path)) and not ("\n" in str(source)) else None

    if path and path.exists() and path.is_file():
        circuit = ceml.load(path)
    else:
        circuit = ceml.loads(str(source))

    validation_report = ceml.validate(circuit)

    if not validation_report.is_valid:
        error_msgs = "\n".join(f"  - [{e.code}] {e.message}" for e in validation_report.errors)
        raise IngestionError(
            f"Circuit '{circuit.circuit_id}' failed CEML validation with {len(validation_report.errors)} error(s):\n{error_msgs}",
            errors=validation_report.errors,
        )

    return _categorize_circuit(circuit, validation_report)
