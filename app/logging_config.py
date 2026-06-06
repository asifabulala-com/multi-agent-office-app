"""Logging configuration for the multi-agent system"""
import logging
import json
from datetime import datetime
from typing import Any, Dict


class AgentInteractionFormatter(logging.Formatter):
    """Custom formatter for agent interactions"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add custom fields if present
        if hasattr(record, "agent"):
            log_data["agent"] = record.agent
        if hasattr(record, "interaction_type"):
            log_data["interaction_type"] = record.interaction_type
        if hasattr(record, "project_id"):
            log_data["project_id"] = record.project_id

        return json.dumps(log_data)


def setup_logging(log_file: str = "agent_interactions.log") -> None:
    """Setup logging for the system"""
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = AgentInteractionFormatter()
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)


def get_agent_logger(agent_name: str) -> logging.Logger:
    """Get a logger for an agent"""
    return logging.getLogger(f"agent.{agent_name}")


def log_agent_action(
    logger: logging.Logger,
    agent: str,
    action: str,
    details: Dict[str, Any],
    project_id: str = "",
) -> None:
    """Log an agent action with details"""
    logger.info(
        f"Agent {agent} action: {action}",
        extra={
            "agent": agent,
            "interaction_type": "action",
            "action": action,
            "details": json.dumps(details),
            "project_id": project_id,
        },
    )


def log_agent_communication(
    logger: logging.Logger,
    from_agent: str,
    to_agent: str,
    message: str,
    project_id: str = "",
) -> None:
    """Log communication between agents"""
    logger.info(
        f"{from_agent} ->{to_agent}: {message}",
        extra={
            "interaction_type": "communication",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "project_id": project_id,
        },
    )


def log_agent_decision(
    logger: logging.Logger,
    agent: str,
    decision: str,
    reasoning: str,
    project_id: str = "",
) -> None:
    """Log an agent decision with reasoning"""
    logger.info(
        f"Agent {agent} decision: {decision}",
        extra={
            "agent": agent,
            "interaction_type": "decision",
            "decision": decision,
            "reasoning": reasoning,
            "project_id": project_id,
        },
    )


def log_feedback_loop(
    logger: logging.Logger,
    from_agent: str,
    to_agent: str,
    feedback: str,
    iteration: int,
    project_id: str = "",
) -> None:
    """Log feedback loop between agents"""
    logger.info(
        f"Feedback loop {from_agent} ->{to_agent} (iteration {iteration})",
        extra={
            "interaction_type": "feedback_loop",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "iteration": iteration,
            "feedback": feedback,
            "project_id": project_id,
        },
    )
