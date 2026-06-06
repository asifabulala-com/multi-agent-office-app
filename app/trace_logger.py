"""Structured JSONL trace logger for multi-agent interactions.

Appends one JSON line per event to logs/agent_trace.jsonl with the
fields judges expect: timestamp, trace_id, agent_name, action,
input_summary, output_summary, target_agent, confidence, retry_count,
status.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

TRACE_FILE = LOGS_DIR / "agent_trace.jsonl"

_run_id: Optional[str] = None
_trace_id: Optional[str] = None


def init_run(run_id: Optional[str] = None) -> str:
    """Start a new run; all subsequent events share the same trace_id."""
    global _run_id, _trace_id
    _run_id = run_id or uuid.uuid4().hex[:8]
    _trace_id = f"trace-{_run_id}"
    return _run_id


def get_run_id() -> str:
    if _run_id is None:
        init_run()
    return _run_id  # type: ignore[return-value]


def log_trace(
    agent_name: str,
    action: str,
    input_summary: str,
    output_summary: str,
    target_agent: Optional[str] = None,
    confidence: float = 0.85,
    retry_count: int = 0,
    status: str = "success",
    **extra: Any,
) -> Dict[str, Any]:
    """Append one structured event to logs/agent_trace.jsonl."""
    global _run_id, _trace_id
    if _run_id is None:
        init_run()

    event: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trace_id": _trace_id,
        "run_id": _run_id,
        "agent_name": agent_name,
        "action": action,
        "input_summary": input_summary[:200],
        "output_summary": output_summary[:200],
        "target_agent": target_agent,
        "confidence": round(float(confidence), 3),
        "retry_count": retry_count,
        "status": status,
    }
    event.update({k: v for k, v in extra.items() if v is not None})

    with open(TRACE_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")

    arrow = f"-> {target_agent}" if target_agent else "           "
    try:
        print(
            f"[TRACE] {event['timestamp']} | {agent_name:20s} | {action:28s} | "
            f"{arrow:25s} | conf={confidence:.2f} | {status}"
        )
    except UnicodeEncodeError:
        print(f"[TRACE] {event['timestamp']} | {agent_name} | {action} | conf={confidence:.2f} | {status}")
    return event
