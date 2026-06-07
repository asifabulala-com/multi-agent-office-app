# Architecture — Multi-Agent Office & Team Simulation

**Use Case ID:** 1 · **G42 Agentathon 2026**

---

## System Overview

A five-agent AI system built on **LangGraph StateGraph** that simulates a complete software project delivery lifecycle. Five specialist agents collaborate through a non-linear workflow — delegating, critiquing, escalating, and replanning — until a coherent, risk-reviewed project plan and MVP are produced.

```
User / Evaluator
      │  POST /run  (port 8000)
      ▼
 FastAPI Server (run.py)
      │
      ▼
 LangGraph PMWorkflowGraph
 ┌────────────────────────────────────────────────────────────────┐
 │                                                                │
 │  Project Manager ◄──── Risk Analyst                           │
 │       │  (escalates high risks)    │                           │
 │       │                            │ assess_risks              │
 │       ▼                            │                           │
 │  Stakeholder ──────────────────────►                           │
 │       │ (approves / rejects plan)                              │
 │       │                                                        │
 │       ▼                                                        │
 │    Engineer ◄──────────────────────────────────────────────    │
 │       │                                          ▲             │
 │       │ (implements task)                  needs_revision      │
 │       ▼                                          │             │
 │   QA Agent ──────────────────────────────────────             │
 │       │ (critiques / approves)                                 │
 │       │                                                        │
 │       └──► Project Manager (if max retries reached)           │
 └────────────────────────────────────────────────────────────────┘
      │
      ▼
 Shared Working Memory (ProjectState TypedDict)
 logs/agent_trace.jsonl
 output_examples/{project_id}/mvp.html
```

---

## Agents

| Agent | Model | Decision Authority | Key Collaboration Signals |
|---|---|---|---|
| **Project Manager** | GPT-5.1 | Decomposes requirements, assigns tasks, replans on escalation | `replan_based_on_feedback`, `plan_tasks` |
| **Risk Analyst** | GPT-5.1 | Classifies delivery risks, escalates high-severity findings before engineering starts | `escalate_high_risk`, `assess_risks`, `branch_high_risk_path` |
| **Stakeholder** | GPT-4.1 | Approves or rejects project plan; monitors satisfaction mid-run | `reject_plan`, `concern_threshold`, `escalated` |
| **Engineer** | GPT-4.1 | Implements tasks; revises up to 2× per task based on QA critique | `implement_task`, `revision`, `retry_count` |
| **QA Agent** | GPT-4.1 | Critiques each Engineer implementation; returns structured issues with severity | `needs_revision`, `critique_implementation`, `approved` |

---

## Collaboration Patterns

### 1. Risk-Driven Replanning
```
PM.plan_tasks()
    → RiskAnalyst.assess_risks()
    → IF high_risks_detected:
        RiskAnalyst.escalate_high_risk() → PM
        PM.replan_based_on_feedback()    [branch_high_risk_path]
    → Stakeholder.review_plan()
```

### 2. Stakeholder Rejection Loop
```
Stakeholder.review_plan()
    → IF satisfaction < threshold:
        Stakeholder.reject_plan() → PM
        PM.replan_based_on_feedback()
        Stakeholder.review_plan()   [up to MAX_STAKEHOLDER_REVISIONS]
```

### 3. QA Critique & Revision Loop
```
Engineer.implement_task()
    → QAAgent.critique_implementation()
    → IF issues_found:
        QAAgent.needs_revision() → Engineer
        Engineer.implement_task()  [revision, retry_count += 1]
        [up to MAX_QA_RETRIES = 2]
    → IF approved:
        next task
```

### 4. Shared Memory
All agents read and write `ProjectState` — a LangGraph `TypedDict` holding:
- `tasks` — task list with status and assignee
- `risks` — risk register with severity and mitigation
- `decisions` — audit trail of all agent decisions
- `messages` — inter-agent communication history
- `qa_feedback` — QA findings per task
- `stakeholder_score` — running satisfaction metric

---

## Real Public Data Integration

| Source | Used By | Purpose |
|---|---|---|
| **O\*NET 28.3 Database** (U.S. Dept of Labor, CC BY 4.0) | Risk Analyst | Technology demand, talent pool, availability risk per stack component |
| **BLS OES May 2023** (Public Domain) | Project Manager | Team cost estimation by role (SOC codes, median wages) |
| **NIST NVD REST API 2.0** (Public Domain) | Risk Analyst + QA | Known HIGH/CRITICAL CVEs for technologies in the stack |
| **npm Registry API** (public) | Engineer | Package maintenance health, stale library detection |
| **PyPI JSON API** (public) | Engineer | Python library release health |

---

## LangGraph StateGraph — Node Map

```
START
  ├─► initialize_run
  ├─► plan_tasks                     [ProjectManager]
  ├─► assess_risks                   [RiskAnalyst]
  ├─► branch_high_risk_path          [conditional edge → replan or continue]
  ├─► escalate_risks                 [RiskAnalyst → ProjectManager]
  ├─► replan_based_on_feedback       [ProjectManager]
  ├─► stakeholder_review             [Stakeholder]
  ├─► branch_stakeholder_approval    [conditional edge → reject or continue]
  ├─► reject_plan                    [Stakeholder → ProjectManager]
  ├─► implement_tasks                [Engineer × N tasks]
  ├─► qa_review                      [QAAgent × N tasks]
  ├─► branch_qa_result               [conditional edge → revise or approve]
  ├─► needs_revision                 [QAAgent → Engineer]
  ├─► monitor_progress               [Stakeholder mid-run]
  ├─► branch_concern_threshold       [conditional edge → escalate or continue]
  ├─► finalize_output                [ProjectManager]
END
```

---

## API Interface

### `POST /run`
```json
{
  "project_id": "IT_ServiceDesk_001",
  "project_name": "IT Service Management Portal",
  "description": "...",
  "use_case_id": "1",
  "input": "...",
  "context": {"domain": "telecom", "department": "corporate-it"}
}
```
Returns `RunResponse` with `status`, `request_id`, `execution_time_seconds`, `output`, `agent_trace`, `logs`, `metadata`.

### `GET /health`
Returns `{"status": "ok", "service": "multi-agent-pm-system", "version": "1.0.0", "timestamp": "...", "timeout_seconds": 900}`.

### `GET /compass/probe`
Verifies Compass API connectivity; returns probe result with model used and response validation.

---

## Timeout & Reliability

| Layer | Timeout | Behaviour |
|---|---|---|
| Inner graph | 720 s | LangGraph raises `TimeoutError`; caught by graph node |
| Outer `/run` | 900 s | `asyncio.wait_for` → HTTP 408 with standard error body |
| SAMPLE_MODE | Instant | SHA-256 deterministic fallback; no API calls |
| QA retries | Max 2/task | After 2 failed critiques, Engineer output is accepted |
| Stakeholder | Max 2 revisions | After 2 plan rejections, last plan is accepted |
| NIST NVD calls | 5 s per request | Timeout → graceful skip, no crash |

---

## File Layout

```
multi-agent-office-simulation/
├── run.py                  # FastAPI server + CLI entry point
├── metadata.json           # Submission metadata (agents, tools, compass_models)
├── Dockerfile              # Single-stage Python 3.11-slim build
├── docker-compose.yml      # Compose with env_file and healthcheck
├── requirements.txt        # Pinned dependencies
├── .env.example            # Environment variable template (no secrets)
├── app/
│   ├── graph.py            # LangGraph PMWorkflowGraph StateGraph
│   ├── orchestrator.py     # Thin wrapper; run_workflow()
│   ├── agents/             # ProjectManager, Engineer, QAAgent, RiskAnalyst, Stakeholder
│   ├── compass_integration.py  # OpenAI client pointed at Compass endpoint
│   ├── trace_logger.py     # JSONL trace writer
│   ├── memory.py           # SharedMemory (ProjectState TypedDict)
│   └── public_data.py      # O*NET, BLS, NIST NVD, npm, PyPI clients
├── data/
│   ├── onet_tech_skills.json   # Bundled O*NET 28.3 data
│   └── bls_wage_data.json      # Bundled BLS OES May 2023 data
├── dataset/
│   └── telecom_projects.json   # 20 telecom enabling-function project specs
├── logs/
│   └── agent_trace.jsonl   # Pre-existing traces from 24 completed runs
├── input_examples/
│   ├── input_1.json        # IT Service Management Portal (judge default)
│   ├── input_2.json        # Revenue Assurance Dashboard
│   ├── input_3.json        # NOC Monitoring Platform
│   ├── input_it_service_desk.json
│   ├── input_leave_attendance.json
│   └── input_revenue_assurance.json
└── output_examples/
    ├── output_1.json       # Standard RunResponse format (current API)
    ├── output_IT_ServiceDesk_001.json
    ├── output_RA_Dashboard_001.json
    └── ...
```
