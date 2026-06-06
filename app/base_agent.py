"""Base agent class – all agents inherit from this."""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import trace_logger
from compass_integration import get_compass_client
from data_types import AgentRole, Message, Project, Task, TaskStatus
from logging_config import get_agent_logger, log_agent_action, log_agent_communication
from memory import SharedMemory


class BaseAgent(ABC):
    """Provides shared infrastructure: messaging, decisions, LLM calls, traces."""

    def __init__(self, role: AgentRole, memory: SharedMemory) -> None:
        self.role = role
        self.memory = memory
        self.logger = get_agent_logger(role.value)
        self.compass = get_compass_client()
        self.decision_history: List[Dict[str, Any]] = []
        self.interaction_history: List[Message] = []

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def process_task(self, task: Task, project: Project) -> str:
        """Execute a task and return a human-readable result summary."""

    @abstractmethod
    def get_next_actions(self, project: Project) -> List[Task]:
        """Return the list of tasks this agent should work on next."""

    # ------------------------------------------------------------------
    # LLM reasoning
    # ------------------------------------------------------------------

    async def llm_decide(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 600,
        use_reasoning_model: bool = False,
    ) -> Dict[str, Any]:
        """Ask the LLM for a structured JSON decision.

        Always returns a dict; falls back gracefully if parsing fails.
        use_reasoning_model=True routes to gpt-5.1 for complex reasoning tasks.
        """
        raw = await self.compass.call_llm(system_prompt, user_message, max_tokens, use_reasoning_model=use_reasoning_model)
        if not raw:
            return {"reasoning": "No LLM response", "confidence": 0.5, "decision": "proceed"}

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"reasoning": cleaned[:300], "confidence": 0.65, "decision": "proceed"}

    # ------------------------------------------------------------------
    # Structured trace logging
    # ------------------------------------------------------------------

    def log_trace(
        self,
        action: str,
        input_summary: str,
        output_summary: str,
        target_agent: Optional[str] = None,
        confidence: float = 0.85,
        retry_count: int = 0,
        status: str = "success",
        **extra: Any,
    ) -> Dict[str, Any]:
        """Write one JSONL trace event and return the event dict."""
        return trace_logger.log_trace(
            agent_name=self.role.value,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            target_agent=target_agent,
            confidence=confidence,
            retry_count=retry_count,
            status=status,
            **extra,
        )

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(
        self,
        receiver: AgentRole,
        content: str,
        message_type: str = "communication",
        project_id: str = "",
    ) -> None:
        message = Message(
            sender=self.role,
            receiver=receiver,
            content=content,
            message_type=message_type,
            metadata={"interaction_type": message_type, "project_id": project_id},
        )
        self.memory.add_message(message)
        self.interaction_history.append(message)
        log_agent_communication(self.logger, self.role.value, receiver.value, content)

    def receive_messages(self) -> List[Message]:
        return self.memory.get_messages_for_agent(self.role)

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def make_decision(
        self, decision: str, reasoning: str, project_id: str = ""
    ) -> None:
        self.decision_history.append(
            {
                "decision": decision,
                "reasoning": reasoning,
            }
        )
        self.memory.log_decision(self.role, decision, reasoning, project_id)
        log_agent_action(
            self.logger,
            self.role.value,
            "make_decision",
            {"decision": decision, "reasoning": reasoning},
            project_id,
        )

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def update_task(
        self, project_id: str, task_id: str, updates: Dict[str, Any]
    ) -> None:
        project = self.memory.get_project(project_id)
        if project:
            for task in project.tasks:
                if task.id == task_id:
                    for key, value in updates.items():
                        if hasattr(task, key):
                            setattr(task, key, value)
                    self.memory.update_project(project_id, {"tasks": project.tasks})
                    break

    def create_subtask(
        self, project_id: str, parent_task_id: str, subtask: Task
    ) -> None:
        project = self.memory.get_project(project_id)
        if project:
            for task in project.tasks:
                if task.id == parent_task_id:
                    task.subtasks.append(subtask.id)
                    project.tasks.append(subtask)
                    self.memory.update_project(project_id, {"tasks": project.tasks})
                    break

    # ------------------------------------------------------------------
    # Escalation and feedback
    # ------------------------------------------------------------------

    def escalate_issue(
        self, project_id: str, issue: str, to_agent: AgentRole
    ) -> None:
        self.send_message(to_agent, f"ESCALATION: {issue}", "escalation", project_id)
        log_agent_action(
            self.logger,
            self.role.value,
            "escalate_issue",
            {"issue": issue, "to_agent": to_agent.value},
            project_id,
        )

    def request_feedback(
        self, receiver: AgentRole, content: str, project_id: str = ""
    ) -> None:
        self.send_message(receiver, content, "request", project_id)
        self.memory.log_feedback_loop(self.role, receiver, content, project_id, 1)

    def provide_feedback(
        self, to_agent: AgentRole, feedback: str, project_id: str = ""
    ) -> None:
        self.send_message(to_agent, feedback, "feedback", project_id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_interaction_summary(self) -> Dict[str, Any]:
        return {
            "agent": self.role.value,
            "total_interactions": len(self.interaction_history),
            "total_decisions": len(self.decision_history),
            "interactions": [m.to_dict() for m in self.interaction_history[-5:]],
            "recent_decisions": self.decision_history[-3:],
        }
