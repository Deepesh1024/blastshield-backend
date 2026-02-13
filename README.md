# 🛡️ BlastShield Backend — Production-Grade Deployment Safety Engine

> **v2.0.0** — Deterministic-first, AI-assisted code risk analysis API.

BlastShield scans entire codebases and PR diffs for deployment-breaking risks — security vulnerabilities, concurrency bugs, unsafe I/O, missing error boundaries, and more. It returns **structured, actionable results** with severity ratings, explainable risk scores, evidence chains, and auto-generated patches.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [API Endpoints](#api-endpoints)
  - [POST /scan — Full Project Scan](#post-scan--full-project-scan)
  - [POST /pr-scan — PR Diff Scan](#post-pr-scan--pr-diff-scan)
  - [GET /scan/{scan_id}/status — Poll Background Scan](#get-scanscan_idstatus--poll-background-scan)
  - [GET /health — Health Check](#get-health--health-check)
- [Request & Response Schemas](#request--response-schemas)
  - [ScanRequest](#scanrequest)
  - [ScanResponse](#scanresponse)
  - [ScanReport](#scanreport)
  - [Issue](#issue)
  - [Patch](#patch)
  - [RiskBreakdown](#riskbreakdown)
  - [ViolationContribution](#violationcontribution)
  - [AuditEntry](#auditentry)
  - [ScanStatusResponse](#scanstatusresponse)
- [Analysis Pipeline (9 Steps)](#analysis-pipeline-9-steps)
- [Layer 1 — Deterministic Core](#layer-1--deterministic-core)
  - [AST Parser](#ast-parser)
  - [Call Graph Builder](#call-graph-builder)
  - [Data Flow Analyzer](#data-flow-analyzer)
  - [Rule Engine (8 Rules)](#rule-engine-8-rules)
  - [Test Harness](#test-harness)
  - [Risk Scorer](#risk-scorer)
- [Layer 2 — AI-Assisted Reasoning](#layer-2--ai-assisted-reasoning)
  - [LLM Gateway](#llm-gateway)
  - [Prompt Builder (Hallucination Prevention)](#prompt-builder-hallucination-prevention)
  - [Response Validator](#response-validator)
  - [Deterministic Fallback](#deterministic-fallback)
- [Layer 3 — Infrastructure](#layer-3--infrastructure)
  - [File Cache (SHA-256)](#file-cache-sha-256)
  - [Background Workers](#background-workers)
  - [Audit Logger](#audit-logger)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Testing](#testing)
- [Legacy Compatibility](#legacy-compatibility)
- [Tech Stack](#tech-stack)

---

## Architecture Overview

BlastShield uses a **3-layer deterministic-first architecture**:

```
┌────────────────────────────────────────────────────────────────────┐
│                    Layer 3 — API & Infrastructure                  │
│   FastAPI endpoints · Background workers · SHA-256 cache · Audit  │
├────────────────────────────────────────────────────────────────────┤
│                    Layer 2 — AI-Assisted Reasoning                 │
│   LLM Gateway (Groq) · Prompt Builder · Response Validator        │
│   · Hallucination prevention · Deterministic fallback             │
├────────────────────────────────────────────────────────────────────┤
│                    Layer 1 — Deterministic Core                    │
│   AST Parser · Call Graph Builder · Data Flow Analyzer            │
│   · Rule Engine (8 rules) · Test Harness · Risk Scorer            │
└────────────────────────────────────────────────────────────────────┘
```

**Key principle**: Layer 1 always runs. Layer 2 (LLM) is only invoked when `risk_score > threshold` or critical/high violations are found. If the LLM fails or returns invalid output, the system falls back gracefully to deterministic-only results. The scan **never fails** due to LLM issues.

---

## API Endpoints

### POST /scan — Full Project Scan

**Primary endpoint for the VS Code extension.** Scans all project files.

- **≤ 10 files** → runs inline, returns full response immediately
- **> 10 files** → queues to background worker, returns `scan_id` for polling

```http
POST /scan
Content-Type: application/json

{
  "files": [
    {
      "path": "/absolute/path/to/file.py",
      "content": "import os\ndef run(cmd):\n    os.system(cmd)\n"
    },
    {
      "path": "/absolute/path/to/other.py",
      "content": "..."
    }
  ]
}
```

**Response** (inline scan — ≤ 10 files):

```json
{
  "message": "scan_complete",
  "scan_id": "a1b2c3d4",
  "report": {
    "issues": [ ... ],
    "riskScore": 72,
    "risk_breakdown": { ... },
    "summary": "Risk score 72/100 based on 5 violations (1 critical, 2 high, 2 medium)...",
    "llm_used": true,
    "deterministic_only": false,
    "audit": { ... }
  }
}
```

**Response** (background scan — > 10 files):

```json
{
  "message": "scan_queued",
  "scan_id": "bg-00042",
  "report": null
}
```

Then poll `GET /scan/bg-00042/status` until `status` is `"complete"`.

---

### POST /pr-scan — PR Diff Scan

**For GitHub Actions integration.** Scans only files changed in a PR. Always runs inline (PRs typically have few changed files).

```http
POST /pr-scan
Content-Type: application/json

{
  "files": [
    {
      "path": "relative/path/to/changed_file.py",
      "content": "..."
    }
  ]
}
```

**Response** — same as `/scan` but with a PR-specific `summary`:

```json
{
  "message": "scan_complete",
  "scan_id": "e5f6a7b8",
  "report": {
    "issues": [ ... ],
    "riskScore": 45,
    "risk_breakdown": { ... },
    "summary": "PR Analysis: BlastShield found 3 issues (0 critical, 1 high) in this PR. Risk score: 45/100.",
    "llm_used": false,
    "deterministic_only": true,
    "audit": { ... }
  }
}
```

---

### GET /scan/{scan_id}/status — Poll Background Scan

Poll the status of a background scan queued by `/scan`.

```http
GET /scan/bg-00042/status
```

```json
{
  "scan_id": "bg-00042",
  "status": "running",
  "progress": 0.5,
  "report": null,
  "error": null
}
```

When complete:

```json
{
  "scan_id": "bg-00042",
  "status": "complete",
  "progress": 1.0,
  "report": { ... },
  "error": null
}
```

**Status values**: `"queued"` | `"running"` | `"complete"` | `"failed"`

---

### GET /health — Health Check

```http
GET /health
```

```json
{
  "status": "ok",
  "model": "moonshotai/kimi-k2-instruct-0905",
  "version": "2.0.0",
  "engine": "deterministic-first"
}
```

---

## Request & Response Schemas

### ScanRequest

| Field       | Type                   | Required | Description                                      |
|-------------|------------------------|----------|--------------------------------------------------|
| `files`     | `FileInput[]`          | Yes*     | List of files to scan                            |
| `scan_mode` | `"full"` \| `"pr"`     | No       | Scan mode (default: `"full"`)                    |
| `combined`  | `string \| null`       | No       | Legacy: single combined code string (deprecated) |

*Either `files` or `combined` must be provided.

### FileInput

| Field     | Type     | Description                        |
|-----------|----------|------------------------------------|
| `path`    | `string` | File path (absolute or relative)   |
| `content` | `string` | Full source code of the file       |

### ScanResponse

| Field      | Type               | Description                                              |
|------------|--------------------|----------------------------------------------------------|
| `message`  | `string`           | `"scan_complete"`, `"scan_queued"`, or `"error"`         |
| `scan_id`  | `string`           | Unique scan identifier                                   |
| `report`   | `ScanReport\|null` | Full report (null when queued or error)                   |

### ScanReport

| Field               | Type                  | Description                                           |
|---------------------|-----------------------|-------------------------------------------------------|
| `issues`            | `Issue[]`             | All detected issues with patches                      |
| `riskScore`         | `int (0–100)`         | Overall risk score                                    |
| `risk_breakdown`    | `RiskBreakdown\|null` | Explainable per-violation risk contribution breakdown  |
| `summary`           | `string`              | Human-readable risk summary                           |
| `llm_used`          | `bool`                | Whether LLM was invoked for this scan                 |
| `deterministic_only`| `bool`                | True if results are purely deterministic (no LLM)     |
| `audit`             | `AuditEntry\|null`    | Audit metadata for this scan                          |

### Issue

| Field         | Type          | Description                                                    |
|---------------|---------------|----------------------------------------------------------------|
| `id`          | `string`      | Unique issue ID (e.g. `"dangerous_eval-1"`)                    |
| `severity`    | `string`      | `"critical"` \| `"high"` \| `"medium"` \| `"low"`             |
| `file`        | `string`      | File path where the issue was found                            |
| `line`        | `int`         | Line number of the issue                                       |
| `rule_id`     | `string`      | Deterministic rule ID that detected this (e.g. `"race_condition"`) |
| `issue`       | `string`      | Short issue title                                              |
| `explanation` | `string`      | Detailed explanation (LLM-enhanced if available)               |
| `risk`        | `string`      | Production risk description                                    |
| `evidence`    | `string[]`    | Deterministic evidence chain (AST paths, variable traces)      |
| `patches`     | `Patch[]`     | Auto-generated code patches                                    |
| `testImpact`  | `string[]`    | Likely impacted test files/functions                           |

### Patch

| Field        | Type     | Description                        |
|--------------|----------|------------------------------------|
| `file`       | `string` | Target file path                   |
| `start_line` | `int`    | Start line of code to replace      |
| `end_line`   | `int`    | End line of code to replace        |
| `new_code`   | `string` | Replacement code                   |

### RiskBreakdown

| Field                     | Type                       | Description                                    |
|---------------------------|----------------------------|------------------------------------------------|
| `total_score`             | `int (0–100)`              | Final risk score                               |
| `max_possible_score`      | `float`                    | Maximum possible score given the violations    |
| `violation_contributions` | `ViolationContribution[]`  | Per-violation breakdown                        |
| `formula`                 | `string`                   | Human-readable formula used                    |
| `summary`                 | `string`                   | Human-readable risk summary                    |

### ViolationContribution

Each violation's individual contribution to the total risk score:

| Field                   | Type    | Description                                  |
|-------------------------|---------|----------------------------------------------|
| `rule_id`               | `string`| Rule identifier                              |
| `severity`              | `string`| Severity level                               |
| `file`                  | `string`| File path                                    |
| `line`                  | `int`   | Line number                                  |
| `base_weight`           | `int`   | Severity weight (critical=10, high=7, med=4, low=1) |
| `blast_radius_factor`   | `float` | Impact based on call graph depth             |
| `state_mutation_factor` | `float` | Shared mutable state factor                  |
| `test_failure_factor`   | `float` | Test harness failure factor                  |
| `async_boundary_factor` | `float` | Async/sync boundary crossing factor          |
| `total_factor`          | `float` | Combined multiplier                          |
| `weighted_score`        | `float` | Final weighted score for this violation      |

### AuditEntry

| Field               | Type    | Description                            |
|---------------------|---------|----------------------------------------|
| `scan_id`           | `string`| Scan identifier                        |
| `files_scanned`     | `int`   | Number of files processed              |
| `violations_found`  | `int`   | Total violations detected              |
| `risk_score`        | `int`   | Risk score                             |
| `llm_invoked`       | `bool`  | Whether LLM was called                 |
| `llm_tokens_used`   | `int`   | LLM tokens consumed                    |
| `duration_ms`       | `float` | Total scan duration in milliseconds    |
| `deterministic_only`| `bool`  | True if LLM was not used               |

### ScanStatusResponse

| Field      | Type               | Description                                    |
|------------|--------------------|------------------------------------------------|
| `scan_id`  | `string`           | Scan identifier                                |
| `status`   | `string`           | `"queued"` \| `"running"` \| `"complete"` \| `"failed"` |
| `progress` | `float (0.0–1.0)`  | Estimated progress                             |
| `report`   | `ScanReport\|null` | Full report when complete                      |
| `error`    | `string\|null`     | Error message if failed                        |

---

## Analysis Pipeline (9 Steps)

Every scan (both `/scan` and `/pr-scan`) executes this pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Parse AST         │ Python AST extraction per file (cached)  │
│ 2. Build Call Graph   │ Inter-function/inter-module graph        │
│ 3. Data Flow Analysis │ Nullable returns, unguarded input, etc.  │
│ 4. Rule Engine        │ 8 deterministic rules → violations       │
│ 5. Test Harness       │ Edge-case test generation (if enabled)   │
│ 6. Risk Scoring       │ Explainable formula with 4 factors       │
│ 7. LLM Invocation     │ Only if risk > threshold or critical     │
│ 8. Response Validation│ Reject hallucinations, fallback if bad   │
│ 9. Cache Results      │ SHA-256 keyed for incremental scans      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Deterministic Core

### AST Parser

**File**: `app/core/ast_parser.py`

Parses Python source using the built-in `ast` module and extracts:

- **Functions & methods**: name, line range, parameters, return annotation, decorators, is_async
- **Classes**: name, bases, methods, class variables, decorators
- **Imports**: module, names, aliases, from-imports
- **Variable mutations**: module-level assignments, augmented assignments, inferred types
- **Async boundaries**: `async def`, `await`, `async for`, `async with`
- **Exception flows**: try/except handlers, bare excepts, re-raises
- **Function calls**: all calls within each function body, including awaited calls
- **Global access**: reads and writes to module-level names from within functions

Currently supports Python (`.py`). JS/TS returns a parse-error fallback (deferred to a future phase).

### Call Graph Builder

**File**: `app/core/call_graph.py`

Constructs an inter-function/inter-module call graph from parsed ASTs:

- **Nodes**: each function/method → unique ID `"module::function"`
- **Edges**: direct calls, import edges, with `async_boundary_crossing` flag
- **Entry point detection**: identifies `@app.route`, `@router.post/get`, `main()`, etc.
- **Cross-module resolution**: resolves imports to actual function definitions
- **Shared state tracking**: records per-node reads/writes to global variables
- **Blast radius computation**: BFS depth from any node through all reachable callees
- **Subgraph extraction**: extract the subgraph around violation nodes (N-hop expansion)

### Data Flow Analyzer

**File**: `app/core/data_flow.py`

Intra-function data flow analysis detecting:

| Issue Type              | Description                                          |
|-------------------------|------------------------------------------------------|
| `nullable_return`       | Function can implicitly return `None` despite non-None annotation |
| `unguarded_input`       | Parameters passed directly to `eval()`, `exec()`, `os.system()`, `subprocess.run()`, `open()`, etc. without sanitization |
| `cross_module_mutation` | Functions mutating module-level mutable containers (`list`, `dict`, `set`), causing race condition risk |

### Rule Engine (8 Rules)

**File**: `app/core/rule_engine.py`  
**Rules directory**: `app/core/rules/`

All rules are **pure deterministic functions** — no LLM, no network, no randomness.

| Rule ID                        | Severity  | What It Detects                                        |
|--------------------------------|-----------|-------------------------------------------------------|
| `race_condition`               | Critical  | Multiple async functions writing to same shared mutable state |
| `missing_await`                | High      | Async function calls without `await` (silent data loss) |
| `dangerous_eval`               | Critical  | `eval()` / `exec()` with dynamic/unsanitized input     |
| `unsanitized_io`               | High      | User input flowing to file/system operations without validation |
| `shared_mutable_state`         | Medium    | Module-level mutable containers mutated from functions  |
| `missing_exception_boundary`   | Medium    | API entry points with no try/except (raw 500s)          |
| `retry_without_backoff`        | Medium    | Retry loops without exponential backoff                 |
| `blocking_io_in_async`         | High      | Blocking calls (`time.sleep`, `requests.get`, `open()`) inside async functions |

Each violation includes:
- `rule_id`, `severity`, `file`, `line`, `end_line`
- `title`, `description` (human-readable)
- `evidence[]` — deterministic evidence chain (AST paths, variable traces)
- `affected_function` — function where violation occurs
- `graph_node_id` — call graph node ID for blast radius computation

### Test Harness

**File**: `app/core/test_harness.py`  
**Feature flag**: `TEST_HARNESS_ENABLED` (default: `false`)

When enabled, automatically generates and runs edge-case tests:

1. **Generates boundary inputs** based on function signatures:
   - `None`, empty string, very long string (`10,000 chars`)
   - XSS payloads, SQL injection, path traversal strings
   - `0`, `-1`, `2^31` (overflow), `infinity`
   - Empty `list`, `dict`, list of `None`s

2. **Runs each test in an isolated subprocess** with a configurable timeout (default: 5s)

3. **Captures**: runtime failures, uncaught exceptions, timeout (infinite loop detection), return values

### Risk Scorer

**File**: `app/core/risk_scorer.py`

Computes an **explainable risk score** (0–100) from rule violations:

```
Per violation:
  base_weight = severity_weight (critical=10, high=7, medium=4, low=1)
  factors = 1.0
    + 0.3 × (blast_radius / max_graph_depth)
    + 0.2 × (1 if mutates_shared_state)
    + 0.3 × (1 if test_failure_present)
    + 0.2 × (1 if async_boundary_crossing)

  weighted_score = base_weight × factors

Total: risk_score = Σ weighted_scores / max_possible × 100   (capped at 100)
```

Every violation's individual contribution is traced in the `risk_breakdown.violation_contributions` array.

---

## Layer 2 — AI-Assisted Reasoning

### LLM Gateway

**File**: `app/llm/gateway.py`

Wraps the Groq SDK with production-grade reliability:

- **Retry with exponential backoff**: 1s → 2s → 4s (configurable max retries)
- **Async execution**: runs sync Groq SDK in thread pool (`asyncio.to_thread`)
- **Token tracking**: per-scan token budget (`LLM_MAX_TOKENS_PER_SCAN`, default: 4096)
- **JSON extraction**: auto-parses `json` fences from markdown-wrapped responses
- **Configurable model**: via `BLASTSHIELD_MODEL` env var

### Prompt Builder (Hallucination Prevention)

**File**: `app/llm/prompt_builder.py`

The LLM **never receives raw source code**. Instead it gets structured JSON:

1. **Serialized rule violations** (these are FACTS from Layer 1)
2. **Call graph subgraph** (only the affected neighborhood)
3. **Test failure results** (from the test harness)
4. **Risk scoring breakdown**
5. **File path whitelist** (the LLM can only reference these files)

The system prompt enforces:
- ❌ NEVER invent new violations not in the input
- ❌ NEVER reference files not in the whitelist
- ❌ Patches must target ONLY the violation line range (±5 lines)
- ✅ ONLY explain and suggest patches for deterministic findings

### Response Validator

**File**: `app/llm/response_validator.py`

Strict post-validation of LLM output. **Rejects** responses that:

- Reference files not in the input whitelist
- Propose patches outside violation line ranges (±5 lines tolerance)
- Contain hallucinated `rule_id`s not in the deterministic output
- Fail Pydantic schema validation

If validation fails → automatic fallback to deterministic-only output.

### Deterministic Fallback

**File**: `app/llm/fallback.py`

Pre-written explanation templates for each rule. Used when:
- LLM fails or times out
- LLM response fails validation
- Risk score is below LLM threshold

Generates `Issue` objects with:
- Template-based `risk` descriptions
- Template-based patch hints (as `# TODO:` comments)
- Full evidence chains from deterministic analysis

---

## Layer 3 — Infrastructure

### File Cache (SHA-256)

**File**: `app/cache/file_cache.py`

- **Key**: `"filepath:SHA256(content)"` — unchanged files skip re-parsing
- **TTL**: configurable via `CACHE_TTL_SECONDS` (default: 3600s)
- **Stores**: parsed `ModuleAST` + rule violations per file
- **Operations**: get, put, invalidate (per file), clear, stats
- Upgradeable to Redis/SQLite by swapping the storage backend

### Background Workers

**File**: `app/workers/scan_worker.py`

- Scans with > `BACKGROUND_FILE_THRESHOLD` (default: 10) files are queued to background
- Background scans run as `asyncio.create_task()` and store results in-memory
- Extension polls `GET /scan/{scan_id}/status` until `status == "complete"`
- Each scan gets a unique `scan_id` for tracking

### Audit Logger

**File**: `app/audit/logger.py`

- Writes structured JSON-lines to `AUDIT_LOG_PATH` (default: `audit.jsonl`)
- Records every scan: timestamp, scan_id, files scanned, violations found, risk score, LLM invocation details, tokens used, duration

---

## Configuration Reference

All settings via environment variables or `.env` file:

| Variable                    | Type    | Default                                | Description                                         |
|-----------------------------|---------|----------------------------------------|-----------------------------------------------------|
| `GROQ_API_KEY`              | string  | **required**                           | Groq API key for LLM gateway                        |
| `BLASTSHIELD_MODEL`         | string  | `moonshotai/kimi-k2-instruct-0905`     | Model identifier for Groq completions                |
| `LLM_TIMEOUT`               | int     | `30`                                   | LLM request timeout in seconds                      |
| `LLM_MAX_RETRIES`           | int     | `3`                                    | Max LLM retry attempts                               |
| `LLM_TEMPERATURE`           | float   | `0.1`                                  | LLM temperature                                      |
| `LLM_MAX_TOKENS_PER_SCAN`   | int     | `4096`                                 | Token budget cap per scan                             |
| `LLM_RISK_THRESHOLD`        | int     | `30`                                   | Min risk score to invoke LLM (0–100)                  |
| `MAX_FILE_SIZE_BYTES`        | int     | `500000`                               | Max file size to accept                               |
| `BACKGROUND_FILE_THRESHOLD`  | int     | `10`                                   | Files above this → background worker                  |
| `TEST_HARNESS_ENABLED`       | bool    | `false`                                | Enable edge-case test harness                         |
| `TEST_HARNESS_TIMEOUT`       | int     | `5`                                    | Timeout per generated test case (seconds)             |
| `CACHE_TTL_SECONDS`          | int     | `3600`                                 | Cache entry TTL                                       |
| `PORT`                       | int     | `5001`                                 | Server port                                           |
| `HOST`                       | string  | `0.0.0.0`                              | Server bind host                                      |
| `CORS_ORIGINS`               | list    | `["*"]`                                | Allowed CORS origins                                  |
| `AUDIT_LOG_PATH`             | string  | `audit.jsonl`                          | Path to audit log file                                |

---

## Project Structure

```
blastshield-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry point (v2.0.0)
│   ├── config.py                  # pydantic-settings configuration
│   │
│   ├── api/
│   │   ├── dependencies.py        # DI singletons (cache, audit, LLM, worker)
│   │   └── routes/
│   │       ├── health.py          # GET /health
│   │       ├── scan.py            # POST /scan + GET /scan/{id}/status
│   │       └── pr_scan.py         # POST /pr-scan
│   │
│   ├── core/
│   │   ├── ast_parser.py          # Python AST extraction
│   │   ├── call_graph.py          # Inter-function/module call graph
│   │   ├── data_flow.py           # Data flow analysis
│   │   ├── risk_scorer.py         # Explainable risk scoring
│   │   ├── rule_engine.py         # Rule orchestrator (8 rules)
│   │   ├── test_harness.py        # Edge-case test generation & runner
│   │   └── rules/
│   │       ├── race_condition.py
│   │       ├── missing_await.py
│   │       ├── dangerous_eval.py
│   │       ├── unsanitized_io.py
│   │       ├── shared_mutable_state.py
│   │       ├── missing_exception_boundary.py
│   │       ├── retry_without_backoff.py
│   │       └── blocking_io_in_async.py
│   │
│   ├── llm/
│   │   ├── gateway.py             # Groq client with retry/backoff/tokens
│   │   ├── prompt_builder.py      # Structured prompts (no raw code to LLM)
│   │   ├── response_validator.py  # Strict schema + hallucination rejection
│   │   └── fallback.py            # Template-based deterministic fallback
│   │
│   ├── models/
│   │   ├── ast_models.py          # ModuleAST, FunctionDef, ClassDef, etc.
│   │   ├── graph_models.py        # CallGraph, CallGraphNode, CallGraphEdge
│   │   ├── risk_models.py         # RiskBreakdown, ViolationContribution
│   │   ├── rule_models.py         # RuleViolation, RuleResult, Severity
│   │   ├── llm_models.py          # LLMResponse, LLMPromptContext
│   │   └── scan_models.py         # ScanRequest, ScanResponse, Issue, Patch
│   │
│   ├── cache/
│   │   └── file_cache.py          # SHA-256 hash-based incremental cache
│   │
│   ├── audit/
│   │   └── logger.py              # JSON-lines audit trail
│   │
│   └── workers/
│       └── scan_worker.py         # Async pipeline orchestrator (9 steps)
│
├── backend.py                     # Legacy Flask backend (deprecated, kept for reference)
├── tests/
│   ├── conftest.py
│   ├── test_ast_parser.py
│   ├── test_call_graph.py
│   ├── test_response_validator.py
│   ├── test_risk_scorer.py
│   ├── test_rule_engine.py
│   └── test_scan_api.py
│
├── requirements.txt
├── .env                           # Environment variables (not committed)
├── .gitignore
└── audit.jsonl                    # Audit log (generated at runtime)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/)

### Setup

```bash
# Clone the repository
git clone https://github.com/Deepesh1024/blastshield-backend.git
cd blastshield-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # or create manually
# Edit .env:
#   GROQ_API_KEY=your_groq_api_key_here
```

### Run the Server

```bash
# Development (with auto-reload)
uvicorn app.main:app --host 0.0.0.0 --port 5001 --reload

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5001
```

### Test a Scan

```bash
curl -X POST http://localhost:5001/scan \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "/example/app.py",
        "content": "import os\ndef run(cmd):\n    os.system(cmd)\n"
      }
    ]
  }'
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_rule_engine.py -v
pytest tests/test_risk_scorer.py -v
pytest tests/test_ast_parser.py -v
```

Test coverage:
- `test_ast_parser.py` — AST extraction for functions, classes, imports, async, exceptions
- `test_call_graph.py` — Call graph construction and blast radius
- `test_rule_engine.py` — All 8 deterministic rules
- `test_risk_scorer.py` — Risk score computation and factor weighting
- `test_response_validator.py` — LLM response validation and hallucination rejection
- `test_scan_api.py` — End-to-end API endpoint tests

---

## Legacy Compatibility

The v2.0.0 API is **backward-compatible** with the v1 Flask `backend.py`:

| v1 Field       | v2 Field          | Notes                                  |
|----------------|-------------------|----------------------------------------|
| `issues`       | `report.issues`   | Same structure, plus `rule_id`, `evidence`, `line` |
| `riskScore`    | `report.riskScore` | Same field name (preserved for compat) |
| —              | `report.risk_breakdown` | **New**: explainable per-violation breakdown |
| —              | `report.llm_used` | **New**: whether LLM contributed       |
| —              | `report.deterministic_only` | **New**: purity flag          |
| —              | `report.audit`    | **New**: scan metadata                  |
| `combined`     | `request.combined` | **Deprecated**: still accepted          |

The legacy `backend.py` (Flask) is kept in the repo root for reference but is **not used** by the v2 FastAPI application.

---

## Tech Stack

| Layer           | Technology                                         |
|-----------------|-----------------------------------------------------|
| **Framework**   | FastAPI + Uvicorn (async)                           |
| **LLM Provider**| Groq (configurable model)                           |
| **Validation**  | Pydantic v2 + pydantic-settings                    |
| **Testing**     | pytest + pytest-asyncio                              |
| **HTTP Client** | httpx                                                |
| **Production**  | Gunicorn + UvicornWorker                             |
| **Parser**      | Python `ast` module (built-in)                       |
| **Cache**       | In-memory SHA-256 (upgradeable to Redis)             |
| **Audit**       | JSON-lines file                                      |

---

## License

MIT

---

*Built with ☢️ by BlastCode — making deployments safer, one scan at a time.*
