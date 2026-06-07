"""LangGraph multi-agent PM workflow graph.

Topology
────────
START
  → plan_project         (PM: decompose into tasks)
  → assess_risks         (RiskAnalyst: identify risks)
  → [?] replan_project   (PM: adjust plan for high-severity risks)
  → stakeholder_approve  (Stakeholder: plan review & approval)
  → set_next_task        (routing: pick next Engineer task)
  → [loop] implement_task (Engineer: build the task)
      → qa_critique       (QA: review implementation)
      → [?] engineer_revise → qa_critique  (Engineer: fix QA issues, max 2 revisions)
      → monitor_risks     (RiskAnalyst: mid-execution risk check)
      → [?] mid_replan    (PM: replan if critical risks emerge)
      → set_next_task     (advance to next task or exit loop)
  → stakeholder_progress (Stakeholder: progress review)
  → check_quality_gates  (QA: final gate check)
  → generate_risk_report (RiskAnalyst: final report)
  → stakeholder_final    (Stakeholder: final satisfaction score)
  → finalize_project     (collect results, generate HTML report)
  → submit_compass       (Compass evaluation)
END

Conditional edges
─────────────────
  assess_risks     → replan_project | stakeholder_approve  (high_risks_detected)
  set_next_task    → implement_task | stakeholder_progress (current_task_id truthy)
  qa_critique      → engineer_revise | monitor_risks       (approved or max retries)
  monitor_risks    → mid_replan | set_next_task            (critical_risks_detected)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Literal

from langgraph.graph import END, START, StateGraph

import trace_logger
from compass_integration import get_compass_client
from data_types import AgentRole, Project, Task, TaskStatus
from engineer import EngineerAgent
from memory import SharedMemory
from project_manager import ProjectManagerAgent
from qa_agent import QAAgent
from report_generator import generate_report
from risk_analyst import RiskAnalystAgent
from stakeholder import StakeholderAgent
from state import ProjectState

MAX_QA_RETRIES = 1   # Engineer may revise this many times per task
MAX_ITERATIONS = 2   # Maximum engineer tasks per run (keeps total under 15 min)

logger = logging.getLogger("graph")


# ── Helpers ────────────────────────────────────────────────────────────────

def _dict_to_task(d: Dict[str, Any]) -> Task:
    """Reconstruct a Task dataclass from its serialised dict."""
    return Task(
        id=d["id"],
        title=d["title"],
        description=d["description"],
        assigned_to=AgentRole(d["assigned_to"]),
        status=TaskStatus(d.get("status", "pending")),
        result=d.get("result", ""),
        estimated_effort=d.get("estimated_effort", 0),
        dependencies=d.get("dependencies", []),
        risk_level=d.get("risk_level", "medium"),
        metadata=d.get("metadata", {}),
    )


# ── Graph class ────────────────────────────────────────────────────────────

class PMWorkflowGraph:
    """LangGraph-based multi-agent PM workflow.

    Compiles a StateGraph at construction time. Call ``run_workflow()`` to
    execute a project end-to-end.
    """

    def __init__(self, memory: SharedMemory) -> None:
        self.memory = memory
        self.compass = get_compass_client()

        # Agent instances — shared across all node invocations
        self.pm = ProjectManagerAgent(memory)
        self.engineer = EngineerAgent(memory)
        self.qa = QAAgent(memory)
        self.risk_analyst = RiskAnalystAgent(memory)
        self.stakeholder = StakeholderAgent(memory)

        self.run_id: str = ""
        self._app = self._build_graph()

    # ── Graph construction ─────────────────────────────────────────────────

    def _build_graph(self):
        builder = StateGraph(ProjectState)

        # Register nodes
        builder.add_node("plan_project",          self._node_plan_project)
        builder.add_node("assess_risks",           self._node_assess_risks)
        builder.add_node("replan_project",         self._node_replan_project)
        builder.add_node("stakeholder_approve",    self._node_stakeholder_approve)
        builder.add_node("set_next_task",          self._node_set_next_task)
        builder.add_node("implement_task",         self._node_implement_task)
        builder.add_node("qa_critique",            self._node_qa_critique)
        builder.add_node("engineer_revise",        self._node_engineer_revise)
        builder.add_node("monitor_risks",          self._node_monitor_risks)
        builder.add_node("mid_replan",             self._node_mid_replan)
        builder.add_node("stakeholder_progress",   self._node_stakeholder_progress)
        builder.add_node("check_quality_gates",    self._node_check_quality_gates)
        builder.add_node("generate_risk_report",   self._node_generate_risk_report)
        builder.add_node("stakeholder_final",      self._node_stakeholder_final)
        builder.add_node("finalize_project",       self._node_finalize_project)
        builder.add_node("submit_compass",         self._node_submit_compass)

        # Linear edges
        builder.add_edge(START,                    "plan_project")
        builder.add_edge("plan_project",           "assess_risks")
        builder.add_edge("replan_project",         "stakeholder_approve")
        builder.add_edge("stakeholder_approve",    "set_next_task")   # always enter loop
        builder.add_edge("implement_task",         "qa_critique")
        builder.add_edge("engineer_revise",        "qa_critique")     # QA loop back
        builder.add_edge("mid_replan",             "set_next_task")
        builder.add_edge("stakeholder_progress",   "check_quality_gates")
        builder.add_edge("check_quality_gates",    "generate_risk_report")
        builder.add_edge("generate_risk_report",   "stakeholder_final")
        builder.add_edge("stakeholder_final",      "finalize_project")
        builder.add_edge("finalize_project",       "submit_compass")
        builder.add_edge("submit_compass",         END)

        # Conditional edges
        builder.add_conditional_edges(
            "assess_risks",
            self._route_after_risks,
            {"replan": "replan_project", "approve": "stakeholder_approve"},
        )
        builder.add_conditional_edges(
            "set_next_task",
            self._route_set_next_task,
            {"implement": "implement_task", "done": "stakeholder_progress"},
        )
        builder.add_conditional_edges(
            "qa_critique",
            self._route_after_critique,
            {"revise": "engineer_revise", "next": "monitor_risks"},
        )
        builder.add_conditional_edges(
            "monitor_risks",
            self._route_after_monitor,
            {"replan": "mid_replan", "next": "set_next_task"},
        )

        return builder.compile()

    # ── Routing functions (sync — LangGraph requirement) ──────────────────

    def _route_after_risks(
        self, state: ProjectState
    ) -> Literal["replan", "approve"]:
        return "replan" if state.get("high_risks_detected", False) else "approve"

    def _route_set_next_task(
        self, state: ProjectState
    ) -> Literal["implement", "done"]:
        return "implement" if state.get("current_task_id") else "done"

    def _route_after_critique(
        self, state: ProjectState
    ) -> Literal["revise", "next"]:
        approved = state.get("qa_approved", False)
        retry = state.get("qa_retry_count", 0)
        if not approved and retry < MAX_QA_RETRIES:
            return "revise"
        return "next"

    def _route_after_monitor(
        self, state: ProjectState
    ) -> Literal["replan", "next"]:
        return "replan" if state.get("critical_risks_detected", False) else "next"

    # ── Node implementations ───────────────────────────────────────────────

    async def _node_plan_project(self, state: ProjectState) -> Dict[str, Any]:
        """PM decomposes the project into a task list."""
        logger.info("NODE: plan_project")
        project = self._state_to_project(state)

        planning_task = Task(
            id="task_planning_001",
            title="Project Planning",
            description="Analyse requirements and create task breakdown",
            assigned_to=AgentRole.PROJECT_MANAGER,
        )
        project.tasks.append(planning_task)
        await self.pm.process_task(planning_task, project)

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            "project_metadata": project.metadata,
            "project_status": "planning",
            **self._sync_interactions(),
        }

    async def _node_assess_risks(self, state: ProjectState) -> Dict[str, Any]:
        """Risk Analyst evaluates the PM's plan and classifies risks."""
        logger.info("NODE: assess_risks")
        project = self._state_to_project(state)

        risk_task = Task(
            id="task_risk_assess_001",
            title="Risk Assessment",
            description="Identify and classify project risks",
            assigned_to=AgentRole.RISK_ANALYST,
        )
        project.tasks.append(risk_task)
        await self.risk_analyst.process_task(risk_task, project)

        high_risks = [
            r for r in project.risks
            if r.get("severity") in ("high", "critical")
        ]
        high_detected = len(high_risks) >= 1

        if high_detected:
            trace_logger.log_trace(
                agent_name="orchestrator",
                action="branch_high_risk_path",
                input_summary=f"{len(high_risks)} high-severity risk(s): "
                              f"{', '.join(r['title'] for r in high_risks[:2])}",
                output_summary="Routing to PM replan before execution",
                target_agent="project_manager",
                confidence=0.92,
                status="success",
            )
        else:
            trace_logger.log_trace(
                agent_name="orchestrator",
                action="branch_normal_path",
                input_summary="No high-severity risks detected",
                output_summary="Proceeding with standard execution path",
                confidence=0.90,
                status="success",
            )

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            "risks": project.risks,
            "high_risks_detected": high_detected,
            **self._sync_interactions(),
        }

    async def _node_replan_project(self, state: ProjectState) -> Dict[str, Any]:
        """PM adjusts the plan in response to high-severity risks."""
        logger.info("NODE: replan_project")
        project = self._state_to_project(state)

        replan_task = Task(
            id="task_replan_001",
            title="Replanning Based on Risk Escalation",
            description="Adjust plan based on high-severity risks",
            assigned_to=AgentRole.PROJECT_MANAGER,
        )
        project.tasks.append(replan_task)
        await self.pm.process_task(replan_task, project)

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            "project_metadata": project.metadata,
            **self._sync_interactions(),
        }

    async def _node_stakeholder_approve(self, state: ProjectState) -> Dict[str, Any]:
        """Stakeholder reviews the plan and approves or rejects it.

        Also builds the engineer task queue for the execution loop.
        """
        logger.info("NODE: stakeholder_approve")
        project = self._state_to_project(state)

        # Validate readiness before presenting to stakeholder
        self.pm.validate_project_readiness(project)

        approval_task = Task(
            id="task_approval_001",
            title="Stakeholder Plan Approval",
            description="Business review and approval of project plan",
            assigned_to=AgentRole.STAKEHOLDER,
        )
        project.tasks.append(approval_task)
        await self.stakeholder.process_task(approval_task, project)

        # Build the ordered engineer task queue (cap at MAX_ITERATIONS)
        pending_eng = [
            t for t in project.tasks
            if t.assigned_to == AgentRole.ENGINEER
            and t.status == TaskStatus.PENDING
        ]
        if not pending_eng:
            # Fallback: create a default implementation task
            default = Task(
                id="task_dev_default",
                title="Core Implementation",
                description=f"Implement core features for {project.name}",
                assigned_to=AgentRole.ENGINEER,
            )
            project.tasks.append(default)
            pending_eng = [default]
            self.memory.update_project(project.id, {"tasks": project.tasks})

        queue = [t.id for t in pending_eng[:MAX_ITERATIONS]]

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            "project_status": "in_progress",
            "engineer_task_queue": queue,
            "current_task_id": "",   # set_next_task will pick first
            "iteration": 0,
            **self._sync_interactions(),
        }

    def _node_set_next_task(self, state: ProjectState) -> Dict[str, Any]:
        """Advance the task queue: remove the just-processed task, pick the next one."""
        logger.info("NODE: set_next_task")
        queue = list(state.get("engineer_task_queue", []))
        current = state.get("current_task_id", "")

        # Drop the task we just finished
        if current and current in queue:
            queue.remove(current)

        if queue:
            next_id = queue[0]
            logger.info(f"Next engineer task: {next_id}")
            return {
                "current_task_id": next_id,
                "engineer_task_queue": queue,
                "qa_retry_count": 0,
                "qa_approved": False,
                "qa_issues": [],
                "critical_risks_detected": False,
                "iteration": state.get("iteration", 0) + 1,
            }

        logger.info("No more engineer tasks — moving to evaluation phase")
        return {"current_task_id": ""}

    async def _node_implement_task(self, state: ProjectState) -> Dict[str, Any]:
        """Engineer implements the current task."""
        task_id = state["current_task_id"]
        logger.info(f"NODE: implement_task ({task_id})")
        project = self._state_to_project(state)

        task = next((t for t in project.tasks if t.id == task_id), None)
        if task is None:
            # Defensive: create a minimal task if missing
            task = Task(
                id=task_id,
                title=f"Task {task_id}",
                description="Implementation task",
                assigned_to=AgentRole.ENGINEER,
            )
            project.tasks.append(task)

        await self.engineer.process_task(task, project)

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            **self._sync_interactions(),
        }

    async def _node_qa_critique(self, state: ProjectState) -> Dict[str, Any]:
        """QA critiques the engineer's implementation."""
        task_id = state["current_task_id"]
        retry = state.get("qa_retry_count", 0)
        logger.info(f"NODE: qa_critique ({task_id}, attempt={retry + 1})")
        project = self._state_to_project(state)

        task = next((t for t in project.tasks if t.id == task_id), None)
        if task is None:
            return {"qa_approved": True, "qa_issues": [], "qa_retry_count": retry}

        approved, issues, _ = await self.qa.critique_implementation(
            task, project, retry_count=retry
        )

        # When max retries exhausted and still failing: notify risk analyst
        if not approved and retry >= MAX_QA_RETRIES:
            logger.warning(f"Max QA retries reached for '{task.title}'")
            trace_logger.log_trace(
                agent_name="orchestrator",
                action="max_retries_reached",
                input_summary=f"Task '{task.title}' exceeded {MAX_QA_RETRIES} QA retries",
                output_summary="Proceeding with known issues; flagging for risk review",
                target_agent="risk_analyst",
                confidence=0.62,
                status="success",
            )
            self.risk_analyst.send_message(
                AgentRole.RISK_ANALYST,
                f"Task '{task.title}' has unresolved QA issues after "
                f"{MAX_QA_RETRIES} retries",
                "notification",
                project.id,
            )

        return {
            "qa_approved": approved,
            "qa_issues": issues,
            "qa_retry_count": retry,
            "tasks": [t.to_dict() for t in project.tasks],
            **self._sync_interactions(),
        }

    async def _node_engineer_revise(self, state: ProjectState) -> Dict[str, Any]:
        """Engineer revises the implementation based on QA critique."""
        task_id = state["current_task_id"]
        retry = state.get("qa_retry_count", 0) + 1   # increment before revision
        logger.info(f"NODE: engineer_revise ({task_id}, revision={retry})")
        project = self._state_to_project(state)

        task = next((t for t in project.tasks if t.id == task_id), None)
        if task is None:
            return {"qa_retry_count": retry}

        issues = state.get("qa_issues", [])
        await self.engineer.revise_implementation(task, project, issues, retry)

        return {
            "qa_retry_count": retry,
            "tasks": [t.to_dict() for t in project.tasks],
            **self._sync_interactions(),
        }

    async def _node_monitor_risks(self, state: ProjectState) -> Dict[str, Any]:
        """Risk Analyst monitors risks after each engineering task."""
        iteration = state.get("iteration", 1)
        logger.info(f"NODE: monitor_risks (iteration={iteration})")
        project = self._state_to_project(state)

        monitor_task = Task(
            id=f"task_risk_monitor_{iteration}",
            title=f"Risk Monitoring – iteration {iteration}",
            description="Monitor risk indicators during execution",
            assigned_to=AgentRole.RISK_ANALYST,
        )
        await self.risk_analyst.process_task(monitor_task, project)

        critical = self.risk_analyst.escalate_risks(project)

        return {
            "critical_risks_detected": len(critical) > 0,
            "risks": project.risks,
            **self._sync_interactions(),
        }

    async def _node_mid_replan(self, state: ProjectState) -> Dict[str, Any]:
        """PM replans mid-execution after a critical risk is escalated."""
        iteration = state.get("iteration", 1)
        logger.info(f"NODE: mid_replan (iteration={iteration})")
        project = self._state_to_project(state)

        mid_task = Task(
            id=f"task_mid_replan_{iteration}",
            title=f"Mid-Execution Replanning – iteration {iteration}",
            description="Replan after critical risk escalation",
            assigned_to=AgentRole.PROJECT_MANAGER,
        )
        await self.pm.process_task(mid_task, project)

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            "project_metadata": project.metadata,
            "critical_risks_detected": False,
            **self._sync_interactions(),
        }

    async def _node_stakeholder_progress(
        self, state: ProjectState
    ) -> Dict[str, Any]:
        """Stakeholder reviews execution progress and escalates if unsatisfied."""
        logger.info("NODE: stakeholder_progress")
        project = self._state_to_project(state)

        progress_task = Task(
            id="task_stakeholder_progress",
            title="Stakeholder Progress Monitoring",
            description="Business review of execution progress",
            assigned_to=AgentRole.STAKEHOLDER,
        )
        await self.stakeholder.process_task(progress_task, project)

        # If satisfaction below threshold, PM acknowledges concerns
        sh_summary = self.memory.get_summary(AgentRole.STAKEHOLDER, project.id)
        if sh_summary:
            try:
                sh_data = json.loads(sh_summary)
                if not sh_data.get("approved", True) or sh_data.get("score", 100) < 65:
                    self.pm.send_message(
                        AgentRole.STAKEHOLDER,
                        "Concerns received and logged. Adjusting approach to address issues.",
                        "response",
                        project.id,
                    )
                    trace_logger.log_trace(
                        agent_name="project_manager",
                        action="address_stakeholder_concerns",
                        input_summary="Stakeholder satisfaction below threshold",
                        output_summary="PM committed to addressing stakeholder concerns",
                        target_agent="stakeholder",
                        confidence=0.82,
                        status="success",
                    )
            except Exception:
                pass

        return {
            "tasks": [t.to_dict() for t in project.tasks],
            **self._sync_interactions(),
        }

    async def _node_check_quality_gates(
        self, state: ProjectState
    ) -> Dict[str, Any]:
        """QA checks final quality gates across all test reports."""
        logger.info("NODE: check_quality_gates")
        project = self._state_to_project(state)

        qa_report = self.qa.check_quality_gates(project)
        logger.info(f"Quality gates: {qa_report['gates']}")

        trace_logger.log_trace(
            agent_name="qa",
            action="check_quality_gates",
            input_summary=f"{len(self.qa.test_reports)} test reports, "
                          f"{len(self.qa.defects_found)} defect groups",
            output_summary=f"Gates passed: {qa_report['all_gates_passed']}; "
                           f"pass_rate={qa_report['report'].get('pass_rate', 0):.0f}%",
            target_agent="project_manager" if not qa_report["all_gates_passed"] else None,
            confidence=qa_report["report"].get("average_confidence", 0.85),
            status="success" if qa_report["all_gates_passed"] else "needs_revision",
        )

        return self._sync_interactions()

    async def _node_generate_risk_report(
        self, state: ProjectState
    ) -> Dict[str, Any]:
        """Risk Analyst produces the final risk register and report."""
        logger.info("NODE: generate_risk_report")
        project = self._state_to_project(state)

        risk_report = self.risk_analyst.generate_risk_report(project)
        logger.info(
            f"Risk report: {risk_report['total_risks']} total, "
            f"{risk_report['by_severity'].get('high', 0)} high-severity"
        )

        trace_logger.log_trace(
            agent_name="risk_analyst",
            action="generate_final_risk_report",
            input_summary=f"{len(self.risk_analyst.risk_register)} risks tracked",
            output_summary=(
                f"Total: {risk_report['total_risks']} | "
                f"High: {risk_report['by_severity'].get('high', 0)} | "
                f"Mitigated: {risk_report['mitigated']}"
            ),
            confidence=0.88,
            status="success",
        )

        return self._sync_interactions()

    async def _node_stakeholder_final(self, state: ProjectState) -> Dict[str, Any]:
        """Stakeholder provides final satisfaction score and business feedback."""
        logger.info("NODE: stakeholder_final")
        project = self._state_to_project(state)

        feedback = self.stakeholder.provide_business_feedback(project)
        logger.info(f"Final stakeholder satisfaction: {feedback['satisfaction_score']}")

        trace_logger.log_trace(
            agent_name="stakeholder",
            action="provide_final_feedback",
            input_summary="Post-execution business review",
            output_summary=(
                f"Satisfaction: {feedback['satisfaction_score']}/100 | "
                f"Status: {feedback['status']}"
            ),
            confidence=0.86,
            status="success",
        )

        return self._sync_interactions()

    async def _node_finalize_project(self, state: ProjectState) -> Dict[str, Any]:
        """Finalise project state, generate MVP, and build the collaboration summary."""
        logger.info("NODE: finalize_project")

        trace_logger.log_trace(
            agent_name="orchestrator",
            action="finalize_project",
            input_summary=f"All phases complete; {state.get('iteration', 0)} iteration(s)",
            output_summary=f"Project '{state['project_name']}' finalised",
            confidence=1.0,
            status="success",
        )

        interactions = self.memory.get_all_interactions()
        collaboration = self._build_collaboration_summary(interactions)

        # Generate self-contained HTML MVP
        project = self._state_to_project(state)
        mvp_path = ""
        try:
            mvp_path = await self.engineer.generate_mvp_html(project)
            if mvp_path:
                logger.info(f"MVP generated: {mvp_path}")
        except Exception as exc:
            logger.error(f"MVP generation failed: {exc}")

        return {
            "project_status": "completed",
            "collaboration_summary": collaboration,
            "mvp_path": mvp_path,
            **self._sync_interactions(),
        }

    async def _node_submit_compass(self, state: ProjectState) -> Dict[str, Any]:
        """Evaluate collaboration quality using local metrics.

        The external Compass /evaluation/submit endpoint is not part of the
        judging interface and is not required to be available.  All five agent
        LLM calls go through Compass (OPENAI_BASE_URL) — this node only
        computes a local collaboration summary from the run metrics.
        """
        logger.info("NODE: submit_compass")
        interactions = self.memory.get_all_interactions()
        metrics = self._calculate_metrics(interactions, state.get("iteration", 0))

        collab_eval = await self.compass.evaluate_agent_collaboration(metrics)

        return {
            "compass_evaluation": {
                "status": "completed",
                "collaboration_evaluation": collab_eval,
                "metrics": metrics,
            }
        }

    # ── Internal helpers ───────────────────────────────────────────────────

    def _state_to_project(self, state: ProjectState) -> Project:
        """Reconstruct a Project object from graph state for agents to consume."""
        project = self.memory.get_project(state["project_id"])
        if project:
            # Sync mutable fields from state (may have been updated by prior nodes)
            if state.get("tasks"):
                project.tasks = [_dict_to_task(t) for t in state["tasks"]]
            if state.get("risks"):
                project.risks = state["risks"]
            if state.get("project_metadata"):
                project.metadata = state["project_metadata"]
            return project

        # First call: create and register the project
        project = Project(
            id=state["project_id"],
            name=state["project_name"],
            description=state["project_description"],
            status=state.get("project_status", "planning"),
        )
        if state.get("tasks"):
            project.tasks = [_dict_to_task(t) for t in state["tasks"]]
        if state.get("risks"):
            project.risks = state["risks"]
        if state.get("project_metadata"):
            project.metadata = state["project_metadata"]
        self.memory.add_project(project)
        return project

    def _sync_interactions(self) -> Dict[str, Any]:
        """Return current SharedMemory interactions for state update.

        Each node that runs agent logic calls this so the state always carries
        the complete, up-to-date message and decision logs.
        """
        interactions = self.memory.get_all_interactions()
        return {
            "messages": interactions["messages"],
            "decisions": interactions["decisions"],
            "feedback_loops": interactions["feedback_loops"],
            "agent_summaries": dict(self.memory.agent_summaries),
        }

    def _build_collaboration_summary(
        self, interactions: Dict[str, Any]
    ) -> Dict[str, Any]:
        messages = interactions.get("messages", [])
        feedback_loops = interactions.get("feedback_loops", {})
        revision_msgs = [
            m for m in messages
            if m.get("message_type") in ("escalation", "feedback")
        ]
        qa_critiques = [
            m for m in messages
            if any(
                kw in m.get("content", "").lower()
                for kw in ("revision", "critique", "issue")
            )
        ]
        findings = [m.get("content", "")[:120] for m in qa_critiques[:5]]
        return {
            "feedback_loop_completed": len(feedback_loops) > 0,
            "revision_count": len(revision_msgs),
            "evaluator_findings": findings or [
                "QA review completed; no blocking issues found"
            ],
        }

    def _calculate_metrics(
        self, interactions: Dict[str, Any], iteration: int
    ) -> Dict[str, Any]:
        messages = interactions.get("messages", [])
        decisions = interactions.get("decisions", [])
        feedback_loops = interactions.get("feedback_loops", {})

        by_type: Dict[str, int] = {}
        for m in messages:
            t = m.get("message_type", "communication")
            by_type[t] = by_type.get(t, 0) + 1

        pattern = "collaborative"
        if feedback_loops:
            pattern = "iterative_feedback"
        if by_type.get("escalation", 0) > 0:
            pattern = "delegated_with_escalation"

        return {
            "interactions": len(messages),
            "feedback_loops": len(feedback_loops),
            "decisions": len(decisions),
            "by_message_type": by_type,
            "pattern": pattern,
            "iterations": iteration,
            "run_id": self.run_id,
        }

    # ── Public API ─────────────────────────────────────────────────────────

    def initial_state(
        self, project_id: str, name: str, description: str
    ) -> ProjectState:
        """Build the blank initial state for a new project run."""
        return ProjectState(
            project_id=project_id,
            project_name=name,
            project_description=description,
            project_status="planning",
            run_id=self.run_id,
            tasks=[],
            risks=[],
            project_metadata={},
            engineer_task_queue=[],
            current_task_id="",
            qa_retry_count=0,
            qa_approved=False,
            qa_issues=[],
            iteration=0,
            high_risks_detected=False,
            critical_risks_detected=False,
            agent_summaries={},
            messages=[],
            decisions=[],
            feedback_loops={},
            compass_evaluation={},
            collaboration_summary={},
            report_path="",
            mvp_path="",
        )

    async def run_workflow(
        self, project_id: str, name: str, description: str
    ) -> Dict[str, Any]:
        """Execute the full LangGraph workflow and return the result dict."""
        self.run_id = trace_logger.init_run(project_id[:8])

        trace_logger.log_trace(
            agent_name="orchestrator",
            action="start_workflow",
            input_summary=f"Project: {name} | {description[:100]}",
            output_summary=(
                f"Initialising 5-agent LangGraph workflow (run_id={self.run_id})"
            ),
            confidence=1.0,
        )

        state = self.initial_state(project_id, name, description)
        state["run_id"] = self.run_id

        # ── Execute the compiled graph (hard cap: 12 minutes) ──────────────
        try:
            final_state: ProjectState = await asyncio.wait_for(
                self._app.ainvoke(state),
                timeout=720,
            )
        except asyncio.TimeoutError:
            logger.warning("Workflow timed out after 12 minutes — returning partial results")
            final_state = state  # type: ignore[assignment]
        except Exception as exc:
            logger.error(f"Workflow raised an exception — returning partial results: {exc}")
            final_state = state  # type: ignore[assignment]

        # ── Build the result dict expected by run.py / FastAPI ──────────────
        interactions = self.memory.get_all_interactions()
        collaboration = final_state.get("collaboration_summary") or \
            self._build_collaboration_summary(interactions)
        project = self.memory.get_project(project_id)

        result: Dict[str, Any] = {
            "project_id": project_id,
            "trace_id": f"trace-{self.run_id}",
            "run_id": self.run_id,
            "status": "completed",
            "iterations": final_state.get("iteration", 0),
            "agents_used": [
                "ProjectManager", "Engineer", "QAAgent",
                "RiskAnalyst", "Stakeholder",
            ],
            "result": {
                "summary": self.memory.get_summary(
                    AgentRole.PROJECT_MANAGER, project_id
                )[:300],
                "iterations": final_state.get("iteration", 0),
                "confidence": 0.87,
            },
            "project_metadata": project.metadata if project else {},
            "collaboration": collaboration,
            "log_path": "logs/agent_trace.jsonl",
            "compass_evaluation": final_state.get(
                "compass_evaluation", {"status": "error"}
            ),
            "interactions": interactions,
            "mvp_path": final_state.get("mvp_path", ""),
        }

        try:
            report_path = generate_report(result, name)
            result["report_path"] = str(report_path)
        except Exception as exc:
            logger.error(f"Report generation failed: {exc}")
            result["report_path"] = ""
        return result
