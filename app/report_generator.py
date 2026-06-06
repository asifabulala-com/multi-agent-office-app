"""HTML report generator with Mermaid sequence diagram.

Converts the workflow result dict into a self-contained HTML file saved to
reports/report_{run_id}.html. Opens automatically after generation.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

_AGENT_LABELS: Dict[str, str] = {
    "project_manager": "PM",
    "risk_analyst": "Risk",
    "engineer": "Engineer",
    "qa": "QA",
    "stakeholder": "Stakeholder",
    "orchestrator": "Orchestrator",
}

_ARROW: Dict[str, str] = {
    "escalation": "->>",
    "approval": "-->>",
    "feedback": "->>",
    "request": "->>",
    "task_assignment": "->>",
    "notification": "-->>",
    "response": "-->>",
}

_SEVERITY_COLOR: Dict[str, str] = {
    "critical": "#c0392b",
    "high": "#e67e22",
    "medium": "#f1c40f",
    "low": "#27ae60",
}

_MSG_TYPE_COLOR: Dict[str, str] = {
    "escalation": "#e74c3c",
    "approval": "#27ae60",
    "feedback": "#e67e22",
    "request": "#3498db",
    "task_assignment": "#9b59b6",
    "notification": "#95a5a6",
    "response": "#1abc9c",
}


def _safe(text: str, max_len: int = 60) -> str:
    """Sanitize text for Mermaid sequence diagram labels.

    Mermaid is sensitive to: quotes, colons, semicolons, hash, newlines,
    angle brackets, and non-ASCII characters.
    """
    import re
    text = str(text)
    text = text.replace("\n", " ").replace("\r", " ")
    # Remove non-ASCII (em dashes, smart quotes, arrows, etc.)
    text = text.encode("ascii", errors="ignore").decode("ascii")
    # Strip characters that break Mermaid syntax even inside quotes
    text = re.sub(r'[#;{}<>]', "", text)
    # Replace double quotes (label delimiter) with single quotes
    text = text.replace('"', "'")
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_mermaid(messages: List[Dict[str, Any]]) -> str:
    lines = ["sequenceDiagram"]

    # Declare participants in appearance order
    seen: List[str] = []
    for m in messages:
        for role in (m.get("sender", ""), m.get("receiver", "")):
            label = _AGENT_LABELS.get(role, role.replace("_", " ").title())
            if label and label not in seen:
                seen.append(label)
                lines.append(f"    participant {label}")

    for m in messages:
        sender = _AGENT_LABELS.get(m.get("sender", ""), m.get("sender", ""))
        receiver = _AGENT_LABELS.get(m.get("receiver", ""), m.get("receiver", ""))
        msg_type = m.get("message_type", "request")
        content = _safe(m.get("content", ""))
        arrow = _ARROW.get(msg_type, "->>")

        if sender == receiver:
            lines.append(f'    Note over {sender}: "{content}"')
        else:
            lines.append(f'    {sender}{arrow}{receiver}: "{content}"')

    return "\n".join(lines)


def _score_card(label: str, value: float, max_val: float = 10.0) -> str:
    pct = int(value / max_val * 100)
    color = "#27ae60" if pct >= 75 else "#e67e22" if pct >= 50 else "#e74c3c"
    return f"""
    <div class="score-card">
        <div class="score-value" style="color:{color}">{value}</div>
        <div class="score-bar-bg">
            <div class="score-bar" style="width:{pct}%;background:{color}"></div>
        </div>
        <div class="score-label">{_html_escape(label)}</div>
    </div>"""


def _risk_row(risk: Dict[str, Any]) -> str:
    sev = risk.get("severity", "low")
    color = _SEVERITY_COLOR.get(sev, "#95a5a6")
    return f"""
    <tr>
        <td><span class="badge" style="background:{color}">{_html_escape(sev.upper())}</span></td>
        <td><strong>{_html_escape(risk.get("title", ""))}</strong></td>
        <td>{_html_escape(risk.get("description", ""))}</td>
        <td>{_html_escape(risk.get("probability", ""))}</td>
    </tr>"""


def _decision_row(d: Dict[str, Any]) -> str:
    agent = d.get("agent", "")
    label = _AGENT_LABELS.get(agent, agent.replace("_", " ").title())
    ts = d.get("timestamp", "")[:19].replace("T", " ")
    decision = _html_escape(d.get("decision", ""))
    reasoning = _html_escape(d.get("reasoning", ""))
    is_reject = "reject" in decision.lower() or "needs revision" in decision.lower()
    is_approve = "approve" in decision.lower()
    dot_color = "#e74c3c" if is_reject else "#27ae60" if is_approve else "#3498db"
    return f"""
    <div class="timeline-item">
        <div class="timeline-dot" style="background:{dot_color}"></div>
        <div class="timeline-content">
            <div class="timeline-header">
                <span class="agent-chip">{label}</span>
                <span class="timeline-ts">{ts}</span>
            </div>
            <div class="timeline-decision">{decision}</div>
            <div class="timeline-reasoning">{reasoning}</div>
        </div>
    </div>"""


def _tech_stack_html(stack: Dict[str, Any]) -> str:
    if not stack:
        return "<p>Technology stack not available.</p>"
    rows = ""
    for key, val in stack.items():
        if key == "key_libraries":
            val = ", ".join(val) if isinstance(val, list) else val
        label = key.replace("_", " ").title()
        rows += f"<tr><td><strong>{_html_escape(label)}</strong></td><td>{_html_escape(str(val))}</td></tr>"
    return f"<table>{rows}</table>"


def _phases_html(phases: List[Dict[str, Any]]) -> str:
    if not phases:
        return ""
    html = '<div class="phases-row">'
    for p in phases:
        tasks_list = ", ".join(p.get("tasks", []))
        html += f"""
        <div class="phase-card">
            <div class="phase-name">{_html_escape(p.get("name", ""))}</div>
            <div class="phase-dur">{p.get("duration_weeks", "?")} weeks</div>
            <div class="phase-goal">{_html_escape(p.get("goal", ""))}</div>
            <div class="phase-tasks">Tasks: {_html_escape(tasks_list)}</div>
        </div>"""
    html += "</div>"
    return html


def _task_card_html(t: Dict[str, Any]) -> str:
    risk = t.get("risk_level", "medium")
    risk_color = {"high": "#e74c3c", "medium": "#e67e22", "low": "#27ae60"}.get(risk, "#95a5a6")
    deps = ", ".join(t.get("dependencies", [])) or "None"
    criteria = t.get("acceptance_criteria", [])
    deliverables = t.get("deliverables", [])
    criteria_html = "".join(f"<li>{_html_escape(c)}</li>" for c in criteria)
    deliverables_html = "".join(f"<li>{_html_escape(d)}</li>" for d in deliverables)
    return f"""
    <div class="task-card">
        <div class="task-header">
            <span class="task-id">{_html_escape(t.get("id",""))}</span>
            <span class="task-title">{_html_escape(t.get("title",""))}</span>
            <span class="badge" style="background:{risk_color}">{risk.upper()}</span>
            <span class="task-effort">{t.get("effort_hours","?")}h</span>
        </div>
        <div class="task-desc">{_html_escape(t.get("description",""))}</div>
        {"<div class='task-section'><strong>Acceptance Criteria</strong><ul>" + criteria_html + "</ul></div>" if criteria else ""}
        {"<div class='task-section'><strong>Deliverables</strong><ul>" + deliverables_html + "</ul></div>" if deliverables else ""}
        <div class="task-meta">Phase: {_html_escape(t.get("phase","N/A"))} &nbsp;|&nbsp; Dependencies: {_html_escape(deps)}</div>
    </div>"""


def _public_data_html(metadata: Dict[str, Any]) -> str:
    if not metadata:
        return "<p>No public data enrichment details available.</p>"

    sections: List[str] = []
    bls = metadata.get("bls_cost_estimate", {})
    if bls:
        rows = ""
        for b in bls.get("breakdown", []):
            rows += (
                f"<tr><td>{_html_escape(b.get('occupation',''))}</td>"
                f"<td>{_html_escape(b.get('soc_code',''))}</td>"
                f"<td>${b.get('annual_median_wage_usd',0):,.0f}</td></tr>"
            )
        sections.append(
            "<div class='public-data-card'><h4>BLS OES Cost Estimate</h4>"
            f"<p>Estimated annual team cost: <strong>{_html_escape(bls.get('estimated_annual_cost_formatted',''))}</strong></p>"
            "<table><thead><tr><th>Occupation</th><th>SOC Code</th><th>Annual Wage</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )

    risk_public = metadata.get("risk_public_data", {})
    onet = risk_public.get("onet_assessment", {})
    if onet and onet.get("findings"):
        lines = ""
        for f in onet.get("findings", [])[:6]:
            lines += (
                f"<li>{_html_escape(f.get('technology',''))}: demand {_html_escape(f.get('demand_level',''))}, "
                f"pool {_html_escape(f.get('talent_pool',''))}, risk {_html_escape(f.get('availability_risk',''))}</li>"
            )
        sections.append(
            "<div class='public-data-card'><h4>O*NET Workforce Intelligence</h4>"
            f"<p><strong>Overall resource risk:</strong> {_html_escape(onet.get('overall_resource_risk','').upper())}</p>"
            f"<ul>{lines}</ul></div>"
        )

    cves = metadata.get("nist_cve_findings", []) or risk_public.get("nist_cve", {}).get("cves_found", [])
    if cves:
        items = "".join(
            f"<li>{_html_escape(str(c.get('cve_id', c)))}</li>" for c in cves[:6]
        )
        sections.append(
            "<div class='public-data-card'><h4>NIST NVD CVE Findings</h4>"
            f"<ul>{items}</ul></div>"
        )

    warnings = metadata.get("package_health_warnings", [])
    if warnings:
        items = "".join(f"<li>{_html_escape(str(w))}</li>" for w in warnings[:6])
        sections.append(
            "<div class='public-data-card'><h4>Package Health Warnings</h4>"
            f"<ul>{items}</ul></div>"
        )

    if not sections:
        return "<p>No public data enrichment details available.</p>"
    return "<div class='public-data-grid'>" + "".join(sections) + "</div>"


def _message_row(m: Dict[str, Any]) -> str:
    sender = _AGENT_LABELS.get(m.get("sender", ""), m.get("sender", ""))
    receiver = _AGENT_LABELS.get(m.get("receiver", ""), m.get("receiver", ""))
    msg_type = m.get("message_type", "request")
    color = _MSG_TYPE_COLOR.get(msg_type, "#95a5a6")
    ts = m.get("timestamp", "")[:19].replace("T", " ")
    content = _html_escape(m.get("content", ""))
    return f"""
    <div class="msg-row">
        <span class="msg-badge" style="background:{color}">{msg_type}</span>
        <span class="msg-agents">{sender} &rarr; {receiver}</span>
        <span class="msg-ts">{ts}</span>
        <div class="msg-content">{content}</div>
    </div>"""


def generate_report(result: Dict[str, Any], project_name: str) -> Path:
    """Generate a self-contained HTML report. Returns the file path."""
    run_id = result.get("run_id", "unknown")
    project_id = result.get("project_id", "")
    interactions = result.get("interactions", {})
    messages: List[Dict[str, Any]] = interactions.get("messages", [])
    decisions: List[Dict[str, Any]] = interactions.get("decisions", [])
    feedback_loops: Dict[str, Any] = interactions.get("feedback_loops", {})
    compass = result.get("compass_evaluation", {})
    scores: Dict[str, Any] = compass.get("results", {}).get("scores", {})
    metrics: Dict[str, Any] = compass.get("metrics", {})
    project_metadata = result.get("project_metadata", {})
    public_data_html = _public_data_html(project_metadata)

    # Risk register
    risk_key = f"risk_analyst:{project_id}"
    risk_raw = interactions.get("agent_summaries", {}).get(risk_key, "{}")
    try:
        risks: List[Dict[str, Any]] = json.loads(risk_raw).get("risks", [])
    except Exception:
        risks = []

    # Project plan from PM summary
    pm_key = f"project_manager:{project_id}"
    pm_raw = interactions.get("agent_summaries", {}).get(pm_key, "{}")
    try:
        pm_data = json.loads(pm_raw)
        tech_stack: Dict[str, Any] = pm_data.get("technology_stack", {})
        phases: List[Dict[str, Any]] = pm_data.get("phases", [])
        project_summary_text: str = pm_data.get("project_summary", "")
        total_effort: int = pm_data.get("total_effort_hours", 0)
        team_size: int = pm_data.get("team_size", 0)
    except Exception:
        tech_stack, phases, project_summary_text, total_effort, team_size = {}, [], "", 0, 0

    # Full task list with rich metadata from raw_plan
    raw_plan_tasks: List[Dict[str, Any]] = []
    try:
        raw_plan = pm_data.get("raw_plan", {})
        raw_plan_tasks = raw_plan.get("tasks", [])
    except Exception:
        pass

    # Stakeholder summary
    sh_key = f"stakeholder:{project_id}"
    sh_raw = interactions.get("agent_summaries", {}).get(sh_key, "{}")
    try:
        sh_data = json.loads(sh_raw)
        sh_score = sh_data.get("score", "N/A")
        sh_concerns = sh_data.get("concerns", [])
    except Exception:
        sh_score, sh_concerns = "N/A", []

    mermaid_code = _build_mermaid(messages)

    # Project plan HTML blocks
    tech_html = _tech_stack_html(tech_stack)
    phases_html = _phases_html(phases)
    task_cards_html = "".join(_task_card_html(t) for t in raw_plan_tasks) if raw_plan_tasks else (
        "<p style='color:#888'>Detailed task cards not available in fallback mode.</p>"
    )
    plan_meta = ""
    if total_effort:
        plan_meta = (
            f"<div class='plan-meta'>"
            f"<span>Total effort: <strong>{total_effort}h</strong></span>"
            f"<span>Recommended team: <strong>{team_size} people</strong></span>"
            f"<span>Phases: <strong>{len(phases)}</strong></span>"
            f"</div>"
        )
    project_summary_html = (
        f"<p class='project-summary'>{_html_escape(project_summary_text)}</p>"
        if project_summary_text else ""
    )

    score_cards_html = "".join(
        _score_card(k.replace("_", " ").title(), v)
        for k, v in scores.items()
    ) if scores else "<p>No scores available</p>"

    risk_rows_html = "".join(_risk_row(r) for r in risks) if risks else (
        "<tr><td colspan='4' style='text-align:center;color:#888'>No risks recorded</td></tr>"
    )

    decisions_html = "".join(_decision_row(d) for d in decisions)

    messages_html = "".join(_message_row(m) for m in messages)

    # Feedback loop summary
    fl_html = ""
    for pair, entries in feedback_loops.items():
        pair_label = pair.replace("→", " &rarr; ").replace("->", " &rarr; ")
        fl_html += f'<div class="fl-pair"><strong>{pair_label}</strong> — {len(entries)} exchange(s)<ul>'
        for e in entries:
            ts = e.get("timestamp", "")[:19].replace("T", " ")
            fl_html += f'<li><span class="fl-ts">{ts}</span> {_html_escape(e.get("feedback", ""))}</li>'
        fl_html += "</ul></div>"
    if not fl_html:
        fl_html = "<p>No feedback loops recorded</p>"

    by_type = metrics.get("by_message_type", {})
    msg_type_pills = " ".join(
        f'<span class="msg-badge" style="background:{_MSG_TYPE_COLOR.get(k,"#888")}">'
        f'{k}: {v}</span>'
        for k, v in by_type.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Report – {_html_escape(project_name)}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f0f2f5; color: #1a1a2e; }}
  header {{ background: linear-gradient(135deg,#1a1a2e,#16213e);
            color: #fff; padding: 32px 40px; }}
  header h1 {{ font-size: 1.8rem; font-weight: 700; }}
  header .meta {{ margin-top: 8px; opacity: .75; font-size: .9rem; }}
  header .status-chip {{ display:inline-block; background:#27ae60; color:#fff;
                          padding:3px 12px; border-radius:20px; font-size:.8rem;
                          font-weight:600; margin-left:12px; vertical-align:middle; }}
  .container {{ max-width: 1200px; margin: 32px auto; padding: 0 24px; }}
  .section {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08);
              padding: 28px 32px; margin-bottom: 28px; }}
  .section h2 {{ font-size: 1.2rem; color: #1a1a2e; margin-bottom: 20px;
                 padding-bottom: 12px; border-bottom: 2px solid #f0f2f5; }}
  .scores-grid {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .score-card {{ flex: 1; min-width: 140px; background: #f8f9fa; border-radius: 10px;
                 padding: 16px; text-align: center; }}
  .score-value {{ font-size: 2rem; font-weight: 700; }}
  .score-bar-bg {{ height: 6px; background: #e0e0e0; border-radius: 3px; margin: 8px 0; }}
  .score-bar {{ height: 6px; border-radius: 3px; transition: width .3s; }}
  .score-label {{ font-size: .8rem; color: #666; font-weight: 500; }}
  .mermaid-wrap {{ overflow-x: auto; background: #fafafa; border-radius: 8px;
                   padding: 20px; border: 1px solid #e8e8e8; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 10px 14px; background: #f8f9fa;
        font-size: .85rem; color: #555; font-weight: 600; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #f0f2f5; font-size: .9rem; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; color: #fff; padding: 2px 10px;
            border-radius: 12px; font-size: .75rem; font-weight: 700; }}
  .timeline-item {{ display: flex; gap: 16px; margin-bottom: 18px; position: relative; }}
  .timeline-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
                   margin-top: 4px; }}
  .timeline-content {{ flex: 1; background: #f8f9fa; border-radius: 8px; padding: 12px 16px; }}
  .timeline-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
  .agent-chip {{ background: #1a1a2e; color: #fff; padding: 2px 10px;
                 border-radius: 12px; font-size: .75rem; font-weight: 600; }}
  .timeline-ts {{ font-size: .75rem; color: #999; }}
  .timeline-decision {{ font-weight: 600; font-size: .9rem; margin-bottom: 4px; }}
  .timeline-reasoning {{ font-size: .85rem; color: #666; }}
  .msg-row {{ padding: 10px 0; border-bottom: 1px solid #f0f2f5; }}
  .msg-row:last-child {{ border-bottom: none; }}
  .msg-badge {{ display: inline-block; color: #fff; padding: 2px 8px;
                border-radius: 10px; font-size: .72rem; font-weight: 600; }}
  .msg-agents {{ font-weight: 600; font-size: .9rem; margin: 0 10px; }}
  .msg-ts {{ font-size: .75rem; color: #999; }}
  .msg-content {{ margin-top: 4px; font-size: .85rem; color: #555; padding-left: 4px; }}
  .fl-pair {{ margin-bottom: 16px; }}
  .fl-pair ul {{ margin-top: 8px; padding-left: 20px; }}
  .fl-pair li {{ margin-bottom: 6px; font-size: .88rem; color: #555; }}
  .fl-ts {{ font-size: .75rem; color: #999; margin-right: 8px; }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr));
                   gap: 14px; }}
  .metric-box {{ background: #f8f9fa; border-radius: 8px; padding: 14px;
                 text-align: center; }}
  .metric-num {{ font-size: 1.8rem; font-weight: 700; color: #1a1a2e; }}
  .metric-label {{ font-size: .8rem; color: #888; margin-top: 4px; }}
  .concern-list {{ margin-top: 10px; padding-left: 20px; }}
  .concern-list li {{ color: #e67e22; margin-bottom: 4px; font-size: .9rem; }}
  .pattern-chip {{ display:inline-block; background:#3498db; color:#fff;
                   padding: 4px 14px; border-radius: 20px; font-size: .85rem;
                   font-weight: 600; margin-bottom: 14px; }}
  footer {{ text-align: center; padding: 24px; color: #aaa; font-size: .8rem; }}
  .project-summary {{ font-size:1rem; color:#444; line-height:1.6; margin-bottom:16px;
                      padding:14px; background:#f0f4ff; border-left:4px solid #3498db; border-radius:4px; }}
  .plan-meta {{ display:flex; gap:24px; margin-bottom:18px; flex-wrap:wrap; }}
  .plan-meta span {{ background:#f8f9fa; padding:6px 14px; border-radius:20px;
                     font-size:.88rem; color:#555; }}
  .phases-row {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }}
  .phase-card {{ flex:1; min-width:180px; background:#1a1a2e; color:#fff;
                 border-radius:10px; padding:16px; }}
  .phase-name {{ font-weight:700; font-size:1rem; margin-bottom:4px; }}
  .phase-dur {{ font-size:.8rem; opacity:.7; margin-bottom:8px; }}
  .phase-goal {{ font-size:.85rem; opacity:.9; margin-bottom:8px; }}
  .phase-tasks {{ font-size:.75rem; opacity:.6; }}
  .task-card {{ border:1px solid #e8e8e8; border-radius:10px; padding:18px;
                margin-bottom:14px; background:#fafafa; }}
  .task-header {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap; }}
  .task-id {{ font-size:.75rem; color:#888; font-family:monospace; }}
  .task-title {{ font-weight:700; font-size:.95rem; flex:1; }}
  .task-effort {{ margin-left:auto; font-size:.85rem; color:#555; font-weight:600; }}
  .task-desc {{ font-size:.88rem; color:#444; margin-bottom:12px; line-height:1.5; }}
  .task-section {{ margin-bottom:10px; }}
  .task-section strong {{ font-size:.82rem; color:#666; display:block; margin-bottom:4px; }}
  .task-section ul {{ padding-left:18px; }}
  .task-section li {{ font-size:.83rem; color:#555; margin-bottom:3px; }}
  .task-meta {{ font-size:.78rem; color:#aaa; margin-top:10px; border-top:1px solid #eee; padding-top:8px; }}
  .public-data-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px,1fr)); gap:16px; margin-top:14px; }}
  .public-data-card {{ background:#f8f9fa; border:1px solid #e8e8e8; border-radius:12px; padding:18px; min-height:160px; }}
  .public-data-card h4 {{ margin-bottom:10px; font-size:1rem; }}
  .public-data-card table {{ width:100%; margin-top:10px; border-collapse: collapse; }}
  .public-data-card th, .public-data-card td {{ padding:8px 10px; border:1px solid #e8e8e8; font-size:.84rem; }}
</style>
</head>
<body>
<header>
  <h1>{_html_escape(project_name)}
    <span class="status-chip">{_html_escape(result.get("status","completed").upper())}</span>
  </h1>
  <div class="meta">
    Project ID: {_html_escape(project_id)} &nbsp;|&nbsp;
    Run ID: {_html_escape(run_id)} &nbsp;|&nbsp;
    Iterations: {result.get("iterations", 0)} &nbsp;|&nbsp;
    Stakeholder Score: {sh_score}/100
  </div>
</header>

<div class="container">

  <!-- COLLABORATION METRICS -->
  <div class="section">
    <h2>Collaboration Metrics</h2>
    <div class="metrics-grid">
      <div class="metric-box">
        <div class="metric-num">{metrics.get("interactions", len(messages))}</div>
        <div class="metric-label">Total Messages</div>
      </div>
      <div class="metric-box">
        <div class="metric-num">{metrics.get("decisions", len(decisions))}</div>
        <div class="metric-label">Decisions Made</div>
      </div>
      <div class="metric-box">
        <div class="metric-num">{metrics.get("feedback_loops", len(feedback_loops))}</div>
        <div class="metric-label">Feedback Loops</div>
      </div>
      <div class="metric-box">
        <div class="metric-num">{result.get("iterations", 0)}</div>
        <div class="metric-label">Exec Iterations</div>
      </div>
      <div class="metric-box">
        <div class="metric-num">{len(risks)}</div>
        <div class="metric-label">Risks Identified</div>
      </div>
    </div>
    <div style="margin-top:16px">
      <span class="pattern-chip">{_html_escape(metrics.get("pattern","collaborative"))}</span>
      {msg_type_pills}
    </div>
  </div>

  <!-- PROJECT PLAN -->
  <div class="section">
    <h2>Project Plan</h2>
    {project_summary_html}
    {plan_meta}
    <h3 style="font-size:1rem;margin:18px 0 10px">Technology Stack</h3>
    {tech_html}
    <h3 style="font-size:1rem;margin:18px 0 10px">Phases</h3>
    {phases_html}
    <h3 style="font-size:1rem;margin:18px 0 10px">Tasks</h3>
    {task_cards_html}
  </div>

  <!-- COMPASS SCORES -->
  <div class="section">
    <h2>Compass Evaluation Scores</h2>
    <div class="scores-grid">{score_cards_html}</div>
    {"<p style='margin-top:14px;color:#666;font-size:.9rem'>" + _html_escape(compass.get("results", {}).get("summary", "")) + "</p>" if compass.get("results", {}).get("summary") else ""}
  </div>

  <!-- PUBLIC DATA ENRICHMENT -->
  <div class="section">
    <h2>Public Data Enrichment</h2>
    {public_data_html}
  </div>

  <!-- SEQUENCE DIAGRAM -->
  <div class="section">
    <h2>Agent Interaction Sequence Diagram</h2>
    <div class="mermaid-wrap">
      <pre class="mermaid">
{mermaid_code}
      </pre>
    </div>
  </div>

  <!-- RISK REGISTER -->
  <div class="section">
    <h2>Risk Register</h2>
    <table>
      <thead>
        <tr><th>Severity</th><th>Title</th><th>Description</th><th>Probability</th></tr>
      </thead>
      <tbody>{risk_rows_html}</tbody>
    </table>
    {"<div style='margin-top:14px'><strong>Stakeholder Concerns:</strong><ul class='concern-list'>" + "".join(f"<li>{_html_escape(c)}</li>" for c in sh_concerns) + "</ul></div>" if sh_concerns else ""}
  </div>

  <!-- AGENT MESSAGE LOG -->
  <div class="section">
    <h2>Agent Message Log</h2>
    {messages_html}
  </div>

  <!-- DECISION TIMELINE -->
  <div class="section">
    <h2>Decision Timeline</h2>
    <div class="timeline">
      {decisions_html}
    </div>
  </div>

  <!-- FEEDBACK LOOPS -->
  <div class="section">
    <h2>QA / Engineer Feedback Loops</h2>
    {fl_html}
  </div>

</div>

<footer>Generated by Multi-Agent PM System &mdash; Run {_html_escape(run_id)}</footer>

<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: "default",
    sequence: {{ actorMargin: 60, messageMargin: 20 }},
  }});
</script>
</body>
</html>"""

    report_path = REPORTS_DIR / f"report_{run_id}.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"[Report] Generated: {report_path}")
    return report_path
