# Req-to-Code

Req-to-Code is a FastAPI-based developer tool that analyzes a codebase, builds code intelligence artifacts, generates implementation attempts from requirements, and routes those attempts through a human-in-the-loop review workflow.

The application includes:

- a dashboard for codebase selection, requirements entry, analysis, and pipeline execution
- an architecture page for Knowledge Graph and Semantic AST exploration
- a dedicated HITL review page with pending and reviewed history views
- SQLite-backed persistence for attempts, feedback, requirements snapshots, and graph snapshots

## What the system does

At a high level, Req-to-Code follows this flow:

1. Select a codebase from a local folder or a GitHub repository.
2. Analyze the codebase to build:
   - a Semantic AST
   - a Knowledge Graph
   - module summaries
   - a project-level codebase overview
3. Enter requirements as either:
   - a normal form-based list
   - raw JSON / text input
4. Save requirements to the database for the selected codebase.
5. Run the generation pipeline.
6. Review generated code in the HITL workspace.
7. Accept or reject changes.
8. Inspect reviewed history later from the same review page.

## Core features

- Local folder selection using the browser's native folder picker
- GitHub repository cloning into a persistent local cache outside this repo
- Codebase-aware reset behavior when the active repo changes
- Semantic AST generation
- Knowledge Graph generation
- Module-level LLM summaries
- Requirements entry as form or JSON/text
- Requirements persistence in SQLite
- Retrieval-augmented code generation
- Reviewer agent with confidence, issues, dependency findings, and security findings
- Impact analysis and risk scoring
- HITL approval/rejection flow
- Reviewed history for accepted and rejected items

## UI routes

- `/`
  Main dashboard
- `/analysis`
  Architecture explorer for Knowledge Graph and Semantic AST
- `/review`
  Human-in-the-loop review workspace with pending and reviewed tabs

## How codebase selection works

Req-to-Code supports two codebase sources.

### 1. Local folder

The dashboard uses a native folder picker:

- HTML folder input with `webkitdirectory`
- browser-selected folder is uploaded to the backend
- the backend stages it in a temp area for processing

### 2. GitHub repository

The dashboard accepts:

- repository URL
- branch

The backend then:

- clones the repository into a persistent local cache
- updates the cached clone on future runs
- falls back to the remote default branch if the requested branch does not exist

By default, persistent GitHub clones are stored under:

`C:\Users\<user>\AppData\Local\ReqToCode\github-repos\`

This path can be changed with:

`REQ_TO_CODE_REPO_ROOT`

## Generated analysis artifacts

Every analysis writes artifacts into the selected codebase under:

`.req-to-code/`

Artifacts include:

- `knowledge_graph.json`
- `semantic_ast.json`
- `analysis_summary.json`

These are written for both:

- explicit analysis runs
- pipeline runs

## Requirements input

Requirements can be entered in two modes from the dashboard.

### Form mode

Each requirement can include:

- ID
- Type (`FIT`, `PARTIAL`, `GAP`)
- Description
- File hint

### JSON mode

The editor accepts:

- JSON arrays
- grouped JSON objects with `FIT`, `PARTIAL`, and `GAP`
- plain text formats already supported by the parser

Examples:

```json
[
  {
    "id": "REQ-101",
    "type": "PARTIAL",
    "description": "Add search support to the API",
    "file_hint": "app.py"
  }
]
```

```text
PARTIAL: Add search support to the API
```

```text
GAP | Create audit logging service | services/audit.py
```

### Saving requirements

The dashboard includes a `Save To DB` action.

Saved requirement snapshots are stored in SQLite and keyed to the active codebase source, so when you come back to the same repo the dashboard loads the saved requirements instead of falling back to sample data.

## Pipeline stages

The backend pipeline lives in `services/pipeline.py`.

Main stages:

1. Load codebase
2. Build Semantic AST and Knowledge Graph
3. Persist graph snapshot
4. Write `.req-to-code` artifacts
5. Index semantic retrieval chunks
6. Parse requirements
7. Check LLM runtime
8. Retrieve contextual code snippets
9. Generate candidate code
10. Validate generated output
11. Review generated output
12. Compute diff, impact, and confidence
13. Save the attempt for HITL review

## Requirement types

### FIT

Analysis-only requirement.

Used when the system should inspect or explain existing code behavior without generating a code modification.

### PARTIAL

Modify an existing file or implementation.

### GAP

Create a new implementation where the current codebase does not cover the requested behavior.

## HITL review flow

Generated attempts are stored in SQLite and surfaced in `/review`.

### Pending tab

Shows items waiting for a decision.

Users can:

- view generated code
- view diff
- approve and apply
- reject with feedback

### Reviewed tab

Shows items that were already reviewed.

Users can revisit:

- accepted items
- rejected items
- past generated code
- past diffs
- rejection feedback

## Codebase-change reset behavior

When the active codebase changes, Req-to-Code clears codebase-dependent state to avoid mixing data between repositories.

Reset behavior includes:

- clearing review attempts from SQLite
- clearing feedback history tied to the previous codebase
- clearing graph snapshots
- clearing cached file summaries
- removing generated `.req-to-code` artifacts
- removing `.backups`
- removing staged temp uploads when applicable

This behavior is coordinated through:

- `services/change_manager.py`
- `POST /codebase/change`

## Persistence

### SQLite database

Database path:

`data/changes.db`

Initialized in:

- `models/db.py`
- FastAPI startup in `main.py`

Current tables include:

- `changes`
- `attempts`
- `feedback`
- `impact_analysis`
- `graph_snapshots`
- `file_summaries`
- `audit_log`
- `saved_requirements`

### Runtime state

The active codebase source is tracked in:

`data/runtime_state.json`

### Learning memory

Learning history is stored in:

`data/memory.json`

## API overview

### `POST /codebase/upload`

Stages a locally selected folder for analysis.

### `POST /codebase/change`

Marks the active codebase and clears codebase-dependent state if the repo changed.

### `POST /requirements/save`

Saves the current requirement snapshot into SQLite.

### `GET /requirements/load`

Loads the saved requirement snapshot for a given codebase source key.

### `POST /analyze-codebase`

Runs codebase analysis and returns:

- `overall_summary`
- `module_summaries`
- `semantic_ast`
- `knowledge_graph`
- `graph_stats`
- `analysis_artifact_dir`

### `POST /run-pipeline`

Runs the code-generation pipeline and returns:

- pipeline status
- pipeline logs
- elapsed time
- artifact directory

### `GET /changes`

Returns reviewable and reviewed change records for the UI.

### `POST /changes/{id}/accept`

Applies the generated code if the safety and impact checks pass.

### `POST /changes/{id}/reject`

Stores human feedback and marks the item rejected.

## LLM runtime

LLM integration is implemented in `utils/llm.py` using the Gemini REST API.

Environment variables:

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (optional)
- `GEMINI_API_BASE` (optional)
- `GEMINI_TIMEOUT_SECONDS` (optional, default `180`)
- `ALLOW_MOCK_LLM` (optional)

If `GEMINI_API_KEY` is not configured and mock mode is not enabled, generation and summary steps will stop with an explicit error.

## Running the project

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure Gemini

Create a `.env` file in the repo root or export environment variables:

```env
GEMINI_API_KEY=your_api_key_here
```

Optional:

```env
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=180
ALLOW_MOCK_LLM=false
```

### Start the server

Recommended:

```bash
uvicorn main:app --reload --port 5035
```

Or:

```bash
python main.py
```

### Open the UI

- [http://127.0.0.1:5035/](http://127.0.0.1:5035/)
- [http://127.0.0.1:5035/analysis](http://127.0.0.1:5035/analysis)
- [http://127.0.0.1:5035/review](http://127.0.0.1:5035/review)

## Example requests

### Analyze a local codebase

```bash
curl -X POST http://127.0.0.1:5035/analyze-codebase ^
  -H "Content-Type: application/json" ^
  -d "{\"codebase_source\":{\"type\":\"local\",\"path\":\"C:\\\\path\\\\to\\\\repo\"}}"
```

### Analyze a GitHub repository

```bash
curl -X POST http://127.0.0.1:5035/analyze-codebase ^
  -H "Content-Type: application/json" ^
  -d "{\"codebase_source\":{\"type\":\"github\",\"repo_url\":\"https://github.com/pallets/itsdangerous\",\"branch\":\"main\"}}"
```

### Run the pipeline

```bash
curl -X POST http://127.0.0.1:5035/run-pipeline ^
  -H "Content-Type: application/json" ^
  -d "{\"requirements_text\":\"PARTIAL: Add structured logging\",\"codebase_source\":{\"type\":\"local\",\"path\":\"C:\\\\path\\\\to\\\\repo\"}}"
```

### Save requirements

```bash
curl -X POST http://127.0.0.1:5035/requirements/save ^
  -H "Content-Type: application/json" ^
  -d "{\"raw_text\":\"PARTIAL: Add structured logging\",\"mode\":\"form\",\"source_key\":\"local:C:\\\\path\\\\to\\\\repo\"}"
```

## Project structure

```text
.
├── agents/              # Generator and reviewer agents
├── api/                 # FastAPI routes
├── data/                # SQLite DB, runtime state, memory, sample assets
├── models/              # DB initialization
├── services/            # Pipeline, parsing, analysis, storage, impact, reset logic
├── static/              # Dashboard, review page, architecture page
├── ui/                  # UI-facing presentation helpers
├── utils/               # Gemini wrapper and shared utilities
├── main.py              # FastAPI entry point
└── README.md
```

## Important implementation files

- `main.py`
- `api/routes.py`
- `models/db.py`
- `services/pipeline.py`
- `services/change_manager.py`
- `services/requirements_store.py`
- `services/knowledge_graph.py`
- `services/ast_builder.py`
- `services/parser.py`
- `services/vector_store.py`
- `services/impact_analyzer.py`
- `services/file_summary_service.py`
- `utils/llm.py`
- `static/index.html`
- `static/review.html`
- `static/analysis.html`

## Current limitations

- Non-Python language support is heuristic and lighter than the Python parser.
- The vector store is an in-memory deterministic implementation, not an external embedding database.
- The review pipeline is single-app and SQLite-backed, so it is best suited for local or small-team use.
- Codebase-change reset is aggressive by design and clears previous codebase-dependent history.
- Some very large repositories may still produce large architecture payloads or slow LLM-backed summaries.

## Summary

Req-to-Code is best thought of as an interactive requirement-to-implementation workbench:

- analyze the repo
- understand its architecture
- save requirements
- generate implementation attempts
- review them in HITL
- revisit reviewed decisions later

It is designed for local-first experimentation, developer-assisted code generation, and traceable review rather than blind code application.
