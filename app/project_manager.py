"""Project Manager Agent – plans, coordinates, and replans based on feedback."""
import json
from typing import Any, Dict, List

from base_agent import BaseAgent
from data_types import AgentRole, Project, Task, TaskStatus
from logging_config import log_agent_action
from memory import SharedMemory
from public_data import BLSClient, extract_tech_keywords

_bls = BLSClient()


_PLAN_SYSTEM = """You are a Project Manager AI agent in a multi-agent software delivery system.
Analyse the project description and produce a REAL, detailed project plan.

Return ONLY valid JSON (no markdown fences) in this exact structure:
{
  "project_summary": "2-3 sentence scope statement covering goals, users, and key constraints",
  "technology_stack": {
    "backend": "specific framework and language e.g. FastAPI + Python 3.11",
    "frontend": "specific framework e.g. React 18 + TypeScript or N/A",
    "database": "specific DB e.g. PostgreSQL 15 + Redis for caching",
    "infrastructure": "e.g. Docker + AWS ECS or Azure App Service",
    "key_libraries": ["lib1", "lib2", "lib3"]
  },
  "phases": [
    {
      "id": "phase_1",
      "name": "Phase name",
      "duration_weeks": 2,
      "goal": "What this phase achieves",
      "tasks": ["task_001", "task_002"]
    }
  ],
  "tasks": [
    {
      "id": "task_001",
      "title": "Specific task title",
      "phase": "phase_1",
      "role": "engineer",
      "description": "Detailed description of exactly what must be built or done",
      "acceptance_criteria": [
        "Specific, testable criterion 1",
        "Specific, testable criterion 2"
      ],
      "deliverables": ["Concrete output 1", "Concrete output 2"],
      "dependencies": [],
      "effort_hours": 8,
      "risk_level": "medium"
    }
  ],
  "total_effort_hours": 80,
  "recommended_team_size": 3,
  "priorities": ["task_001", "task_002"],
  "confidence": 0.88,
  "reasoning": "One sentence justifying the plan."
}
Roles allowed: engineer, qa, risk_analyst.
Produce exactly 4-5 tasks across 2 phases. Be specific to the domain — real technologies,
real deliverables, and testable acceptance criteria. Keep each task description under 60 words."""


_REPLAN_SYSTEM = """You are a Project Manager AI agent. You are replanning a project because
risks or concerns have been escalated to you.

Return ONLY valid JSON (no markdown fences):
{
  "adjustments": [
    {"task_id": "task_002", "change": "Reduce scope to MVP", "reason": "Risk of overrun"}
  ],
  "added_tasks": [
    {"id": "task_006", "title": "Risk Mitigation Sprint", "role": "engineer",
     "description": "Address escalated technical risks", "effort_hours": 8}
  ],
  "confidence": 0.82,
  "reasoning": "Brief rationale for the replan."
}"""


class ProjectManagerAgent(BaseAgent):
    """Plans projects, distributes work, and replans on escalation."""

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(AgentRole.PROJECT_MANAGER, memory)
        self.planning_iterations = 0

    async def process_task(self, task: Task, project: Project) -> str:
        title_lower = task.title.lower()
        # Check "replanning" and "escalation" BEFORE "planning" so the longer
        # prefix matches first ("replanning" contains "planning").
        if "replanning" in title_lower or "escalation" in title_lower:
            return await self._run_replanning(task, project)
        if "planning" in title_lower:
            return await self._run_planning(task, project)
        if "approval" in title_lower:
            return await self._handle_approval_task(task, project)
        # Generic fallback
        result = f"PM processed: {task.title}"
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": result})
        return result

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _run_planning(self, task: Task, project: Project) -> str:
        """Call LLM to decompose the project and create tasks."""
        self.log_trace(
            "decompose_project",
            f"Project: {project.name} | {project.description[:100]}",
            "Requesting LLM task breakdown...",
            target_agent="risk_analyst",
            confidence=0.90,
            status="success",
        )

        llm_result = await self.llm_decide(
            _PLAN_SYSTEM,
            f"Project name: {project.name}\nDescription: {project.description}",
            max_tokens=4000,
        )

        tasks_data = llm_result.get("tasks", [])
        confidence = float(llm_result.get("confidence", 0.85))
        reasoning = llm_result.get("reasoning", "Task breakdown complete.")
        tech_stack = llm_result.get("technology_stack", {})
        phases = llm_result.get("phases", [])
        project_summary = llm_result.get("project_summary", "")
        total_effort = int(llm_result.get("total_effort_hours", 0))
        team_size = int(llm_result.get("recommended_team_size", 2))

        # Store rich plan data in project metadata
        project.metadata["technology_stack"] = tech_stack
        project.metadata["phases"] = phases
        project.metadata["project_summary"] = project_summary
        project.metadata["total_effort_hours"] = total_effort
        project.metadata["recommended_team_size"] = team_size
        project.metadata["raw_plan"] = llm_result

        # Create tasks with full rich fields
        role_map = {
            "engineer": AgentRole.ENGINEER,
            "qa": AgentRole.QA,
            "risk_analyst": AgentRole.RISK_ANALYST,
        }
        created = []
        for i, t in enumerate(tasks_data):
            role_str = t.get("role", "engineer")
            new_task = Task(
                id=t.get("id", f"task_{i:03d}"),
                title=t.get("title", f"Task {i}"),
                description=t.get("description", ""),
                assigned_to=role_map.get(role_str, AgentRole.ENGINEER),
                estimated_effort=int(t.get("effort_hours", 8)),
                dependencies=t.get("dependencies", []),
                risk_level=t.get("risk_level", "medium"),
                metadata={
                    "acceptance_criteria": t.get("acceptance_criteria", []),
                    "deliverables": t.get("deliverables", []),
                    "phase": t.get("phase", ""),
                },
            )
            project.tasks.append(new_task)
            created.append(new_task.title)

        self.memory.update_project(project.id, {"tasks": project.tasks, "metadata": project.metadata})

        # --- BLS real public data: team cost estimate ---
        tech_text = project.description + " " + json.dumps(tech_stack)
        tech_kw = extract_tech_keywords(tech_text)
        roles_for_bls = (
            ["engineer"] * max(1, team_size - 1) + ["qa"]
            if team_size > 1 else ["engineer"]
        )
        bls_estimate = _bls.estimate_project_cost(team_size, roles_for_bls)
        project.metadata["bls_cost_estimate"] = bls_estimate
        self.memory.update_project(project.id, {"metadata": project.metadata})

        stack_summary = ", ".join(
            f"{k}: {v}" for k, v in tech_stack.items() if k != "key_libraries" and v
        )
        cost_note = (
            f" Estimated annual team cost: {bls_estimate['estimated_annual_cost_formatted']}"
            f" ({bls_estimate['source']})."
        )
        output_summary = (
            f"Plan: {len(created)} tasks across {len(phases)} phase(s). "
            f"Stack: {stack_summary[:120]}. "
            f"Total effort: {total_effort}h, team size: {team_size}.{cost_note}"
        )

        self.log_trace(
            "delegate_tasks",
            reasoning,
            output_summary,
            target_agent="risk_analyst",
            confidence=confidence,
            status="success",
        )

        self.make_decision("Create project plan", reasoning, project.id)

        # Store full plan for other agents and the report to read
        self.memory.store_summary(
            self.role,
            project.id,
            json.dumps({
                "tasks": created,
                "technology_stack": tech_stack,
                "phases": phases,
                "project_summary": project_summary,
                "total_effort_hours": total_effort,
                "team_size": team_size,
                "reasoning": reasoning,
                "raw_plan": llm_result,
                "bls_cost_estimate": bls_estimate,
            }),
        )

        # Notify agents with meaningful plan context
        self._distribute_tasks(project, tech_stack, total_effort)

        task.status = TaskStatus.COMPLETED
        task.result = output_summary
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output_summary})

        log_agent_action(
            self.logger, self.role.value, "create_task_breakdown",
            {"tasks_created": len(created)}, project.id,
        )
        return output_summary

    def _distribute_tasks(self, project: Project, tech_stack: dict = None, total_effort: int = 0) -> None:
        stack_note = ""
        if tech_stack:
            be = tech_stack.get("backend", "")
            db = tech_stack.get("database", "")
            stack_note = f" Stack: {be}, {db}." if be or db else ""

        engineer_tasks = [t for t in project.tasks if t.assigned_to == AgentRole.ENGINEER]
        qa_tasks = [t for t in project.tasks if t.assigned_to == AgentRole.QA]

        self.send_message(
            AgentRole.RISK_ANALYST,
            f"Project plan ready: {len(project.tasks)} tasks, ~{total_effort}h total effort.{stack_note} "
            f"Please assess delivery risks before implementation begins.",
            "request", project.id,
        )
        self.send_message(
            AgentRole.ENGINEER,
            f"{len(engineer_tasks)} implementation task(s) assigned.{stack_note} "
            f"Await risk clearance before starting.",
            "task_assignment", project.id,
        )
        self.send_message(
            AgentRole.QA,
            f"{len(qa_tasks)} QA task(s) assigned. Prepare test strategy based on acceptance criteria "
            f"once risk assessment completes.",
            "task_assignment", project.id,
        )

    # ------------------------------------------------------------------
    # Replanning
    # ------------------------------------------------------------------

    async def _run_replanning(self, task: Task, project: Project) -> str:
        """Replan based on escalated risks or stakeholder feedback."""
        self.planning_iterations += 1

        # Gather context: risk register + stakeholder concerns
        risk_summary = self.memory.get_summary(AgentRole.RISK_ANALYST, project.id)
        stakeholder_summary = self.memory.get_summary(AgentRole.STAKEHOLDER, project.id)

        context = (
            f"Project: {project.name}\n"
            f"Current tasks: {[t.title for t in project.tasks]}\n"
            f"Risk register: {risk_summary[:300]}\n"
            f"Stakeholder concerns: {stakeholder_summary[:200]}"
        )

        llm_result = await self.llm_decide(_REPLAN_SYSTEM, context)

        adjustments = llm_result.get("adjustments", [])
        added_tasks = llm_result.get("added_tasks", [])
        confidence = float(llm_result.get("confidence", 0.78))
        reasoning = llm_result.get("reasoning", "Replanned based on feedback.")

        # Apply adjustments to existing tasks
        for adj in adjustments:
            for t in project.tasks:
                if t.id == adj.get("task_id"):
                    t.description += f" [ADJUSTED: {adj.get('change')}]"

        # Add new mitigation tasks
        role_map = {"engineer": AgentRole.ENGINEER, "qa": AgentRole.QA, "risk_analyst": AgentRole.RISK_ANALYST}
        for t in added_tasks:
            new_task = Task(
                id=t.get("id", f"replan_task_{self.planning_iterations}"),
                title=t.get("title", "Mitigation Task"),
                description=t.get("description", ""),
                assigned_to=role_map.get(t.get("role", "engineer"), AgentRole.ENGINEER),
                estimated_effort=int(t.get("effort_hours", 8)),
            )
            project.tasks.append(new_task)

        self.memory.update_project(project.id, {"tasks": project.tasks})

        output = f"Replanned: {len(adjustments)} adjustments, {len(added_tasks)} new tasks added."

        self.log_trace(
            "replan_based_on_feedback",
            f"Risks escalated; iteration {self.planning_iterations}",
            output,
            target_agent="engineer",
            confidence=confidence,
            retry_count=self.planning_iterations,
            status="success",
        )
        self.make_decision("Replan project", reasoning, project.id)

        # Notify Engineer of updated plan
        self.send_message(AgentRole.ENGINEER, f"Plan updated after escalation: {output}", "notification", project.id)

        task.status = TaskStatus.COMPLETED
        task.result = output
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": output})
        return output

    # ------------------------------------------------------------------
    # Stakeholder approval handling
    # ------------------------------------------------------------------

    async def _handle_approval_task(self, task: Task, project: Project) -> str:
        result = "Awaiting stakeholder approval"
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": result})
        return result

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def validate_project_readiness(self, project: Project) -> Dict[str, Any]:
        issues = []
        if not project.tasks:
            issues.append("No tasks defined")
        if not project.risks:
            issues.append("No risk assessment completed")

        self.make_decision(
            "Project readiness check",
            f"Found {len(issues)} issues" if issues else "Project is ready to execute",
            project.id,
        )
        return {"is_ready": len(issues) == 0, "issues": issues, "total_tasks": len(project.tasks)}

    def get_next_actions(self, project: Project) -> List[Task]:
        if project.status == "planning":
            return [
                t for t in project.tasks
                if t.assigned_to == AgentRole.PROJECT_MANAGER
                and t.status != TaskStatus.COMPLETED
            ]
        msgs = self.receive_messages()
        if any(m.message_type == "feedback" for m in msgs) and project.status == "in_progress":
            return [Task(
                id="task_replan_auto",
                title="Replanning Based on Feedback",
                description="Replan based on agent escalation",
                assigned_to=AgentRole.PROJECT_MANAGER,
            )]
        return []
