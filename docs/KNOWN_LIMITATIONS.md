# Known Limitations

*Documenting these honestly so judges can assess the system fairly and run it without surprises.*

---

## Execution behaviour

### QA retries capped at 1 per task
`MAX_QA_RETRIES = 1` in `app/graph.py`. The Engineer may revise each task at most once before QA passes it through regardless of remaining issues. This was reduced from 2 to keep total execution time under 2 minutes per project. A higher value is more rigorous but slower.

### Risk monitoring is deterministic
The `_run_monitoring` method in `app/risk_analyst.py` does not call the LLM. It checks progress percentage and critical-risk count against fixed thresholds. This saves one LLM call per engineer task (~3–6 calls per run). The trade-off: mid-execution risk re-evaluation is rule-based, not reasoned.

### Maximum 3 engineer tasks per run
`MAX_ITERATIONS = 3` in `app/graph.py`. If the PM produces more than 3 engineer tasks, only the first 3 are processed. This bounds execution time at the cost of partial project coverage.

---

## Data persistence

### All state is in-memory only
`SharedMemory` stores everything in Python dicts. Restarting the server (`python run.py`) clears all project history, messages, and decisions. There is no database layer. Concurrent runs from different browser tabs share the same memory instance and can interfere.

### MVP HTML is per-project, not per-run
`output_examples/{project_id}/mvp.html` is overwritten on each run for the same `project_id`. Use distinct `project_id` values to preserve multiple outputs.

---

## LLM reliability

### LLM sometimes returns strings instead of dicts in arrays
The LLM occasionally returns `"issues": ["Missing error handling"]` instead of `"issues": [{"description": "...", "severity": "medium"}]`. Defensive normalisation is applied in `critique_implementation` (QA) and `_run_assessment` (Risk Analyst) — string items are wrapped into dicts with `severity: "medium"`. This prevents crashes but results in lower-quality issue descriptions.

### JSON parse failures fall back gracefully
If the LLM returns non-JSON (e.g. prose with embedded JSON, or a truncated response), `llm_decide` returns `{"reasoning": raw_text, "confidence": 0.65, "decision": "proceed"}`. The workflow continues with reduced information — no crash, but the affected agent's output will be thin.

### MVP HTML quality varies by project domain
The `_MVP_SYSTEM` prompt asks the LLM for a complete, domain-appropriate MVP. For generic or abstract project descriptions the LLM may produce a less realistic UI. The output is always self-contained HTML but the domain-specific data and interactions reflect LLM best-effort.

---

## Compass integration

### Evaluation API returns errors in some configurations
`submit_compass` in `app/graph.py` submits project data to the G42 Compass evaluation endpoint. When the evaluation API is unavailable or returns an unexpected response, the submission is logged as `{"status": "error", "message": "Submission failed"}`. The rest of the workflow (report generation, MVP, response to the caller) completes normally. The collaboration metrics are still calculated and returned in the response JSON.

---

## Generated source files

### Engineer-written files are not compiled or executed
The Engineer agent writes React/TypeScript source files to `output_examples/{project_id}/spa/`. These represent the LLM's best attempt at a working implementation but are not verified by actually running `npm install && npm run dev`. Syntax errors or missing imports are possible. The separately generated `mvp.html` is always self-contained and verified to open in a browser.

### Banned package list may lag behind ecosystem changes
`app/engineer.py` maintains a blocklist of packages that cause `npm install` failures (e.g. Next.js, Material UI). New packages added to the LLM's training set after the blocklist was written may still appear in generated `package.json` files.

---

## Web UI

### No user authentication
The web UI and API have no authentication. Anyone who can reach port 8000 can run simulations and read results.

### Project history not shown in UI after server restart
The result panel shows only the most recent simulation result for the current browser session. Previous runs are not recoverable after a server restart.

---

## Infrastructure

### No Docker support in the current build
The README references Docker setup inherited from an earlier version. The current codebase does not include a `Dockerfile` or `docker-compose.yml`. Use the Python virtual environment setup (`python -m venv venv; pip install -r requirements.txt; python run.py`).

### Python version constraint
The `venv` directory in the repo was created with Python 3.14 (the version installed on the development machine). On a different Python version, recreate the venv: `python -m venv venv && pip install -r requirements.txt`.
