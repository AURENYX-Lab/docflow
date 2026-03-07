## System Overview

docflow implements a deterministic document processing pipeline designed for local archives.

The system separates:

- deterministic classification
    
- optional AI enrichment
    
- human approval
    
- file system changes
    

This separation ensures traceability and safe automation.

---

## Component Overview
```
             +------------------+
             |   CLI Interface  |
             +---------+--------+
                       |
                       v
                +------+------+
                |   Pipeline   |
                +------+------+
                       |
     +--------+--------+--------+--------+
     v        v        v        v
    OCR   Heuristics  LLM   Verification
                                   |
                                   v
                            Approval Gate
                                   |
                                   v
                                 Apply
                                   |
                                   v
                              Audit Log
```
---

## Pipeline Design

The pipeline consists of several independent stages.

### OCR

Responsible for extracting text from PDFs and scans.

Outputs:

- extracted text
    
- OCR metadata
    

---

### Heuristics

Primary classification stage.

Heuristics analyze:

- keywords
    
- document structure
    
- known identifiers
    
- date patterns
    

Outputs structured metadata including:

- doc_type
    
- likely_area
    
- extracted fields
    

---

### LLM Suggestion

Optional enrichment stage.

The LLM may suggest:

- improved titles
    
- tags
    
- additional metadata
    

LLM suggestions cannot override heuristic decisions.

---

### Suggest Verification

All suggestions pass through strict validation.

Validation includes:

- closed-world ID checks
    
- safe filename validation
    
- year range checks
    
- schema validation
    

Invalid suggestions are marked but not applied.

---

### Approval Gate

Before archive changes occur, suggestions must be approved.

Approval can be provided via:

- suggestion JSON flag
    
- sidecar approval file
    

---

### Apply

Final stage performing file operations.

Responsibilities:

- file move or copy
    
- metadata generation
    
- Obsidian note creation
    
- audit logging
    

---

## Settings System

docflow uses YAML configuration validated through Pydantic models.

Settings define the allowed classification space.

Closed world means:

```
area ∈ categories.yaml
doc_type ∈ doctypes.yaml
```

No unknown categories are allowed.

---

## Reproducibility

Each run is tied to a configuration fingerprint.

```
settings_sha256
```

Suggestions contain this fingerprint.

Apply will refuse suggestions generated under different settings.

---

## Determinism

Determinism is a core requirement.

The system avoids:

- random decisions
    
- implicit defaults
    
- filesystem guessing
    

Given identical input and configuration, the system must produce identical outputs.

---

## Audit Logging

All state-changing actions produce audit events.

Events include:

- file hash
    
- source path
    
- destination path
    
- applied settings hash
    
- timestamp
    

Logs are stored as append-only JSONL files.
