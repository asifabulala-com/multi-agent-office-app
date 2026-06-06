"""Shared memory system for agent communication and collaboration."""
import json
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional, Union

from data_types import AgentRole, Message, Project, Task, TaskStatus


class SharedMemory:
    """Thread-safe shared context accessible by all agents."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.projects: Dict[str, Project] = {}
        self.messages: List[Message] = []
        self.agent_states: Dict[AgentRole, Dict[str, Any]] = {}
        self.decisions_log: List[Dict[str, Any]] = []
        self.feedback_loops: Dict[str, List[Dict[str, Any]]] = {}
        # Stores agent reasoning summaries keyed by "agent_role:context_key"
        # so any agent can read another's output for cross-agent context.
        self.agent_summaries: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def add_project(self, project: Project) -> None:
        with self.lock:
            self.projects[project.id] = project

    def get_project(self, project_id: str) -> Optional[Project]:
        with self.lock:
            return self.projects.get(project_id)

    def update_project(self, project_id: str, updates: Dict[str, Any]) -> None:
        with self.lock:
            if project_id in self.projects:
                project = self.projects[project_id]
                for key, value in updates.items():
                    if hasattr(project, key):
                        setattr(project, key, value)

    def get_agent_tasks(self, agent_role: AgentRole, project_id: str) -> List[Task]:
        with self.lock:
            project = self.projects.get(project_id)
            if not project:
                return []
            return [t for t in project.tasks if t.assigned_to == agent_role]

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, message: Message) -> None:
        with self.lock:
            self.messages.append(message)
            try:
                print(
                    f"[MSG] {message.sender.value} -> {message.receiver.value}: "
                    f"{message.content[:80]}..."
                )
            except UnicodeEncodeError:
                pass

    def get_messages_for_agent(
        self, agent_role: AgentRole, limit: int = 20
    ) -> List[Message]:
        with self.lock:
            msgs = [m for m in self.messages if m.receiver == agent_role]
            return msgs[-limit:]

    def get_project_messages(self, project_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            return [
                m.to_dict()
                for m in self.messages
                if project_id in str(m.metadata)
            ]

    # ------------------------------------------------------------------
    # Agent summaries – cross-agent context sharing
    # ------------------------------------------------------------------

    def store_summary(self, agent_role: AgentRole, key: str, summary: str) -> None:
        """Store an agent's reasoning/output so other agents can read it."""
        with self.lock:
            self.agent_summaries[f"{agent_role.value}:{key}"] = summary

    def get_summary(self, agent_role: AgentRole, key: str) -> str:
        """Retrieve a stored summary produced by another agent."""
        with self.lock:
            return self.agent_summaries.get(f"{agent_role.value}:{key}", "")

    def get_all_summaries(self) -> Dict[str, str]:
        with self.lock:
            return dict(self.agent_summaries)

    # ------------------------------------------------------------------
    # Decisions and feedback loops
    # ------------------------------------------------------------------

    def log_decision(
        self,
        agent: AgentRole,
        decision: str,
        reasoning: str,
        project_id: str,
    ) -> None:
        with self.lock:
            self.decisions_log.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "agent": agent.value,
                    "decision": decision,
                    "reasoning": reasoning,
                    "project_id": project_id,
                }
            )

    def log_feedback_loop(
        self,
        from_agent: AgentRole,
        to_agent: AgentRole,
        feedback: str,
        project_id: str,
        iteration: int,
    ) -> None:
        with self.lock:
            key = f"{from_agent.value}->{to_agent.value}_{project_id}"
            if key not in self.feedback_loops:
                self.feedback_loops[key] = []
            self.feedback_loops[key].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "iteration": iteration,
                    "feedback": feedback,
                }
            )

    # ------------------------------------------------------------------
    # Agent state
    # ------------------------------------------------------------------

    def set_agent_state(self, agent: AgentRole, state: Dict[str, Any]) -> None:
        with self.lock:
            self.agent_states[agent] = state

    def get_agent_state(self, agent: AgentRole) -> Dict[str, Any]:
        with self.lock:
            return self.agent_states.get(agent, {})

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_all_interactions(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "messages": [m.to_dict() for m in self.messages],
                "decisions": self.decisions_log,
                "feedback_loops": self.feedback_loops,
                "agent_summaries": dict(self.agent_summaries),
            }

    def clear(self) -> None:
        with self.lock:
            self.projects.clear()
            self.messages.clear()
            self.agent_states.clear()
            self.decisions_log.clear()
            self.feedback_loops.clear()
            self.agent_summaries.clear()
