![Status](https://img.shields.io/badge/status-early%20development-orange)
![Local-first](https://img.shields.io/badge/runtime-local--first-lightgrey)
![Deterministic](https://img.shields.io/badge/design-deterministic-critical)

> ⚠ Early Development
>
> docflow is currently in early development.
> Architecture and interfaces may change.

## Project description

docflow is a deterministic document pipeline for local archives.

It transforms raw documents (PDF, scans, OCR text) into structured, auditable records using a reproducible pipeline:

```
OCR → Heuristics → LLM Suggest → Human Approval → Apply
```

The system is designed for forensic traceability, reproducibility, and controlled automation, not for autonomous AI classification.

docflow runs locally, produces append-only audit logs,
and requires explicit human approval before archive modifications.

## Pipeline diagramm
```
              +----------------+
              |   Documents    |
              +--------+-------+
                       |
                       v
                +------+------+
                |     OCR     |
                +------+------+
                       |
                       v
                +------+------+
                |  Heuristics |
                +------+------+
                       |
                       v
                +------+------+
                | LLM Suggest |
                +------+------+
                       |
                       v
                +------+------+
                |   Approval  |
                +------+------+
                       |
                       v
                +------+------+
                |    Apply    |
                +-------------+
```
Each stage produces structured artifacts that can be inspected or audited.

---

## Key Features

- Deterministic document classification pipeline
- Optional LLM enrichment with validation
- Human approval gates before archive modifications
- Cryptographic traceability (file hashes & settings fingerprints)
- Append-only audit logs for all operations
- Local-first architecture (no cloud dependency)
---

## Motivation

Most document management tools prioritize convenience over traceability.

Files are automatically moved without clear reasoning,
AI classifiers produce opaque results,
and archives slowly become inconsistent over time.

docflow explores a different approach:

a deterministic processing pipeline where every decision is
inspectable, reproducible, and bound to explicit configuration.

Instead of autonomous automation, the system emphasizes:

- deterministic heuristics
- optional AI assistance
- explicit configuration
- human approval gates
- complete audit logging

Automation is always subordinate to auditability.

---

## Core Principles

docflow follows several architectural rules.

### Determinism first

Heuristics produce the primary classification.

LLM suggestions are only **optional enrichment** and never override deterministic decisions.


### Closed-World configuration

Valid areas and document types are defined explicitly in YAML settings.

The system never guesses unknown categories.


### Human approval before changes

File moves or archive modifications require explicit approval unless forced.

This prevents accidental archive corruption.


### Reproducibility

Each suggestion is bound to a `settings_sha256` fingerprint.

Suggestions generated with different settings cannot be applied accidentally.


### Complete audit trail

Every action is logged in append-only JSONL audit logs.

Logs include:

* file hashes
* applied settings hash
* decision state
* timestamps

---

## Installation

docflow is currently under active development.

Installation instructions will be added once the CLI stabilizes.

---

## Development Setup
```bash
git clone https://github.com/AURENYX-lab/docflow
cd docflow
pip install -e .
pytest
```

---

## Example Usage

Typical workflow:

### 1. Extract text

```
docflow ocr inbox/
```

Runs OCR on documents inside `inbox/`.

Outputs extracted text files and OCR metadata.


### 2. Generate suggestions

```
docflow suggest inbox/
```

Runs heuristics and optional LLM suggestions.

Produces structured suggestion files.


### 3. Review suggestions

Human inspection of generated suggestions.

Invalid or uncertain results can be corrected manually.


### 4. Apply archive changes

```
docflow apply suggestions/
```

Moves files to archive locations, generates Obsidian notes, and writes audit logs.

---

## Architecture Overview

docflow is structured as a deterministic pipeline.

Key design decisions:

* **Pydantic models** define runtime truth
* **JSON schemas** are derived from models
* **settings_sha256** binds suggestions to configuration
* **Heuristics dominate classification**
* **LLM output is validated, never trusted blindly**

See `ARCHITECTURE.md` for full details.

---

## Configuration

docflow uses YAML configuration files validated by Pydantic.

Example:

```
settings/
 ├── categories.yaml
 ├── doctypes.yaml
 └── pipeline.yaml
```

The configuration defines:

* valid archive areas
* document types
* heuristic rules
* pipeline behavior

Configuration changes change the `settings_sha256` fingerprint.

This guarantees that suggestions are always linked to the exact configuration used to generate them.

---

## Project Status

docflow is currently in **early development**.

The focus is on:

* deterministic pipeline design
* strict contracts
* reproducible processing
* audit-safe file operations

Core architecture is still evolving.
