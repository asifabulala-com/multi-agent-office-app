from enum import Enum
from typing import Any, Dict, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json


class AgentRole(str, Enum):
    """Agent roles in the system"""
    PROJECT_MANAGER = "project_manager"
    ENGINEER = "engineer"
    QA = "qa"
    RISK_ANALYST = "risk_analyst"
    STAKEHOLDER = "stakeholder"


class TaskStatus(str, Enum):
    """Task status values"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Message:
    """Message between agents"""
    sender: AgentRole
    receiver: AgentRole
    content: str
    message_type: str = "communication"  # communication, request, feedback, approval
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    """Task in the system"""
    id: str
    title: str
    description: str
    assigned_to: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    result: str = ""
    risk_level: str = "medium"  # low, medium, high
    estimated_effort: int = 0  # hours
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "dependencies": self.dependencies,
            "subtasks": self.subtasks,
            "result": self.result,
            "risk_level": self.risk_level,
            "estimated_effort": self.estimated_effort,
            "metadata": self.metadata,
        }


@dataclass
class Project:
    """Project being managed"""
    id: str
    name: str
    description: str
    status: str = "planning"  # planning, in_progress, completed, on_hold
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tasks: List[Task] = field(default_factory=list)
    risks: List[Dict[str, Any]] = field(default_factory=list)
    stakeholder_feedback: List[Message] = field(default_factory=list)
    qa_reports: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "tasks": [t.to_dict() for t in self.tasks],
            "risks": self.risks,
            "stakeholder_feedback": [m.to_dict() if hasattr(m, 'to_dict') else m for m in self.stakeholder_feedback],
            "qa_reports": self.qa_reports,
            "metadata": self.metadata,
        }
