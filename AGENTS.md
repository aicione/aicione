# AGENTS.md

Instructions for coding agents working in the `aicione` repository.

## Project Vision & Scope

`AI.ciOne` is an intelligent system for analytical reasoning, symbolic equation formulation, and solving of analog electronic circuits.

### Pipeline Relationship with CEML
- `ceml-lang` (markup repository): defines the declarative `.ci` grammar, AST models (`Circuit`, `Node`, `Component`, `Specs`), and validation rules.
- `aicione` (this repository): ingests validated `ceml.models.Circuit` structures, decomposes circuits by regime (DC bias vs AC small-signal), formulates analytical network equations (KCL, KVL, transistor small-signal equivalent models), and solves for unknown variables symbolically and deterministically.

## Language Convention

Everything in this repository must be written in **English**:
- All source code, module names, functions, classes, and variables.
- All docstrings and code comments.
- All documentation, ADRs in `decisions/`, and READMEs.
- All commit messages following Conventional Commits (`feat(...)`, `fix(...)`, etc.).

## Architectural Decision Records (ADRs)

All significant technical and architectural decisions must be recorded as ADRs under `decisions/` in English, sequentially numbered, and linked in `decisions/README.md`.

## Git Conventions

- Remote uses SSH (`git@github.com:aicione/aicione.git`), not HTTPS.
- Never commit unless explicitly requested by the user.
- Commit messages follow Conventional Commits format with a clear title under ~70 characters and bullet-point body.
- Always provide suggested commit messages in English at the end of every completed task or work session, including both the title and body, so the user can review and commit immediately.
