# Req-to-Code POC V2

FastAPI-based requirement-to-code pipeline with knowledge-graph analysis, semantic retrieval, SQLite-backed change tracking, and a human-in-the-loop review flow.

## Overview

The system analyzes a target codebase under `data/codebase/`, parses requirements from `data/reqs.json`, retrieves relevant context, generates candidate code, reviews it, calculates impact and confidence, stores every attempt in SQLite, and waits for a human decision before applying code changes.

Core capabilities:

- Knowledge graph-based code analysis
- Semantic retrieval over indexed code chunks
- Generator and reviewer agent loop
- SQLite persistence for changes, attempts, feedback, and graph snapshots
- HITL approval and rejection flow
- Visual dashboard, dedicated review workspace, and visual analysis page

## Current UI

Routes served by FastAPI:

- `/`
  Dashboard overview
- `/review`
  Dedicated HITL review page for approve/reject decisions
- `/analysis`
  Visual knowledge graph and analysis page

Static files:

- `static/index.html`
- `static/review.html`
- `static/analysis.html`

## API Endpoints

### `POST /analyze-codebase`

Runs analysis for a target code directory.

Request:

```json
{
  "path": "data/codebase"
}
```

Response shape:

```json
{
  "overall_summary": "Knowledge graph built for 13 file(s), 4 class(es), 25 function(s), and 9 import(s).",
  "files": [],
  "semantic_ast": [],
  "knowledge_graph": {
    "nodes": [],
    "edges": []
  },
  "graph_stats": {
    "files": 13,
    "classes": 4,
    "functions": 25,
    "imports": 9
  }
}
```

### `POST /run-pipeline`

Runs the generation pipeline over `data/reqs.json`.

Response shape:

```json
{
  "status": "success",
  "logs": [
    "[10%] Loading multi-language codebase...",
    "[20%] Building semantic AST + knowledge graph..."
  ],
  "time_seconds": 1.23
}
```

### `GET /changes`

Returns persisted changes, attempts, reviews, and impact analysis for the UI.

### `POST /changes/{id}/accept`

Applies the generated code to disk if the change passes safety checks and risk threshold checks.

### `POST /changes/{id}/reject`

Stores human feedback and marks the current change rejected.

Request:

```json
{
  "comment": "Add stronger validation for this edge case."
}
```

## Execution Flow

The main runtime flow is implemented in [`services/pipeline.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/pipeline.py).

Pipeline stages:

1. Load codebase from `data/codebase/`
2. Build semantic AST and knowledge graph
3. Save graph snapshot to SQLite
4. Index code chunks into the semantic vector store
5. Parse requirements from `data/reqs.json`
6. Check LLM runtime readiness
7. Retrieve relevant context for each requirement
8. Generate candidate output
9. Review and validate generated code
10. Compute diff, impact analysis, and confidence
11. Persist attempt and mark it `PENDING`
12. Wait for human review

## Analysis and Knowledge Graph

### Where analysis is generated

Analysis is generated in `run_analysis()` in [`services/pipeline.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/pipeline.py).

It returns:

- `overall_summary`
- `semantic_ast`
- `knowledge_graph`
- `graph_stats`

### Where the text summary appears

The text summary shown to the user comes from `overall_summary`.

It is displayed in:

- dashboard `/`
  `Knowledge graph summary`
- analysis page `/analysis`
  `What the analysis found`

### What the graph contains

Graph building lives in [`services/knowledge_graph.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/knowledge_graph.py).

Nodes include:

- files
- classes
- functions
- variables
- imports

Edges include:

- `DEFINES`
- `CALLS`
- `IMPORTS`
- `INHERITS`

Example:

```json
{
  "nodes": [
    {
      "id": "func:data/codebase/services/order_service.py::create_order",
      "type": "function"
    }
  ],
  "edges": [
    {
      "from": "file:data/codebase/services/order_service.py",
      "to": "func:data/codebase/services/order_service.py::create_order",
      "type": "DEFINES"
    }
  ]
}
```

### Multi-language parsing

Language parsing is handled by [`services/language_engine.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/language_engine.py).

Currently supported:

- Python
- JavaScript-style syntax via regex extraction
- Go-style syntax via regex extraction
- Java-style syntax via regex extraction

Python uses `ast`; the other languages currently use lightweight parsing heuristics.

## Semantic Retrieval

Semantic retrieval is implemented in [`services/vector_store.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/vector_store.py).

Current behavior:

- chunks file-level and symbol-level code
- creates deterministic local embeddings
- ranks by cosine similarity
- boosts matches when the file hint matches the chunk path

This is an in-repo semantic store implementation, not FAISS or Chroma.

## Generator and Reviewer

### Generator

Implemented in [`agents/generator_agent.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/agents/generator_agent.py).

Generator prompt inputs:

- requirement payload
- retrieved semantic context
- semantic AST summary
- knowledge graph summary
- learning context
- previous rejection history
- reviewer feedback

### Reviewer

Implemented in [`agents/reviewer_agent.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/agents/reviewer_agent.py).

Reviewer output shape:

```json
{
  "issues": [],
  "suggestions": [],
  "dependency_violations": [],
  "security_findings": [],
  "confidence": 0.82,
  "verdict": "PASS"
}
```

Reviewer checks focus on:

- logic correctness
- style issues
- dependency violations
- security concerns

## LLM Runtime Behavior

LLM integration is handled by [`utils/llm.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/utils/llm.py).

Runtime expectations:

- `GEMINI_API_KEY` must be set
- outbound HTTPS access to the Gemini REST API must be available

Mock mode is only enabled when:

```bash
export ALLOW_MOCK_LLM=true
```

Without either a working Gemini setup or explicit mock mode, the pipeline stops early and returns an error instead of silently falling back.

Runtime status helper:

- `llm_status()`

## Confidence Calculation

Confidence is calculated in `_build_confidence()` in [`services/pipeline.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/pipeline.py).

Inputs:

- reviewer confidence
- number of review issues
- dependency violations
- security findings
- syntax validation result
- impact risk score
- whether feedback-aware regeneration was used

The final value is clamped between `0.0` and `1.0`.

## Impact Analysis

Impact analysis is implemented in [`services/impact_analyzer.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/impact_analyzer.py).

### Inputs

- target file path
- unified diff text
- knowledge graph
- optional protected file list

### Outputs

- `impacted_files`
- `impacted_functions`
- `dependency_chain`
- `risk_score`
- `summary`

### How risk is currently calculated

The current risk score is a heuristic:

```python
risk_score = min(
    1.0,
    0.2
    + (0.1 * len(impacted_files))
    + (0.07 * len(impacted_functions))
    + (0.12 if any(item in file_path for item in protected_files) else 0.0),
)
```

Interpretation:

- base risk starts at `0.2`
- more impacted files increase risk
- more impacted functions increase risk
- touching a protected file can further increase risk
- score is capped at `1.0`

### Apply blocking

`apply_diff()` in [`services/change_manager.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/change_manager.py) blocks apply when:

- `risk_score > IMPACT_RISK_THRESHOLD`

Default:

```bash
IMPACT_RISK_THRESHOLD=0.85
```

## Human-in-the-Loop Flow

The HITL workflow is split across the dashboard and dedicated review UI.

### Dashboard `/`

Purpose:

- high-level system view
- queue summary
- links into detailed review

### Review page `/review`

Purpose:

- inspect a single change
- compare before/after code
- inspect unified diff
- review impact analysis
- review attempt history
- approve or reject with human feedback

### Accept flow

1. UI calls `POST /changes/{id}/accept`
2. `apply_diff()` checks:
   - risk threshold
   - protected file restrictions
   - backup creation
3. generated code is written to disk
4. change status is updated to `ACCEPTED`

### Reject flow

1. UI calls `POST /changes/{id}/reject`
2. feedback is stored in SQLite
3. learning memory stores rejection context
4. later pipeline runs can use that feedback for regeneration

## Database

Database schema is initialized in [`models/db.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/models/db.py).

Current DB path:

```python
DB_PATH = "data/changes.db"
```

### Tables

- `changes`
- `attempts`
- `feedback`
- `impact_analysis`
- `graph_snapshots`
- `audit_log`

### Initialization

Initialization is triggered on FastAPI startup in [`main.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/main.py):

```python
@app.on_event("startup")
def startup():
    init_db()
```

### Database responsibilities

`changes`

- latest persisted state of a requirement/change

`attempts`

- per-attempt generated code, review, validation, impact, and confidence

`feedback`

- human rejection and review comments

`impact_analysis`

- saved impact-analysis results per attempt

`graph_snapshots`

- saved graph JSON for analysis runs

`audit_log`

- change and lifecycle events

## Learning Memory

Learning memory is stored in `data/memory.json` and managed by [`services/learning_engine.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/learning_engine.py).

Tracked keys:

- `successful_patterns`
- `rejected_attempts`
- `reviewer_feedback`
- `attempt_log`
- `common_issues`

The loader normalizes older memory files and backfills missing keys so legacy `memory.json` files do not crash the pipeline.

## Target Codebase and Requirements

### Target codebase

The current sample codebase lives in:

- `data/codebase/`

It is a small BookBarn-style Python backend with:

- `app.py`
- `models/`
- `repositories/`
- `services/`
- `utils/`

### Requirements

Requirements are stored in:

- `data/reqs.json`

Supported requirement types:

- `FIT`
- `PARTIAL`
- `GAP`

## Running the Project

### Install dependencies

```bash
pip install -r requirements.txt
```

### Optional Gemini dependency

If you want real generation and review:

```bash
export GEMINI_API_KEY="your-gemini-key"
```

### Optional mock mode

```bash
export ALLOW_MOCK_LLM=true
```

### Start the server

```bash
uvicorn main:app --reload --port 5034
```

## Recommended URLs

- `http://127.0.0.1:5034/`
- `http://127.0.0.1:5034/review`
- `http://127.0.0.1:5034/analysis`

## Example Commands

Analyze:

```bash
curl -X POST http://127.0.0.1:5034/analyze-codebase \
  -H "Content-Type: application/json" \
  -d '{"path": "data/codebase"}'
```

Run pipeline:

```bash
curl -X POST http://127.0.0.1:5034/run-pipeline
```

List changes:

```bash
curl -X GET http://127.0.0.1:5034/changes
```

Reject a change:

```bash
curl -X POST http://127.0.0.1:5034/changes/7/reject \
  -H "Content-Type: application/json" \
  -d '{"comment": "Handle invalid input and return a clearer error."}'
```

Accept a change:

```bash
curl -X POST http://127.0.0.1:5034/changes/7/accept
```

## Known Constraints

- `DB_PATH` is still a relative path
- non-Python language support is lightweight
- semantic retrieval uses a local deterministic embedding strategy
- impact risk is heuristic, not learned
- the analysis text summary is currently concise and stats-based rather than a long architecture narrative

## Key Files

- [`main.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/main.py)
- [`api/routes.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/api/routes.py)
- [`models/db.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/models/db.py)
- [`services/pipeline.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/pipeline.py)
- [`services/change_manager.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/change_manager.py)
- [`services/knowledge_graph.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/knowledge_graph.py)
- [`services/vector_store.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/vector_store.py)
- [`services/impact_analyzer.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/impact_analyzer.py)
- [`services/learning_engine.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/services/learning_engine.py)
- [`utils/llm.py`](/Users/chandrabalaji/pycharmPython/req-to-code-v2/utils/llm.py)
