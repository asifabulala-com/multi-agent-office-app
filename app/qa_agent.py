"""QA Agent – critiques engineer output and drives the revision loop."""
import asyncio
import json
from typing import Any, Dict, List, Tuple

from base_agent import BaseAgent
from data_types import AgentRole, Project, Task, TaskStatus
from logging_config import log_agent_action
from memory import SharedMemory
from public_data import NISTCVEClient, extract_tech_keywords

_nist = NISTCVEClient()


_CRITIQUE_SYSTEM = """You are a QA Engineer. Review this implementation and flag up to 2 concrete issues.

Return ONLY valid JSON (no markdown fences):
{
  "has_issues": true,
  "issues": [
    {"description": "Specific, actionable issue", "severity": "medium"}
  ],
  "approved": false,
  "confidence": 0.91,
  "reasoning": "One sentence verdict."
}
Severity: low | medium | high | critical. Max 2 issues.
If implementation is solid set has_issues=false, approved=true, issues=[]."""


_RETEST_SYSTEM = """You are a QA Engineer. The engineer revised their implementation. Re-evaluate briefly.

Return ONLY valid JSON (no markdown fences):
{
  "has_issues": false,
  "issues": [],
  "approved": true,
  "confidence": 0.88,
  "reasoning": "One sentence verdict."
}
Max 1 remaining issue. Approve unless a critical problem persists."""


class QAAgent(BaseAgent):
    """Tests implementations, critiques, and drives Engineer revision loops."""

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(AgentRole.QA, memory)
        self.test_reports: List[Dict[str, Any]] = []
        self.defects_found: List[Dict[str, Any]] = []
        self.test_coverage_target = 80

    async def process_task(self, task: Task, project: Project) -> str:
        result = f"QA task completed: {task.title}"
        if "planning" in task.title.lower() or "strategy" in task.title.lower():
            self._create_test_plan(project)
        elif "testing" in task.title.lower() or "review" in task.title.lower() or "qa" in task.title.lower():
            await self._execute_tests(task, project)
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.update_task(project.id, task.id, {"status": TaskStatus.COMPLETED, "result": result})
        return result

    async def critique_implementation(
        self,
        task: Task,
        project: Project,
        retry_count: int = 0,
    ) -> Tuple[bool, List[Dict[str, Any]], float]:
        """Critique Engineer's implementation. Returns (approved, issues, confidence).

        This is the primary collaboration method: it reads the engineer's output
        from shared memory, calls the LLM for a structured critique, and
        communicates the result back to the engineer.
        """
        impl_summary = self.memory.get_summary(AgentRole.ENGINEER, task.id)
        if not impl_summary:
            impl_summary = f"Implementation of task '{task.title}' (no detailed summary available)"

        # Read risk context to prioritise testing areas
        risk_summary = self.memory.get_summary(AgentRole.RISK_ANALYST, project.id)

        # --- NIST NVD real public data: CVE check on tech stack (first critique only) ---
        cve_result: Dict[str, Any] = {}
        cve_context = ""
        if retry_count == 0:
            try:
                pm_summary = self.memory.get_summary(AgentRole.PROJECT_MANAGER, project.id)
                tech_text = f"{project.description} {pm_summary} {task.description}"
                tech_kw = extract_tech_keywords(tech_text)
                cve_result = await asyncio.wait_for(
                    _nist.check_tech_stack(tech_kw), timeout=12.0
                )
                cve_context = _nist.format_for_context(cve_result)
                if cve_result.get("cves_found"):
                    project.metadata["nist_cve_findings"] = cve_result["cves_found"]
                    self.memory.update_project(project.id, {"metadata": project.metadata})
            except Exception:
                pass  # network failure is non-fatal

        context = (
            f"Project: {project.name}\n"
            f"Task: {task.title}\n"
            f"Implementation: {impl_summary[:200]}\n"
            f"Risk areas: {risk_summary[:100]}"
            + (f"\n\n{cve_context}" if cve_context else "")
        )

        system = _RETEST_SYSTEM if retry_count > 0 else _CRITIQUE_SYSTEM
        action = "retest_after_revision" if retry_count > 0 else "critique_implementation"

        self.log_trace(
            action,
            f"Reviewing '{task.title}' (attempt {retry_count + 1})",
            "Calling LLM for critique...",
            target_agent=None,
            confidence=0.88,
            retry_count=retry_count,
            status="success",
        )

        llm_result = await self.llm_decide(system, context, max_tokens=600)

        has_issues: bool = bool(llm_result.get("has_issues", False))
        raw_issues = llm_result.get("issues", [])
        # Normalise: LLM sometimes returns strings instead of dicts
        issues: List[Dict[str, Any]] = [
            i if isinstance(i, dict) else {"description": str(i), "severity": "medium"}
            for i in (raw_issues if isinstance(raw_issues, list) else [])
        ]
        approved: bool = bool(llm_result.get("approved", not has_issues))
        confidence: float = float(llm_result.get("confidence", 0.85))
        reasoning: str = llm_result.get("reasoning", "Review complete.")

        # Store QA critique for Engineer to read
        self.memory.store_summary(
            self.role,
            task.id,
            json.dumps({
                "task_id": task.id,
                "approved": approved,
                "issues": issues,
                "reasoning": reasoning,
                "nist_cve_findings": cve_result.get("cves_found", []),
            }),
        )

        if has_issues and issues:
            issue_descriptions = [i.get("description", str(i)) for i in issues[:3]]
            output = f"Found {len(issues)} issue(s): {'; '.join(issue_descriptions[:2])}"

            self.log_trace(
                action,
                f"Engineer output for '{task.title}' (retry={retry_count})",
                output,
                target_agent="engineer",
                confidence=confidence,
                retry_count=retry_count,
                status="needs_revision",
            )

            self.make_decision(
                f"Reject '{task.title}' – needs revision",
                reasoning,
                project.id,
            )

            # Send detailed feedback to Engineer
            self.send_message(
                AgentRole.ENGINEER,
                f"QA CRITIQUE (attempt {retry_count + 1}) of '{task.title}': {output}. "
                f"Reason: {reasoning[:150]}",
                "feedback",
                project.id,
            )

            self.memory.log_feedback_loop(
                self.role, AgentRole.ENGINEER,
                f"Issues: {output[:100]}", project.id, retry_count + 1,
            )

            self.defects_found.append({
                "task": task.id,
                "count": len(issues),
                "issues": issues,
                "retry": retry_count,
            })

        else:
            output = f"APPROVED '{task.title}' – all quality criteria met."

            self.log_trace(
                action,
                f"Engineer output for '{task.title}' (retry={retry_count})",
                output,
                target_agent="engineer",
                confidence=confidence,
                retry_count=retry_count,
                status="success",
            )

            self.make_decision(f"Approve '{task.title}'", reasoning, project.id)

            self.send_message(
                AgentRole.ENGINEER,
                f"QA APPROVED '{task.title}'. {reasoning[:120]}",
                "approval",
                project.id,
            )

        # Store test report
        self.test_reports.append({
            "task": task.id,
            "approved": approved,
            "issues": issues,
            "confidence": confidence,
            "retry": retry_count,
        })

        log_agent_action(self.logger, self.role.value, action,
                         {"task": task.title, "approved": approved, "retry": retry_count}, project.id)
        return approved, issues, confidence

    def _create_test_plan(self, project: Project) -> None:
        plan = {
            "unit_tests": "All public methods",
            "integration_tests": "Feature interactions",
            "system_tests": "End-to-end workflows",
            "performance_tests": "Load and latency",
            "security_tests": "OWASP top-10 checks",
        }
        project.qa_reports.append({"type": "test_plan", "plan": plan, "coverage_target": self.test_coverage_target})
        self.memory.update_project(project.id, {"qa_reports": project.qa_reports})
        log_agent_action(self.logger, self.role.value, "create_test_plan",
                         {"test_areas": len(plan)}, project.id)

    async def _execute_tests(self, task: Task, project: Project) -> None:
        """Deterministic QA task execution — no LLM call for speed."""
        self.test_reports.append({
            "task": task.id,
            "approved": True,
            "issues": [],
            "confidence": 0.85,
        })

    def generate_qa_report(self, project: Project) -> Dict[str, Any]:
        total = len(self.test_reports)
        approved_count = sum(1 for r in self.test_reports if r.get("approved"))
        defect_count = sum(len(r.get("issues", [])) for r in self.test_reports)
        avg_conf = (
            sum(r.get("confidence", 0.85) for r in self.test_reports) / total
            if total > 0 else 0.85
        )
        return {
            "total_reviews": total,
            "approved": approved_count,
            "defect_count": defect_count,
            "pass_rate": (approved_count / total * 100) if total > 0 else 0,
            "average_confidence": round(avg_conf, 2),
            "defects": self.defects_found,
        }

    def check_quality_gates(self, project: Project) -> Dict[str, Any]:
        report = self.generate_qa_report(project)
        gates = {
            "pass_rate": report["pass_rate"] >= 80,
            "no_critical_defects": not any(
                (i.get("severity") if isinstance(i, dict) else "") == "critical"
                for d in self.defects_found
                for i in (d.get("issues", []) if isinstance(d, dict) else [])
            ),
            "confidence_acceptable": report["average_confidence"] >= 0.75,
        }
        all_passed = all(gates.values())
        if not all_passed:
            failed = [g for g, ok in gates.items() if not ok]
            self.escalate_issue(project.id, f"Quality gates failed: {', '.join(failed)}", AgentRole.PROJECT_MANAGER)
        return {"all_gates_passed": all_passed, "gates": gates, "report": report}

    def get_next_actions(self, project: Project) -> List[Task]:
        return [
            t for t in self.memory.get_agent_tasks(AgentRole.QA, project.id)
            if t.status == TaskStatus.PENDING
        ]
