# ADR 0001: Repository Architecture and CEML-lang Integration

## Status
Accepted

## Context
AI.ciOne is the analytical reasoning and symbolic solving engine for analog circuits described in CEML (`.ci`).
A modular separation of concerns was agreed upon between:
1. `ceml-lang`: the declarative language grammar, YAML parser, semantic validator, and pure in-memory AST models.
2. `aicione`: the ingestion layer, regime decomposition (DC operating point vs AC small-signal), symbolic equation formulation, and analytical solving engine.

## Decision
1. **Repository Boundary**:
   - Keep `aicione` as an independent repository consuming `ceml-lang` as a dependency.
   - During development across sibling directories (`/ceml-lang` and `/aicione`), install `ceml-lang` in editable mode (`pip install -e ../ceml-lang`) inside `aicione/.venv`.
2. **Ingestion Pipeline**:
   - Provide an `aicione.ingest` module that serves as the gateway for reading `.ci` files or strings, executing CEML validation, checking for fatal errors, and returning an enriched circuit representation ready for the analytical solver.
3. **Analytical Core Dependency**:
   - Include `sympy` as the fundamental mathematical engine for exact symbolic calculations, avoiding numerical simulation or LLM arithmetic hallucinations.

## Consequences
- Clean decoupling between circuit description syntax and mathematical solving routines.
- Changes in the CEML language grammar are automatically and immediately reflected in `aicione` during local development via the editable installation.
