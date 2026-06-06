"""Risk Analyst Agent – identifies risks, monitors execution, escalates critical issues."""
import asyncio
import json
from typing import Any, Dict, List

from base_agent import BaseAgent
from data_types import AgentRole, Project, Task, TaskStatus
from logging_config import log_agent_action
from memory import SharedMemory
from public_data import NISTCVEClient, ONetClient, extract_tech_keywords

_onet = ONetClient()
_nist = NISTCVEClient()


_ASSESS_SYSTEM = """You are a Risk Analyst. Identify the top 3 delivery risks for this project.

Return ONLY valid JSON (no markdown fences):
{
  "risks": [
    {
      "id": "risk_001",
      "title": "Short risk title",
      "description": "One sentence description",
      "probability": "high|medium|low",
      "impact": "high|medium|low",
      "severity": "critical|high|medium|low",
      "affected_tasks": []
    }
  ],
  "high_severity_count": 1,
  "escalate": false,
  "mitigation_recommendations": ["Recommendation 1"],
  "confidence": 0.86,
  "reasoning": "One sentence rationale."
}
Return exactly 3 risks. Escalate only if high_severity_count >= 2."""


class RiskAnalystAgent(BaseAgent):
    """Identifies risks, develops mitigations, and escalates when needed."""

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(AgentRole.RISK_ANALYST, memory)
        self.risk_register: List[Dict[str, Any]] = []
        self.mitigation_strategies: Dict[str, Any] = {}

    async def process_task(self, task: Task, project: Project) -> str:
        title_lower = task.title.lower()
        # Check "monitoring" before "risk" since "Risk Monitoring" contains "risk".
        if "monitoring" in title_lower or "monitor" in title_lower:
            return await self._run_monitoring(task, project)
        if "assessment" in title_lower or "risk" in title_lower:
            return await self._run_assessment(task, project)
        result = f"Risk task completed: {task.title}"
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": result})
        return result

    async def _run_assessment(self, task: Task, project: Project) -> str:
        """LLM-driven initial risk assessment enriched with O*NET workforce data."""
        # Read PM's plan for context
        pm_plan = self.memory.get_summary(AgentRole.PROJECT_MANAGER, project.id)

        # --- O*NET real public data enrichment ---
        combined_text = f"{project.name} {project.description} {pm_plan}"
        tech_keywords = extract_tech_keywords(combined_text)
        onet_context = _onet.format_for_risk_context(tech_keywords) if tech_keywords else ""
        onet_assessment = _onet.assess_tech_stack(tech_keywords) if tech_keywords else {}

        # --- NIST NVD real public data enrichment ---
        cve_result: Dict[str, Any] = {}
        cve_context = ""
        try:
            cve_result = await asyncio.wait_for(
                _nist.check_tech_stack(tech_keywords), timeout=12.0
            )
            cve_context = _nist.format_for_context(cve_result)
        except Exception:
            pass  # network failure is non-fatal

        context = (
            f"Project: {project.name}\n"
            f"Description: {project.description[:200]}\n"
            f"PM plan: {pm_plan[:150]}\n"
            + (f"\n{onet_context}" if onet_context else "")
            + (f"\n{cve_context}" if cve_context else "")
        )

        self.log_trace(
            "assess_risks",
            f"Project: {project.name}",
            "Calling LLM for risk assessment...",
            target_agent="project_manager",
            confidence=0.88,
            status="success",
        )

        llm_result = await self.llm_decide(_ASSESS_SYSTEM, context, max_tokens=800)

        raw_risks = llm_result.get("risks", [])
        # Normalise: LLM sometimes returns strings instead of dicts
        risks: List[Dict[str, Any]] = [
            r if isinstance(r, dict) else {"id": f"risk_{i}", "title": str(r), "description": str(r), "probability": "medium", "impact": "medium", "severity": "medium", "affected_tasks": []}
            for i, r in enumerate(raw_risks if isinstance(raw_risks, list) else [])
        ]
        high_count: int = int(llm_result.get("high_severity_count", 0))
        should_escalate: bool = bool(llm_result.get("escalate", False))
        mitigations: List[str] = llm_result.get("mitigation_recommendations", [])
        confidence: float = float(llm_result.get("confidence", 0.85))
        reasoning: str = llm_result.get("reasoning", "Risk assessment complete.")

        # Use fallback risks if LLM returned nothing
        if not risks:
            risks = [
                {
                    "id": "risk_001",
                    "title": "Resource Availability",
                    "description": "Insufficient skilled resources may delay delivery.",
                    "probability": "medium",
                    "impact": "high",
                    "severity": "high",
                    "affected_tasks": [],
                },
                {
                    "id": "risk_002",
                    "title": "Integration Complexity",
                    "description": "System integration may surface hidden dependencies.",
                    "probability": "medium",
                    "impact": "medium",
                    "severity": "medium",
                    "affected_tasks": [],
                },
            ]
            high_count = 1

        # Inject O*NET-backed resource availability risk if data was found
        if onet_assessment.get("findings"):
            hr_techs = onet_assessment.get("high_risk_technologies", [])
            overall = onet_assessment.get("overall_resource_risk", "medium")
            severity_map = {"high": "high", "medium": "medium", "low": "low"}
            onet_severity = severity_map.get(overall, "medium")
            tech_list = ", ".join(hr_techs) if hr_techs else "key stack technologies"
            onet_risk = {
                "id": "risk_onet_001",
                "title": "Resource Availability (O*NET Data)",
                "description": (
                    f"Based on O*NET 28.3 workforce data: {tech_list} show "
                    f"{overall.upper()} availability risk. "
                    f"{onet_assessment.get('findings', [{}])[0].get('notes', '')} "
                    f"Source: O*NET 28.3 Database, U.S. Dept of Labor."
                ),
                "probability": "high" if overall == "high" else "medium",
                "impact": "high",
                "severity": onet_severity,
                "affected_tasks": [],
                "data_source": "O*NET 28.3 Database (https://www.onetcenter.org/database.html)",
                "technologies_assessed": [f["technology"] for f in onet_assessment["findings"]],
            }
            # Replace generic resource risk if present, otherwise prepend
            risks = [r for r in risks if "resource" not in r.get("title", "").lower()]
            risks.insert(0, onet_risk)
            if onet_severity in ("high", "critical"):
                high_count = max(high_count, 1)

        # Add NIST NVD security risk if CVEs were found
        cves_found = cve_result.get("cves_found", [])
        if cves_found:
            cve_names = ", ".join({c["cve_id"] for c in cves_found[:3]})
            tech_names = ", ".join({c["technology"] for c in cves_found[:3]})
            cve_severity = "high" if any(c["severity"] == "CRITICAL" for c in cves_found) else "medium"
            nist_risk = {
                "id": "risk_nist_cve_001",
                "title": "Known Security Vulnerabilities (NIST NVD)",
                "description": (
                    f"NIST NVD reports {len(cves_found)} HIGH/CRITICAL CVE(s) for stack technologies "
                    f"({tech_names}): {cve_names}. "
                    f"Security review and patch validation required before go-live. "
                    f"Source: NIST National Vulnerability Database (nvd.nist.gov)."
                ),
                "probability": "high",
                "impact": "high",
                "severity": cve_severity,
                "affected_tasks": [],
                "data_source": "NIST National Vulnerability Database REST API 2.0 (https://nvd.nist.gov/)",
                "cves": [c["cve_id"] for c in cves_found[:5]],
            }
            risks = [r for r in risks if "security vulnerabilit" not in r.get("title", "").lower()]
            risks.insert(0, nist_risk)
            if cve_severity == "high":
                high_count = max(high_count, 1)

        self.risk_register = risks
        project.risks = risks
        self.memory.update_project(project.id, {"risks": risks})

        # Build mitigation strategies
        for risk in risks:
            self.mitigation_strategies[risk["id"]] = {
                "strategy": f"Mitigate {risk['title']}",
                "actions": mitigations[:2] if mitigations else ["Monitor and escalate if worsening"],
            }
        project.metadata["mitigation_strategies"] = self.mitigation_strategies
        project.metadata["risk_public_data"] = {
            "onet_assessment": onet_assessment,
            "nist_cve": cve_result,
        }
        self.memory.update_project(project.id, {"metadata": project.metadata})

        output = (
            f"Identified {len(risks)} risks ({high_count} high-severity). "
            f"Escalation needed: {should_escalate}."
        )

        self.log_trace(
            "risk_assessment_complete",
            f"Project: {project.name}",
            output,
            target_agent="project_manager" if should_escalate else "stakeholder",
            confidence=confidence,
            status="escalated" if should_escalate else "success",
        )

        self.make_decision("Risk assessment", reasoning, project.id)

        # Notify stakeholders of high-severity risks
        high_risks = [r for r in risks if isinstance(r, dict) and r.get("severity") in ("high", "critical")]
        if high_risks:
            names = ", ".join(r["title"] for r in high_risks)
            self.send_message(
                AgentRole.STAKEHOLDER,
                f"HIGH-SEVERITY RISKS identified: {names}. Details in risk register.",
                "notification",
                project.id,
            )

        # Escalate to PM if needed
        if should_escalate:
            self.log_trace(
                "escalate_to_pm",
                f"{high_count} high-severity risks require PM intervention",
                "Requesting PM replan based on risk findings",
                target_agent="project_manager",
                confidence=confidence,
                status="escalated",
            )
            self.escalate_issue(
                project.id,
                f"{high_count} high-severity risks: {', '.join(r['title'] for r in high_risks)}",
                AgentRole.PROJECT_MANAGER,
            )

        # Store summary for other agents
        self.memory.store_summary(
            self.role,
            project.id,
            json.dumps({
                "risks": risks,
                "mitigations": mitigations,
                "escalate": should_escalate,
                "onet_assessment": onet_assessment,
                "nist_cve": cve_result,
            }),
        )

        task.status = TaskStatus.COMPLETED
        task.result = output
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output})

        log_agent_action(self.logger, self.role.value, "risk_assessment",
                         {"risks": len(risks), "high_severity": high_count, "escalate": should_escalate},
                         project.id)
        return output

    async def _run_monitoring(self, task: Task, project: Project) -> str:
        """Deterministic risk monitoring — no LLM call for speed."""
        completed_tasks = [t for t in project.tasks if t.status == TaskStatus.COMPLETED]
        total_tasks = len(project.tasks)
        progress = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0

        # Mark all tracked risks as stable unless already escalating
        for risk in self.risk_register:
            if risk.get("status") != "escalating":
                risk["status"] = "stable"

        # Escalate only if progress is severely behind (< 20%) and critical risks exist
        critical = [r for r in self.risk_register if r.get("severity") == "critical"]
        escalate_now = progress < 20 and len(critical) > 0
        escalation_reason = (
            f"{len(critical)} critical risk(s) with low progress ({progress:.0f}%)"
            if escalate_now else ""
        )

        output = (
            f"Monitoring: {progress:.0f}% complete, "
            f"{len(self.risk_register)} risks tracked, "
            f"escalate={escalate_now}."
        )

        self.log_trace(
            "monitor_risks",
            f"Progress {progress:.0f}%; deterministic check",
            output,
            target_agent="project_manager" if escalate_now else None,
            confidence=0.80,
            status="escalated" if escalate_now else "success",
        )

        if escalate_now and escalation_reason:
            self.escalate_issue(project.id, escalation_reason, AgentRole.PROJECT_MANAGER)

        task.status = TaskStatus.COMPLETED
        task.result = output
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output})
        return output

    def escalate_risks(self, project: Project) -> List[Dict[str, Any]]:
        critical = [r for r in self.risk_register if isinstance(r, dict) and r.get("severity") == "critical"]
        for risk in critical:
            self.escalate_issue(
                project.id,
                f"CRITICAL: {risk['title']} – {risk['description']}",
                AgentRole.PROJECT_MANAGER,
            )
        return critical

    def generate_risk_report(self, project: Project) -> Dict[str, Any]:
        severity_counts: Dict[str, int] = {}
        for s in ("critical", "high", "medium", "low"):
            severity_counts[s] = sum(1 for r in self.risk_register if isinstance(r, dict) and r.get("severity") == s)
        return {
            "total_risks": len(self.risk_register),
            "by_severity": severity_counts,
            "mitigated": sum(1 for r in self.risk_register if r.get("status") == "mitigated"),
            "escalated": sum(1 for r in self.risk_register if r.get("status") == "escalating"),
            "risks": self.risk_register,
            "mitigations": self.mitigation_strategies,
        }

    def get_next_actions(self, project: Project) -> List[Task]:
        pending = [
            t for t in self.memory.get_agent_tasks(AgentRole.RISK_ANALYST, project.id)
            if t.status == TaskStatus.PENDING
        ]
        if project.status == "in_progress":
            pending.append(Task(
                id="risk_monitor_auto",
                title="Risk Monitoring",
                description="Monitor risk indicators during execution",
                assigned_to=AgentRole.RISK_ANALYST,
            ))
        return pending
