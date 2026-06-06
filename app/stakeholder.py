"""Stakeholder Agent – business perspective, plan approval, progress oversight."""
import json
from typing import Any, Dict, List

from base_agent import BaseAgent
from data_types import AgentRole, Project, Task, TaskStatus
from logging_config import log_agent_action
from memory import SharedMemory


_APPROVE_SYSTEM = """You are a business Stakeholder AI agent in a multi-agent software delivery system.
Review the project plan and decide whether to approve it.

Return ONLY valid JSON (no markdown fences):
{
  "approved": true,
  "satisfaction_score": 78,
  "concerns": ["Any business concerns"],
  "recommendations": ["Any suggestions"],
  "confidence": 0.88,
  "reasoning": "Rationale for the approval decision."
}
Approval requires: tasks are defined, risks have been assessed, and the project scope is clear."""


_PROGRESS_SYSTEM = """You are a business Stakeholder AI agent reviewing project progress.
You receive a progress report and provide business-level feedback.

Return ONLY valid JSON (no markdown fences):
{
  "satisfaction_score": 75,
  "concerns": ["Concern if any"],
  "escalate_to_pm": false,
  "escalation_message": "",
  "recommendations": ["Suggestion"],
  "confidence": 0.85
}"""


class StakeholderAgent(BaseAgent):
    """Provides business perspective and drives escalation when unsatisfied."""

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(AgentRole.STAKEHOLDER, memory)
        self.satisfaction_score: int = 75
        self.concerns: List[str] = []
        self.expectations: Dict[str, Any] = {}

    async def process_task(self, task: Task, project: Project) -> str:
        title_lower = task.title.lower()
        if "approval" in title_lower or "approve" in title_lower:
            return await self._review_and_approve(task, project)
        if "monitor" in title_lower or "progress" in title_lower:
            return await self._monitor_progress(task, project)
        result = f"Stakeholder reviewed: {task.title}"
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": result})
        return result

    # ------------------------------------------------------------------
    # Plan approval
    # ------------------------------------------------------------------

    async def _review_and_approve(self, task: Task, project: Project) -> str:
        """Review the plan (tasks + risks now exist) and approve or reject."""
        pm_plan = self.memory.get_summary(AgentRole.PROJECT_MANAGER, project.id)
        risk_summary = self.memory.get_summary(AgentRole.RISK_ANALYST, project.id)

        context = (
            f"Project: {project.name}\nDescription: {project.description}\n"
            f"Tasks defined: {[t.title for t in project.tasks[:5]]}\n"
            f"Risk register: {risk_summary[:300]}\n"
            f"PM plan: {pm_plan[:200]}"
        )

        self.log_trace(
            "review_project_plan",
            f"Reviewing plan for '{project.name}'",
            "Calling LLM for stakeholder review...",
            target_agent="project_manager",
            confidence=0.88,
            status="success",
        )

        llm_result = await self.llm_decide(_APPROVE_SYSTEM, context)

        approved = bool(llm_result.get("approved", True))
        score = int(llm_result.get("satisfaction_score", 75))
        concerns = llm_result.get("concerns", [])
        recommendations = llm_result.get("recommendations", [])
        confidence = float(llm_result.get("confidence", 0.85))
        reasoning = llm_result.get("reasoning", "Review complete.")

        self.satisfaction_score = score
        self.concerns.extend(concerns)

        output = (
            f"{'APPROVED' if approved else 'REJECTED'} – satisfaction {score}/100. "
            f"Concerns: {'; '.join(concerns) if concerns else 'none'}."
        )

        self.log_trace(
            "approve_plan" if approved else "reject_plan",
            f"Reviewing '{project.name}' ({len(project.tasks)} tasks, {len(project.risks)} risks)",
            output,
            target_agent="project_manager",
            confidence=confidence,
            status="success" if approved else "needs_revision",
        )

        self.make_decision(
            f"{'Approve' if approved else 'Reject'} project plan",
            reasoning,
            project.id,
        )

        # Store for PM to read
        self.memory.store_summary(
            self.role,
            project.id,
            json.dumps({"approved": approved, "score": score, "concerns": concerns}),
        )

        if approved:
            self.send_message(
                AgentRole.PROJECT_MANAGER,
                f"STAKEHOLDER APPROVED. Score: {score}/100. "
                f"Recommendations: {'; '.join(recommendations) if recommendations else 'none'}.",
                "approval",
                project.id,
            )
        else:
            self.send_message(
                AgentRole.PROJECT_MANAGER,
                f"STAKEHOLDER REJECTED. Concerns: {'; '.join(concerns)}. Please revise.",
                "feedback",
                project.id,
            )

        task.status = TaskStatus.COMPLETED
        task.result = output
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output})

        log_agent_action(self.logger, self.role.value, "approve_plan",
                         {"approved": approved, "score": score}, project.id)
        return output

    # ------------------------------------------------------------------
    # Progress monitoring
    # ------------------------------------------------------------------

    async def _monitor_progress(self, task: Task, project: Project) -> str:
        """Review progress and escalate concerns to PM if needed."""
        completed = [t for t in project.tasks if t.status == TaskStatus.COMPLETED]
        total = len(project.tasks)
        progress_pct = (len(completed) / total * 100) if total > 0 else 0

        qa_reports = project.qa_reports
        risk_count = len([r for r in project.risks if r.get("severity") in ("high", "critical")])

        context = (
            f"Project: {project.name}\n"
            f"Progress: {progress_pct:.0f}% ({len(completed)}/{total} tasks done)\n"
            f"QA reports: {len(qa_reports)} ({sum(1 for r in qa_reports if r.get('approved')) } approved)\n"
            f"High/critical risks active: {risk_count}"
        )

        self.log_trace(
            "monitor_progress",
            f"Progress {progress_pct:.0f}%; {len(qa_reports)} QA reports",
            "Calling LLM for stakeholder assessment...",
            target_agent="project_manager",
            confidence=0.85,
            status="success",
        )

        llm_result = await self.llm_decide(_PROGRESS_SYSTEM, context)

        score = int(llm_result.get("satisfaction_score", 70))
        concerns = llm_result.get("concerns", [])
        escalate = bool(llm_result.get("escalate_to_pm", False))
        esc_msg = llm_result.get("escalation_message", "")
        confidence = float(llm_result.get("confidence", 0.82))

        self.satisfaction_score = score
        self.concerns.extend(concerns)

        output = (
            f"Progress check: {progress_pct:.0f}% done; satisfaction {score}/100. "
            f"{'Escalating.' if escalate else 'On track.'}"
        )

        self.log_trace(
            "progress_review",
            f"Progress {progress_pct:.0f}%; {risk_count} high risks",
            output,
            target_agent="project_manager" if escalate else None,
            confidence=confidence,
            status="escalated" if escalate else "success",
        )

        self.make_decision("Monitor progress", output, project.id)

        # Notify PM
        self.send_message(
            AgentRole.PROJECT_MANAGER,
            f"Stakeholder progress update: {progress_pct:.0f}% complete, "
            f"satisfaction {score}/100. {('ESCALATION: ' + esc_msg) if escalate else ''}",
            "escalation" if escalate else "notification",
            project.id,
        )

        if escalate and esc_msg:
            self.log_trace(
                "escalate_concerns",
                f"Satisfaction {score}/100 triggers escalation",
                esc_msg,
                target_agent="project_manager",
                confidence=confidence,
                status="escalated",
            )
            self.escalate_issue(project.id, esc_msg, AgentRole.PROJECT_MANAGER)

        task.status = TaskStatus.COMPLETED
        task.result = output
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output})
        return output

    # ------------------------------------------------------------------
    # Legacy synchronous interface (called by orchestrator)
    # ------------------------------------------------------------------

    def approve_plan(self, project: Project) -> Dict[str, Any]:
        """Sync check used only before async phase is set up; deferred to async version."""
        has_tasks = bool(project.tasks)
        has_risks = bool(project.risks)
        issues = []
        if not has_tasks:
            issues.append("No tasks defined")
        if not has_risks:
            issues.append("No risk assessment")
        return {"approved": len(issues) == 0, "issues": issues}

    def provide_business_feedback(self, project: Project) -> Dict[str, Any]:
        feedback = {
            "satisfaction_score": self.satisfaction_score,
            "status": (
                "green" if self.satisfaction_score > 75
                else "yellow" if self.satisfaction_score > 50
                else "red"
            ),
            "concerns": self.concerns,
            "recommendations": [],
        }
        if "Quality concerns" in self.concerns:
            feedback["recommendations"].append("Increase QA resources")
        if "Progress behind schedule" in self.concerns:
            feedback["recommendations"].append("Adjust scope or timeline")
        return feedback

    def get_next_actions(self, project: Project) -> List[Task]:
        return [Task(
            id="stakeholder_monitor_auto",
            title="Stakeholder Progress Monitoring",
            description="Review project health and provide business feedback",
            assigned_to=AgentRole.STAKEHOLDER,
        )]
