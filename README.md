# BlastShield 🛡️

**AI-powered Python code scanner** — detects infinite loop risks using tree-sitter AST analysis and generates explanations + patches via AWS Bedrock (Amazon Nova Lite).

Built for the **AWS AI for Bharat Hackathon** (Round 2).

## Architecture

```
POST /scan  →  tree-sitter parse  →  infinite loop detection  →  risk score
                                                                      ↓
                                                              AWS Bedrock AI
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
│   │   ├── explainer.py          # AI risk explanation
│   │   └── patcher.py            # AI patch generation (guaranteed non-empty)
│   ├── api/routes/
│   │   └── scan.py               # POST /scan endpoint
│   └── core/
│       ├── parser.py              # tree-sitter Python parser
│       ├── scorer.py              # Risk score calculator
│       └── rules/
│           └── infinite_loop.py   # Infinite loop detection
├── .github/workflows/
│   └── blastshield.yml           # GitHub Actions PR scanner
├── handler.py                    # Mangum Lambda wrapper
├── serverless.yml                # Serverless Framework config
├── requirements.txt
└── .env.example
```

## Local Development

### Prerequisites

- Python 3.11+
- AWS Bedrock access (bearer token or IAM credentials)

### Setup

```bash
cd blastshield-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your AWS credentials
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

## API Reference

### `GET /health`

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok"}
```

### `POST /scan`

**Request:**
```bash
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{
    "code": "import time\n\ndef worker():\n    while True:\n        time.sleep(1)\n        print(\"working...\")\n\nworker()"
  }'
```

**Response (risk detected — real Bedrock AI):**
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
  "explanation": "In production, an infinite loop like `while True` can cause serious problems. The server will keep executing the loop forever, using up all the CPU. This means the server won't be able to handle other important tasks or requests from users, leading to service unavailability. Adding more servers doesn't help because the root problem is the infinite loop. This can lead to prolonged outages.",
  "suggested_patch": "--- original.py\n+++ fixed.py\n@@ -4,6 +4,8 @@\n     while True:\n+        if counter >= 1000:\n+            break\n         time.sleep(1)\n         print(\"working...\")\n+        counter += 1"
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

> **Note:** `suggested_patch` is **always non-empty** when `risk_score > 0`. If Bedrock is unavailable, a deterministic static patch is generated.

## Test Results (10/10 ✅)

### Health Endpoint

| Test | Description | HTTP | Status |
|------|-------------|------|--------|
| H1 | Standard GET | 200 | ✅ |
| H2 | POST (wrong method) | 405 | ✅ |
| H3 | PUT (wrong method) | 405 | ✅ |
| H4 | Non-existent route | 404 | ✅ |
| H5 | Custom Accept header | 200 | ✅ |

### Scan Endpoint

| Test | Description | Score | Status |
|------|-------------|-------|--------|
| S1 | Redis task processor — `while True` polling | 50 ⚠️ | ✅ Detected with AI explanation + patch |
| S2 | Graceful shutdown server — `while True` + `break` | 0 | ✅ Correctly safe |
| S3 | IoT sensor stream — `itertools.count()` | 50 ⚠️ | ✅ Detected with AI explanation + patch |
| S4 | FastAPI CRUD app — no loops | 0 | ✅ No false positives |
| S5 | Error cases (empty, >50KB, bad syntax, non-JSON, GET) | — | ✅ 422/400/405 |

**0 false positives — 0 false negatives — Real Bedrock AI responses**

## AWS Deployment

### IAM Policy Required

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

### Deploy

```bash
npm install -g serverless
npm install serverless-python-requirements
serverless deploy
```

Output shows your API Gateway URL. Copy it and test:

```bash
API_URL="https://your-api-id.execute-api.us-east-1.amazonaws.com"
curl "$API_URL/health"
curl -X POST "$API_URL/scan" \
  -H "Content-Type: application/json" \
  -d '{"code": "while True:\n    print(\"forever\")"}'
```

## GitHub Actions — PR Scanning

Automatically scans Python files changed in PRs and posts a risk report as a PR comment.

### Setup

1. Deploy the API (see above)
2. Go to repo → **Settings → Secrets → Actions**
3. Add secret: `BLASTSHIELD_API_URL` = your API Gateway URL
4. Push — next PR with `.py` changes triggers the scan

### PR Comment Format

```
🛡️ BlastShield Scan Report 🔴
Files scanned: 3 | Average risk: 50/100

⚠️ app/worker.py — Risk Score: 50/100
Explanation: This while True loop will pin CPU at 100%...
[Suggested Patch]

✅ app/utils.py — Clean
```

## Detection Rules

| Pattern | Detected | Example |
|---------|----------|---------|
| `while True` without `break`/`return`/`raise` | ✅ | `while True: do_work()` |
| `while True` WITH `break` | ❌ Safe | `while True: if done: break` |
| `for x in itertools.count()` without `break` | ✅ | `for i in itertools.count(): print(i)` |
| `for x in itertools.repeat()` without `break` | ✅ | `for x in itertools.repeat(1): ...` |
| `for x in iter(callable, sentinel)` without `break` | ✅ | `for x in iter(int, 1): ...` |
| Normal `for` / `while` loops | ❌ Safe | `for i in range(100): ...` |

## Fallback Behavior

| Component | Bedrock Available | Bedrock Unavailable |
|-----------|------------------|-------------------|
| Risk detection | ✅ Deterministic | ✅ Same |
| Risk score | ✅ Deterministic | ✅ Same |
| Explanation | ✅ AI-generated | ✅ Static fallback |
| Patch | ✅ AI-generated diff | ✅ Static safety-counter diff |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| Parser | tree-sitter + tree-sitter-python |
| AI | AWS Bedrock (Amazon Nova Lite) |
| Runtime | AWS Lambda via Mangum |
| Gateway | AWS HTTP API Gateway |
| IaC | Serverless Framework |
| CI/CD | GitHub Actions |
