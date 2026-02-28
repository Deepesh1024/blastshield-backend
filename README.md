# BlastShield 🛡️

**AI-powered Python code scanner** — detects infinite loop risks using tree-sitter AST analysis and generates explanations + patches via AWS Bedrock (Claude 3.5 Sonnet).

Built for the **AWS AI for Bharat Hackathon** (Round 2).

## Architecture

```
POST /scan  →  tree-sitter parse  →  infinite loop detection  →  risk score
                                                                      ↓
                                                              AWS Bedrock Claude
                                                                      ↓
                                                          explanation + patch
                                                                      ↓
                                                              JSON response
```

## Directory Structure

```
blastshield-backend/
├── app/
│   ├── main.py                  # FastAPI app (/scan + /health)
│   ├── ai/
│   │   ├── bedrock.py            # Bedrock client (bearer token + IAM)
│   │   ├── explainer.py          # AI risk explanation (Claude 3.5 Sonnet)
│   │   └── patcher.py            # AI patch generation (guaranteed non-empty)
│   ├── api/routes/
│   │   └── scan.py               # POST /scan endpoint
│   └── core/
│       ├── parser.py              # tree-sitter Python parser
│       ├── scorer.py              # Risk score calculator
│       └── rules/
│           └── infinite_loop.py   # Infinite loop detection
├── .github/workflows/
│   └── pr-scan.yml               # GitHub Actions PR scanner
├── handler.py                    # Mangum Lambda wrapper
├── serverless.yml                # Serverless Framework config
├── requirements.txt
└── .env.example
```

## Local Development

### Prerequisites

- Python 3.11+
- AWS credentials with `bedrock:InvokeModel` permission

### Setup

```bash
cd blastshield-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your AWS credentials or Bedrock bearer token
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

## API Reference

**Base URL (Local):** `http://localhost:8000`  
**Base URL (Live):** `https://<api-id>.execute-api.us-east-1.amazonaws.com`

### `GET /health`

```bash
curl <BASE_URL>/health
# → {"status": "ok"}
```

### `POST /scan`

**Request:**
```bash
curl -X POST <BASE_URL>/scan \
  -H "Content-Type: application/json" \
  -d '{
    "code": "import time\n\ndef worker():\n    while True:\n        time.sleep(1)\n        print(\"working...\")\n\nworker()"
  }'
```

**Response (risk detected):**
```json
{
  "risk_score": 50,
  "risks": [
    {
      "line_start": 4,
      "line_end": 6,
      "evidence": "`while True` loop without break/return/raise — will run indefinitely and exhaust CPU"
    }
  ],
  "explanation": "This code contains a `while True` loop that runs forever without any exit condition. In production, this will pin one CPU core at 100%, causing health-check failures and eventual cascading timeouts across dependent services.",
  "suggested_patch": "--- original\n+++ fixed\n@@ -4,3 +4,7 @@\n+counter = 0\n while True:\n+    if counter >= 1000:\n+        break\n     ...\n+    counter += 1"
}
```

**Response (clean code):**
```json
{
  "risk_score": 0,
  "risks": [],
  "explanation": "No infinite loop risks detected. Code looks safe.",
  "suggested_patch": ""
}
```

> **Note:** `suggested_patch` is **always non-empty** when `risk_score > 0`. If Bedrock is unavailable, a deterministic static patch is generated with a safety counter + break.

## Test Results

Passed on **5 curated test cases**:

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | Redis task processor — `while True` polling | Detected | ✅ risk_score: 50, non-empty patch |
| 2 | Graceful shutdown — `while True` + `break` | Clean | ✅ risk_score: 0 |
| 3 | IoT sensor — `itertools.count()` | Detected | ✅ risk_score: 50, non-empty patch |
| 4 | FastAPI CRUD app — no loops | Clean | ✅ risk_score: 0 |
| 5 | Error cases (empty, >50KB, bad syntax) | 400/422 | ✅ proper HTTP codes |

## AWS Deployment

### 1. IAM Policy — Confirm Access

Attach this to your Lambda execution role **and verify** it's active:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "*"
    }
  ]
}
```

**Confirm step:** Run `aws bedrock-runtime invoke-model --model-id anthropic.claude-3-5-sonnet-20241022-v2:0 --body '{}' /dev/null 2>&1` — you should see a validation error (not AccessDenied).

### 2. Deploy

```bash
npm install -g serverless
npm install serverless-python-requirements
serverless deploy
```

### 3. Live API URL

After deployment, note the output URL:

```
endpoints:
  ANY - https://<api-id>.execute-api.us-east-1.amazonaws.com/{proxy+}
```

Set this as your live API base URL:

```bash
API_URL="https://<api-id>.execute-api.us-east-1.amazonaws.com"

curl "$API_URL/health"
# → {"status": "ok"}

curl -X POST "$API_URL/scan" \
  -H "Content-Type: application/json" \
  -d '{"code": "while True:\n    print(\"forever\")"}'
```

## GitHub Actions — PR Scanning

Auto-scans changed `.py` files in Pull Requests and comments a risk summary.

### Setup

1. Deploy the API
2. Repo → **Settings → Secrets → Actions** → add `BLASTSHIELD_API_URL`
3. Push — next PR with `.py` changes triggers the scan

### Workflow

`.github/workflows/pr-scan.yml` (~45 lines):
- Triggers on `pull_request` with `.py` changes
- Reads each changed file, POSTs to `/scan`
- Comments ⚠️ or ✅ per file on the PR

## Detection Rules

| Pattern | Detected | Example |
|---------|----------|---------|
| `while True` without `break`/`return`/`raise` | ✅ | `while True: do_work()` |
| `while True` WITH `break` | ❌ Safe | `while True: if done: break` |
| `for x in itertools.count()` without `break` | ✅ | `for i in itertools.count(): ...` |
| `for x in itertools.repeat()` without `break` | ✅ | `for x in itertools.repeat(1): ...` |
| Normal loops | ❌ Safe | `for i in range(100): ...` |

## Fallback Behavior

| Component | Bedrock Available | Bedrock Unavailable |
|-----------|------------------|-------------------|
| Risk detection | ✅ Deterministic | ✅ Same |
| Risk score | ✅ Deterministic | ✅ Same |
| Explanation | ✅ AI-generated | ✅ Static fallback |
| Patch | ✅ AI-generated diff | ✅ Static counter+break diff |

**Patch is NEVER empty when risks are detected.**

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| Parser | tree-sitter + tree-sitter-python |
| AI | AWS Bedrock (Claude 3.5 Sonnet v2) |
| Runtime | AWS Lambda via Mangum |
| Gateway | AWS HTTP API Gateway |
| IaC | Serverless Framework |
| CI/CD | GitHub Actions |
