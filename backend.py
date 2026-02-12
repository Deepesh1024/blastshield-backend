import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

# ── API Key: env var first, then api.txt fallback ──
API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

if not API_KEY:
    api_file = os.path.join(os.path.dirname(__file__), "api.txt")
    if os.path.exists(api_file):
        with open(api_file, "r") as f:
            API_KEY = f.read().strip()

if not API_KEY:
    raise RuntimeError(
        "BlastShield: No API key found. "
        "Set GROQ_API_KEY env var or create api.txt."
    )

client = Groq(api_key=API_KEY)

MODEL = os.environ.get("BLASTSHIELD_MODEL", "moonshotai/kimi-k2-instruct-0905")

# ── Full Scan Prompt (VS Code Extension — all project files) ──

BLUEPRINT_FULL = """
You are BlastShield, a deployment-grade risk detector.

You analyze code for:
- security vulnerabilities  
- reliability failures  
- production breakpoints  
- path traversal  
- injection  
- race conditions  
- misconfigurations  
- bad error handling  
- silent failures  
- memory leaks  
- data corruption risks  
- concurrency anomalies  
- dependency hazards  
- wrong environment assumptions  
- missing boundary checks  
- unsafe I/O  
- incorrect async logic  
- undefined behavior  

Your goal:
Detect ALL issues that could break in real deployments, not just theoretical issues.
Return EVERY issue you find — not just one.

You always return STRICT JSON in this exact format:
{
  "issues": [
    {
      "id": "unique-string",
      "severity": "critical" | "high" | "medium" | "low",
      "file": "ABSOLUTE FILE PATH",
      "issue": "Short issue title",
      "explanation": "Detailed explanation of the problem",
      "risk": "What could go wrong in production",
      "patches": [
        {
          "file": "ABSOLUTE FILE PATH",
          "start_line": number,
          "end_line": number,
          "new_code": "replacement code"
        }
      ],
      "testImpact": ["tests/test_file.py::test_name", "..."]
    }
  ],
  "riskScore": number_between_0_and_100
}

Rules:
- Return ALL issues found, not just one.
- Always use absolute paths exactly as given.
- Never invent filenames.
- Never output markdown or text outside the JSON.
- Never write comments outside JSON.
- Find real problems with real production reasoning.
- Patches must be fully runnable code blocks.
- Each issue must have a unique id string.
- severity must be one of: "critical", "high", "medium", "low".
- riskScore is 0-100 representing overall project risk.
- testImpact should list likely impacted test files/functions.
- If no issues are found, return {"issues": [], "riskScore": 0}.
"""

# ── PR Scan Prompt (GitHub Actions — only changed files) ──

BLUEPRINT_PR = """
You are BlastShield, a deployment-grade risk detector for Pull Request reviews.

You are given ONLY the files changed in a Pull Request — not the entire codebase.
Focus your analysis strictly on what was changed.

You analyze for:
- security vulnerabilities introduced by the changes
- reliability failures in the modified code
- race conditions or concurrency bugs
- path traversal or injection risks
- unsafe I/O or file operations
- incorrect async/await logic
- missing boundary checks or input validation
- bad error handling or silent failures
- breaking API contracts
- dependency misuse

Your goal:
Find every issue in the CHANGED FILES that could break in production.
Be specific about WHY the change is dangerous.

You always return STRICT JSON in this exact format:
{
  "issues": [
    {
      "id": "unique-string",
      "severity": "critical" | "high" | "medium" | "low",
      "file": "relative/path/to/file",
      "issue": "Short issue title",
      "explanation": "Detailed explanation — what's wrong and why it matters",
      "risk": "What breaks in production if this ships",
      "patches": [
        {
          "file": "relative/path/to/file",
          "start_line": number,
          "end_line": number,
          "new_code": "replacement code"
        }
      ],
      "testImpact": ["tests/test_file.py::test_name"]
    }
  ],
  "riskScore": number_between_0_and_100,
  "summary": "One-paragraph summary of the PR's risk profile"
}

Rules:
- Return ALL issues found in the changed files.
- Use file paths exactly as given (relative paths).
- Never invent filenames.
- Never output markdown or text outside the JSON.
- Patches must be fully runnable replacement code.
- Each issue must have a unique id string.
- severity must be one of: "critical", "high", "medium", "low".
- riskScore is 0-100 representing this PR's risk level.
- summary is a brief paragraph for the PR comment.
- If no issues are found, return {"issues": [], "riskScore": 0, "summary": "No issues detected."}.
"""


def build_prompt(files, blueprint):
    combined_parts = []
    for f in files:
        combined_parts.append(f"=== FILE: {f['path']} ===\n{f['content']}")
    combined = "\n\n".join(combined_parts)
    return f"""
{blueprint}

Here are the code files to analyze:

{combined}
"""


def normalize_issues(parsed):
    """Ensure all issues have required fields."""
    issues = parsed.get("issues", [])
    for i, issue in enumerate(issues):
        if not issue.get("id"):
            issue["id"] = str(i + 1)
        if "testImpact" not in issue:
            issue["testImpact"] = []
        if "risk" not in issue:
            issue["risk"] = issue.get("explanation", "")
        if "patches" not in issue:
            issue["patches"] = []
    return issues


# ── Route: Full Project Scan (VS Code Extension) ──

@app.route("/scan", methods=["POST"])
def scan():
    data = request.get_json()
    files = data.get("files", [])

    if not files and "combined" in data:
        files = [{"path": "unknown", "content": data["combined"]}]

    if not files:
        return jsonify({"message": "error", "detail": "No files provided."}), 400

    prompt = build_prompt(files, BLUEPRINT_FULL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )

        llm_text = response.choices[0].message.content

        try:
            parsed = json.loads(llm_text)
        except Exception:
            return jsonify({"message": "invalid_json", "raw": llm_text}), 200

        issues = normalize_issues(parsed)
        risk_score = parsed.get("riskScore", 50)

        return jsonify({
            "message": "scan_complete",
            "report": {
                "issues": issues,
                "riskScore": risk_score
            }
        })

    except Exception as e:
        return jsonify({"message": "error", "detail": str(e)}), 500


# ── Route: PR Scan (GitHub Actions) ──

@app.route("/pr-scan", methods=["POST"])
def pr_scan():
    data = request.get_json()
    files = data.get("files", [])

    if not files:
        return jsonify({"message": "error", "detail": "No changed files provided."}), 400

    prompt = build_prompt(files, BLUEPRINT_PR)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )

        llm_text = response.choices[0].message.content

        try:
            parsed = json.loads(llm_text)
        except Exception:
            return jsonify({"message": "invalid_json", "raw": llm_text}), 200

        issues = normalize_issues(parsed)
        risk_score = parsed.get("riskScore", 50)
        summary = parsed.get("summary", "BlastShield scan complete.")

        return jsonify({
            "message": "scan_complete",
            "report": {
                "issues": issues,
                "riskScore": risk_score,
                "summary": summary
            }
        })

    except Exception as e:
        return jsonify({"message": "error", "detail": str(e)}), 500


# ── Health Check ──

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
