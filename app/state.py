"""LangGraph state definition for the multi-agent PM workflow.

ProjectState is the single source of truth passed between every node in the graph.
It replaces the implicit state split between SharedMemory and orchestrator instance
variables, making data flow explicit and auditable.
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class ProjectState(TypedDict):
    """Typed state dict passed through every node in the LangGraph workflow."""

    # ── Identity ────────────────────────────────────────────────────────────
    project_id: str
    project_name: str
    project_description: str
    project_status: str
    run_id: str

    # ── Planning outputs (set by PM node, read by all subsequent nodes) ─────
    tasks: List[Dict[str, Any]]          # serialised Task.to_dict() entries
    risks: List[Dict[str, Any]]          # risk-register entries
    project_metadata: Dict[str, Any]     # tech stack, phases, effort, etc.

    # ── Execution-loop tracking ─────────────────────────────────────────────
    engineer_task_queue: List[str]       # ordered task IDs for the Engineer
    current_task_id: str                 # task currently being processed
    qa_retry_count: int                  # QA retries for the current task
    qa_approved: bool                    # QA verdict for the current task
    qa_issues: List[Dict[str, Any]]      # issues from the last QA critique
    iteration: int                       # execution-loop counter

    # ── Conditional-edge routing flags ──────────────────────────────────────
    high_risks_detected: bool            # set by assess_risks → triggers replan
    critical_risks_detected: bool        # set by monitor_risks → triggers mid-replan

    # ── Cross-agent context (mirrors SharedMemory.agent_summaries) ──────────
    agent_summaries: Dict[str, str]      # "role:key" → summary text

    # ── Interaction logs (each node returns full current list from memory) ───
    messages: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]
    feedback_loops: Dict[str, List[Dict[str, Any]]]

    # ── Final results ────────────────────────────────────────────────────────
    compass_evaluation: Dict[str, Any]
    collaboration_summary: Dict[str, Any]
    report_path: str
    mvp_path: str
