"""Orchestrator – thin compatibility wrapper around the LangGraph PMWorkflowGraph.

run.py and the FastAPI layer continue to call:
    orchestrator.initialize_agents()
    project = orchestrator.create_project(id, name, description)
    result  = await orchestrator.run_workflow(project)

All actual workflow logic now lives in graph.py (LangGraph StateGraph).
"""
import logging
from typing import Any, Dict

from data_types import AgentRole, Project
from graph import PMWorkflowGraph
from memory import SharedMemory


class AgentOrchestrator:
    """Thin wrapper that delegates to PMWorkflowGraph.

    Kept for API compatibility with run.py and the /status endpoint.
    """

    def __init__(self, memory: SharedMemory) -> None:
        self.memory = memory
        self.graph = PMWorkflowGraph(memory)
        self.logger = logging.getLogger("orchestrator")
        self.iteration: int = 0
        self.run_id: str = ""

        # Populated by initialize_agents() for the /status endpoint
        self.agents: Dict[AgentRole, Any] = {}

    def initialize_agents(self) -> None:
        """Expose the graph's agent instances for the /status endpoint."""
        self.agents = {
            AgentRole.PROJECT_MANAGER: self.graph.pm,
            AgentRole.ENGINEER:        self.graph.engineer,
            AgentRole.QA:              self.graph.qa,
            AgentRole.RISK_ANALYST:    self.graph.risk_analyst,
            AgentRole.STAKEHOLDER:     self.graph.stakeholder,
        }
        self.logger.info("All agents initialised via LangGraph PMWorkflowGraph")

    def create_project(
        self, project_id: str, name: str, description: str
    ) -> Project:
        """Register the project in SharedMemory and return a Project object."""
        project = Project(
            id=project_id, name=name, description=description, status="planning"
        )
        self.memory.add_project(project)
        self.logger.info(f"Project created: {name}")
        return project

    async def run_workflow(self, project: Project) -> Dict[str, Any]:
        """Delegate to PMWorkflowGraph and return the result dict."""
        result = await self.graph.run_workflow(
            project.id, project.name, project.description
        )
        self.iteration = result.get("iterations", 0)
        self.run_id = result.get("run_id", "")
        return result

    def get_execution_summary(self) -> Dict[str, Any]:
        """Return a summary of the last execution (kept for test/debug use)."""
        all_interactions = self.memory.get_all_interactions()
        return {
            "run_id": self.run_id,
            "total_messages": len(all_interactions["messages"]),
            "total_decisions": len(all_interactions["decisions"]),
            "feedback_loops": len(all_interactions["feedback_loops"]),
            "iterations": self.iteration,
        }
