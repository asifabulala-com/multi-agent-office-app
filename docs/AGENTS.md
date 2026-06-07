# Agent Specifications

*Last updated: 2026-06-05 — reflects the system as delivered for AI Agenthon evaluation.*

Each agent inherits from `BaseAgent` (`app/base_agent.py`), which provides: LLM calls (`llm_decide`), inter-agent messaging (`send_message` / `receive_messages`), decision logging (`make_decision`), structured trace logging (`log_trace`), and task state updates (`update_task`).

---

## 1. Project Manager — `AgentRole.PROJECT_MANAGER`

**File:** `app/project_manager.py`

### Role
Decomposes the project description into a phased task plan, distributes work to other agents, and replans when risks or stakeholder concerns escalate. Acts as the central coordinator.

### When it runs
- **`plan_project` node** — initial decomposition
- **`replan_project` node** — triggered when `high_risks_detected = True` after `assess_risks`
- **`mid_replan` node** — triggered when `critical_risks_detected = True` during execution

### LLM prompts
- `_PLAN_SYSTEM` — asks for a full project plan in JSON: tasks (id, title, role, description, acceptance_criteria, deliverables, effort_hours, risk_level), technology_stack, phases, total_effort_hours, recommended_team_size, confidence.
- `_REPLAN_SYSTEM` — asks for adjustments to existing tasks and optional new mitigation tasks given the risk register and stakeholder concerns.

### Key method: `_run_planning`
1. Calls `llm_decide(_PLAN_SYSTEM, project description + name)` with `max_tokens=4000`.
2. Creates `Task` objects for roles: `engineer`, `qa`, `risk_analyst`.
3. Stores the rich plan in `project.metadata` and `memory.agent_summaries`.
4. Calls `_distribute_tasks` — sends messages to Risk Analyst, Engineer, and QA.

### Inputs
```json
{ "project_id": "HC_001", "project_name": "Employee Self-Service Portal",
  "description": "Build a web-based portal for telecom employees..." }
```

### Outputs (stored in SharedMemory)
```json
{
  "tasks": [{"id": "task_001", "title": "Backend API setup", "role": "engineer", ...}],
  "technology_stack": {"backend": "FastAPI + Python 3.11", "database": "PostgreSQL 15"},
  "phases": [{"id": "phase_1", "name": "Foundation", "duration_weeks": 2}],
  "total_effort_hours": 120,
  "recommended_team_size": 3
}
```

### Messages sent
| To | Type | Content |
|---|---|---|
| Risk Analyst | `request` | "Project plan ready: N tasks, ~Xh total effort. Stack: ... Please assess delivery risks." |
| Engineer | `task_assignment` | "N implementation task(s) assigned. Stack: ... Await risk clearance." |
| QA | `task_assignment` | "N QA task(s) assigned. Prepare test strategy." |

---

## 2. Engineer — `AgentRole.ENGINEER`

**File:** `app/engineer.py`

### Role
Implements each task assigned from the PM plan by calling the LLM to generate real source files. Revises output based on QA critique. After all tasks complete, generates a self-contained MVP HTML file.

### When it runs
- **`implement_task` node** — once per task in the engineer queue
- **`engineer_revise` node** — triggered when QA rejects and `qa_retry_count < MAX_QA_RETRIES`
- **`finalize_project` node** — calls `generate_mvp_html`

### LLM prompts
- `_CODE_GEN_SYSTEM` — asks for complete React/TypeScript source files (no TODOs, no banned packages), returns JSON with `files[]`, `implementation_summary`, `technical_approach`, `confidence`.
- `_CODE_REVISE_SYSTEM` — asks to fix every QA-flagged issue; returns full revised file contents.
- `_MVP_SYSTEM` — asks for a single self-contained HTML MVP (all CSS/JS inline, dark theme, CRUD, localStorage persistence, `<dialog>` elements).

### Key methods
- `_write_files(project_id, files)` — writes each file to `output_examples/{project_id}/spa/`, sanitises `package.json` to remove banned packages and pin safe versions.
- `generate_mvp_html(project)` — calls LLM with MVP prompt, post-processes escaped characters, writes to `output_examples/{project_id}/mvp.html`.

### File index
The engineer maintains a per-project file index in `memory.agent_summaries["engineer:{project_id}:file_index"]` so revisions reference already-written files.

### Inputs
```json
{
  "task": {"id": "task_001", "title": "Backend API setup",
           "description": "...", "acceptance_criteria": [...]},
  "pm_plan_context": "...(first 300 chars of PM summary)...",
  "risk_warnings": "...(first 200 chars of risk summary)...",
  "files_already_written": ["src/main.tsx", "package.json"]
}
```

### Outputs
- Source files written to `output_examples/{project_id}/spa/`
- Implementation summary stored in `memory.agent_summaries["engineer:{task_id}"]`
- MVP HTML written to `output_examples/{project_id}/mvp.html`

### Messages sent
| To | Type | Content |
|---|---|---|
| QA | `request` | "Implementation of '{task}' ready for QA review. Wrote N file(s): ..." |
| QA | `feedback` | "Revision N of '{task}' ready. Addressed: ..." |

---

## 3. QA Agent — `AgentRole.QA`

**File:** `app/qa_agent.py`

### Role
Critiques each engineer implementation and drives the revision loop. Enforces final quality gates across all completed tasks.

### When it runs
- **`qa_critique` node** — after every `implement_task` and after every `engineer_revise`
- **`check_quality_gates` node** — once at the end of all engineering tasks

### LLM prompts
- `_CRITIQUE_SYSTEM` — first review. Asks for up to 2 concrete issues with severity (low/medium/high/critical). Returns `{has_issues, issues[], approved, confidence, reasoning}`.
- `_RETEST_SYSTEM` — re-evaluation after revision. Biased toward approving unless a critical problem persists. Max 1 remaining issue.

### Key method: `critique_implementation`
1. Reads engineer implementation summary from `memory.get_summary(ENGINEER, task_id)`.
2. Reads risk summary for test focus areas (first 100 chars).
3. Calls `llm_decide` with `max_tokens=600`.
4. **Normalises `issues`**: if the LLM returns strings instead of dicts, wraps them as `{"description": str, "severity": "medium"}`.
5. Stores critique in `memory.agent_summaries["qa:{task_id}"]` for the engineer to read.
6. Sends feedback or approval message to Engineer.
7. Logs to `feedback_loops` in SharedMemory.

### Quality gates (`check_quality_gates`)
All three must pass:

| Gate | Threshold |
|---|---|
| `pass_rate` | ≥ 80 % of reviewed tasks approved |
| `no_critical_defects` | No issue with severity `"critical"` across all defects |
| `confidence_acceptable` | Average QA confidence ≥ 0.75 |

### Inputs
```json
{
  "project_name": "Software Licence Management System",
  "task_title": "Integrate SAM with ITSM",
  "implementation_summary": "...(first 200 chars)...",
  "risk_areas": "...(first 100 chars)..."
}
```

### Outputs
```json
{
  "approved": false,
  "issues": [
    {"description": "Missing retry logic on API timeout", "severity": "medium"}
  ],
  "confidence": 0.88,
  "reasoning": "Implementation lacks error handling for network failures."
}
```

### Messages sent
| To | Type | Content |
|---|---|---|
| Engineer | `feedback` | "QA CRITIQUE (attempt N) of '{task}': Found N issue(s): ..." |
| Engineer | `approval` | "QA APPROVED '{task}'. ..." |
| PM | escalation (via `escalate_issue`) | "Quality gates failed: {gate_names}" |

---

## 4. Risk Analyst — `AgentRole.RISK_ANALYST`

**File:** `app/risk_analyst.py`

### Role
Identifies the top 3 delivery risks after planning, monitors execution progress deterministically, escalates critical risks to the PM, and produces the final risk register.

### When it runs
- **`assess_risks` node** — after `plan_project`; result drives the `high_risks_detected` flag
- **`monitor_risks` node** — after each `qa_critique` completes (one per engineer task)
- **`generate_risk_report` node** — after `check_quality_gates`

### LLM prompts
- `_ASSESS_SYSTEM` — asks for exactly 3 risks as structured dicts: `{id, title, description, probability, impact, severity, affected_tasks[]}`. Escalate flag set if `high_severity_count >= 2`. Uses `max_tokens=800` (no reasoning model — reduced for speed).

### Key method: `_run_assessment`
1. Reads PM plan summary (first 150 chars).
2. Calls `llm_decide` — normalises any string items in `risks` to dicts (defensive guard against LLM schema drift).
3. Stores risk register in `self.risk_register` and `project.risks`.
4. Sends high-severity notification to Stakeholder.
5. If `should_escalate`, calls `escalate_issue` to PM.

### Key method: `_run_monitoring` (deterministic — no LLM call)
- Calculates `progress = completed_tasks / total_tasks`.
- Marks all non-escalating risks as `"stable"`.
- Escalates only if `progress < 20%` AND at least one critical risk exists.
- Runs after every engineer task; kept fast intentionally.

### Inputs
```json
{
  "project_name": "Revenue Leakage Detection System",
  "description": "...(first 200 chars)...",
  "pm_plan": "...(first 150 chars)..."
}
```

### Outputs (stored in SharedMemory and `project.risks`)
```json
{
  "risks": [
    {"id": "risk_001", "title": "Data quality issues", "severity": "high",
     "probability": "medium", "impact": "high", "affected_tasks": ["task_002"]}
  ],
  "high_severity_count": 1,
  "escalate": false,
  "mitigation_recommendations": ["Implement data validation layer before processing"]
}
```

### Messages sent
| To | Type | Content |
|---|---|---|
| Stakeholder | `notification` | "HIGH-SEVERITY RISKS identified: {risk_names}. Details in risk register." |
| PM | escalation | "{N} high-severity risks: {names}" |
| PM | escalation | "Task '{title}' has unresolved QA issues after {N} retries" |

---

## 5. Stakeholder — `AgentRole.STAKEHOLDER`

**File:** `app/stakeholder.py`

### Role
Provides the business perspective. Approves or challenges the plan before engineering begins, reviews progress mid-execution, and gives a final satisfaction score.

### When it runs
- **`stakeholder_approve` node** — after risks are resolved; triggers the engineer task queue build
- **`stakeholder_progress` node** — after all engineering tasks complete
- **`stakeholder_final` node** — after quality gates and risk report

### LLM prompts
- `_APPROVE_SYSTEM` — reviews plan for business viability. Returns `{approved, satisfaction_score, concerns[], recommendations[], confidence, reasoning}`.
- `_PROGRESS_SYSTEM` — reviews execution progress. Returns `{satisfaction_score, concerns[], escalate_to_pm, escalation_message, recommendations[]}`.
- `_FEEDBACK_SYSTEM` — final business review. Returns `{satisfaction_score, status, concerns[], strategic_value, business_impact, recommendations[]}`.

### Key behaviour: plan approval
After the stakeholder approves, `_node_stakeholder_approve` in `graph.py` validates project readiness (`pm.validate_project_readiness`) and builds the `engineer_task_queue` — the ordered list of task IDs the Engineer will work through.

### Escalation
If `satisfaction_score < 65` during `stakeholder_progress`, the PM is automatically notified: *"Concerns received and logged. Adjusting approach to address issues."*

### Inputs
```json
{
  "project_name": "Customer 360 View Platform",
  "tasks": ["Backend API", "Frontend SPA", "Integration tests"],
  "risks": [...],
  "tech_stack": {"backend": "Salesforce + FastAPI"},
  "total_effort_hours": 160
}
```

### Outputs
```json
{
  "approved": true,
  "satisfaction_score": 82,
  "concerns": ["Timeline may be tight given integration complexity"],
  "recommendations": ["Build API contracts first to unblock parallel work"],
  "status": "approved"
}
```

### Messages sent
| To | Type | Content |
|---|---|---|
| PM | `escalation` | Escalation message when satisfaction < threshold |

---

## Agent communication matrix

```
                PM    Engineer    QA    Risk Analyst   Stakeholder
PM          —         tasks     tasks     request         plans
Engineer    escalation    —     request       —              —
QA          gate-fail  feedback    —         —            quality
Risk        escalation    —       —          —            risks
Stakeholder concerns      —       —          —              —
```

## Interaction counts (typical run, 3 engineer tasks)

| Interaction type | Approximate count |
|---|---|
| LLM calls | 12–18 (plan × 1, risks × 1, approve × 1, implement × 3, critique × 3–6, revise × 0–3, progress × 1, final × 1, MVP × 1) |
| Agent messages | 14–25 |
| Decision log entries | 10–16 |
| Feedback loops logged | 0–3 |
