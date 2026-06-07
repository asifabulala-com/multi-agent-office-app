# API Documentation

## Overview

The Multi-Agent Office Simulation System exposes a RESTful API running on FastAPI. All endpoints return JSON responses and support standard HTTP status codes.

**Base URL**: `http://localhost:8000`  
**API Documentation**: `http://localhost:8000/docs` (Swagger UI)  
**ReDoc Documentation**: `http://localhost:8000/redoc`

---

## Endpoints

### 1. Health Check

**Endpoint**: `GET /health`

**Description**: Check system health and availability

**Parameters**: None

**Response** (200 OK):
```json
{
  "status": "ok",
  "service": "Multi-Agent Office Simulation System",
  "version": "1.0.0",
  "timestamp": "2026-06-07T10:00:00+00:00",
  "timeout_seconds": 900
}
```

**Example**:
```bash
curl http://localhost:8000/health
```

---

### 2. Run Project (Async)

**Endpoint**: `POST /run`

**Description**: Execute multi-agent project simulation asynchronously

**Request Body**:
```json
{
  "project_id": "proj_001",
  "project_name": "Multi-Agent Project",
  "description": "Testing collaborative AI agents"
}
```

**Request Parameters**:
- `project_id` (string, required) - Unique project identifier
- `project_name` (string, required) - Human-readable project name
- `description` (string, required) - Project description

**Response** (200 OK):
```json
{
  "project_id": "proj_001",
  "status": "completed",
  "iterations": 3,
  "compass_evaluation": {
    "evaluation_id": "eval_12345",
    "results": {
      "collaboration_score": 8.5,
      "pattern": "iterative_feedback"
    },
    "collaboration_evaluation": {
      "status": "strong_collaboration"
    },
    "metrics": {
      "interactions": 47,
      "feedback_loops": 3,
      "decisions": 12,
      "pattern": "iterative_feedback"
    }
  },
  "interactions": {
    "messages": [...],
    "decisions": [...],
    "feedback_loops": {...}
  }
}
```

**Error Responses**:
- `500 Internal Server Error` - Project execution failed

**Example**:
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_001",
    "project_name": "Multi-Agent Project",
    "description": "Collaborative AI agent project"
  }'
```

**Execution Timeline**: ~30-60 seconds depending on iteration count

---

### 3. Run Project (Sync)

**Endpoint**: `POST /run-sync`

**Description**: Execute multi-agent project simulation synchronously

**Request Body**: Same as `/run`

**Response**: Same as `/run`

**Note**: Blocks until execution completes. Useful for testing and verification.

**Example**:
```bash
curl -X POST http://localhost:8000/run-sync \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_001",
    "project_name": "Multi-Agent Project",
    "description": "Collaborative AI agent project"
  }'
```

---

### 4. Get Project

**Endpoint**: `GET /project/{project_id}`

**Description**: Retrieve current project state and details

**Path Parameters**:
- `project_id` (string, required) - Project identifier

**Response** (200 OK):
```json
{
  "id": "proj_001",
  "name": "Multi-Agent Project",
  "description": "...",
  "status": "completed",
  "created_at": "2026-05-18T10:30:45.123456",
  "tasks": [
    {
      "id": "task_001",
      "title": "Project Planning",
      "description": "...",
      "assigned_to": "project_manager",
      "status": "completed",
      "created_at": "...",
      "updated_at": "...",
      "dependencies": [],
      "subtasks": [],
      "result": "...",
      "risk_level": "medium",
      "estimated_effort": 8,
      "metadata": {}
    }
  ],
  "risks": [...],
  "stakeholder_feedback": [...],
  "qa_reports": [...],
  "metadata": {}
}
```

**Error Responses**:
- `404 Not Found` - Project doesn't exist
- `500 Internal Server Error` - Server error

**Example**:
```bash
curl http://localhost:8000/project/proj_001
```

---

### 5. Get Agent Interactions

**Endpoint**: `GET /interactions/{project_id}`

**Description**: Retrieve all agent interactions for a project

**Path Parameters**:
- `project_id` (string, required) - Project identifier

**Response** (200 OK):
```json
{
  "project_id": "proj_001",
  "interactions": [
    {
      "sender": "project_manager",
      "receiver": "engineer",
      "content": "Your development tasks are ready...",
      "message_type": "task_assignment",
      "timestamp": "2026-05-18T10:30:45.123456",
      "metadata": {...}
    },
    {
      "sender": "qa",
      "receiver": "engineer",
      "content": "Testing of Task 1 found 5 issues...",
      "message_type": "feedback",
      "timestamp": "2026-05-18T10:35:20.654321",
      "metadata": {...}
    }
  ],
  "count": 47
}
```

**Error Responses**:
- `500 Internal Server Error` - Server error

**Example**:
```bash
curl http://localhost:8000/interactions/proj_001
```

---

### 6. Get System Status

**Endpoint**: `GET /status`

**Description**: Get current system status and metrics

**Parameters**: None

**Response** (200 OK):
```json
{
  "status": "running",
  "agents_initialized": 5,
  "projects": 1,
  "total_messages": 47,
  "total_decisions": 12,
  "feedback_loops": 3,
  "agents": [
    "project_manager",
    "engineer",
    "qa",
    "risk_analyst",
    "stakeholder"
  ]
}
```

**Error Responses**:
- `500 Internal Server Error` - Server error

**Example**:
```bash
curl http://localhost:8000/status
```

---

### 7. Compass Probe

**Endpoint**: `GET /compass/probe`

**Description**: Verify that the agent can reach the Compass/Core42 LLM endpoint using the injected API key. Used by judges before scoring.

**Parameters**: None

**Response** (200 OK):
```json
{
  "status": "ok",
  "compass_reachable": true,
  "model": "gpt-4.1",
  "latency_ms": 420
}
```

**Error Response** (200 OK with error body):
```json
{
  "status": "error",
  "compass_reachable": false,
  "error": "Connection refused"
}
```

**Example**:
```bash
curl http://localhost:8000/compass/probe
```

---

### 8. Demo Presentation

**Endpoint**: `GET /demo`

**Description**: Serve the submission demo presentation HTML file from `docs/submission_demo.html`. Useful for live demos where a same-origin iframe is required.

**Parameters**: None

**Response**: HTML page (200 OK) or 404 if the file is not present.

---

### 9. Submission Demo (alias)

**Endpoint**: `GET /submission_demo`

**Description**: Alias for `/demo` — serves `docs/submission_demo.html`.

---

### 10. Reset System

**Endpoint**: `POST /reset`

**Description**: Clear all projects and reset system state

**Parameters**: None

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "System reset complete"
}
```

**Warning**: This deletes all project data and interactions

**Error Responses**:
- `500 Internal Server Error` - Reset failed

**Example**:
```bash
curl -X POST http://localhost:8000/reset
```

---

## Response Models

### ProjectRequest

```python
{
  "project_id": str,      # Unique identifier
  "project_name": str,    # Human-readable name
  "description": str      # Project description
}
```

### ExecutionResponse

```python
{
  "project_id": str,
  "status": str,          # "completed", "failed"
  "iterations": int,      # Number of iterations
  "compass_evaluation": {
    "evaluation_id": str,
    "results": dict,
    "collaboration_evaluation": dict,
    "metrics": dict
  },
  "interactions": {
    "messages": list,
    "decisions": list,
    "feedback_loops": dict
  }
}
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| **200** | Success |
| **201** | Created |
| **400** | Bad Request |
| **404** | Not Found |
| **500** | Internal Server Error |

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Descriptive error message"
}
```

### Common Errors

**Invalid Project ID**:
```
GET /project/invalid_id
→ 404 Not Found
→ "Project not found"
```

**Execution Failure**:
```
POST /run
→ 500 Internal Server Error
→ "Project execution failed: [reason]"
```

---

## Authentication

Currently, the API has **no authentication**. In production, add:
- API key validation
- JWT tokens
- CORS headers
- Rate limiting

---

## Rate Limiting

Not implemented in current version. In production, recommend:
- Max 10 concurrent executions
- Max 60 requests per minute per client
- Queue system for large projects

---

## Data Flow

### Execution Flow

```
1. Client sends POST /run request
   ↓
2. API receives and validates request
   ↓
3. Orchestrator creates project
   ↓
4. Orchestrator initializes agents
   ↓
5. Planning phase executes
   ├─ Stakeholder approves
   ├─ PM plans
   ├─ Risk assesses
   └─ Readiness checked
   ↓
6. Execution phase runs (iterative)
   ├─ Engineer develops
   ├─ QA tests
   ├─ Feedback loops if needed
   ├─ Risk monitors
   └─ Stakeholder tracks
   ↓
7. Evaluation phase validates
   ├─ Quality gates checked
   ├─ Reports generated
   └─ Status finalized
   ↓
8. Compass submission
   ├─ Project data sent
   ├─ Interactions logged
   └─ Evaluation received
   ↓
9. Response returned to client
   ├─ Execution summary
   ├─ Compass results
   └─ Interaction logs
```

---

## Example Workflows

### Complete Project Execution

```bash
# 1. Start server
python run.py

# 2. Check health
curl http://localhost:8000/health

# 3. Run project
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_001",
    "project_name": "Example Project",
    "description": "Testing multi-agent collaboration"
  }'

# 4. Get project details (while running or after)
curl http://localhost:8000/project/proj_001

# 5. Get interactions
curl http://localhost:8000/interactions/proj_001

# 6. Check system status
curl http://localhost:8000/status

# 7. Reset for next test (optional)
curl -X POST http://localhost:8000/reset
```

### Python Client Example

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Check health
response = requests.get(f"{BASE_URL}/health")
print(f"Health: {response.json()}")

# Run project
project_data = {
    "project_id": "proj_001",
    "project_name": "Test Project",
    "description": "Testing multi-agent system"
}

response = requests.post(
    f"{BASE_URL}/run",
    json=project_data
)

result = response.json()
print(f"Execution Status: {result['status']}")
print(f"Iterations: {result['iterations']}")
print(f"Compass Evaluation: {result['compass_evaluation']}")

# Get interactions
response = requests.get(f"{BASE_URL}/interactions/{project_data['project_id']}")
interactions = response.json()
print(f"Total Interactions: {interactions['count']}")
```

---

## Logging

All requests and responses are logged to `agent_interactions.log` in JSON format.

### Log Format

```json
{
  "timestamp": "2026-05-18T10:30:45.123456",
  "level": "INFO",
  "logger": "api",
  "message": "Starting project execution: proj_001",
  "agent": "orchestrator",
  "interaction_type": "execution"
}
```

---

## Performance Considerations

### Execution Time

- **Planning Phase**: ~2-3 seconds
- **Execution Phase** (per iteration): ~5-8 seconds
- **Evaluation Phase**: ~2-3 seconds
- **Compass Submission**: ~3-5 seconds
- **Total**: ~30-60 seconds (3-5 iterations)

### Memory Usage

- Project data: ~10-50 KB
- Interactions/messages: ~100-500 KB
- Decision logs: ~50-200 KB
- **Total per project**: ~200 KB - 1 MB

---

## Future Enhancements

- [ ] WebSocket for real-time updates
- [ ] Batch project execution
- [ ] Project templates
- [ ] Custom agent configuration
- [ ] Performance monitoring endpoints
- [ ] Advanced filtering for interactions
- [ ] Export to various formats (CSV, PDF)
- [ ] Webhook notifications

---

## Troubleshooting

### Server Won't Start

```bash
# Check if port 8000 is in use
netstat -tuln | grep 8000

# Try different port
uvicorn run:app --port 8001
```

### Slow Execution

- Reduce `max_iterations` in orchestrator
- Check system resources
- Review logs for bottlenecks

### No Compass Results

- Verify `COMPASS_API_KEY` in `.env`
- Check Compass connectivity
- Review API logs for errors

### Incomplete Interactions

- Check that all agents are initialized
- Verify shared memory is working
- Review orchestrator logs

---

**API Version**: 1.0.0  
**Last Updated**: 2026-06-07  
**Status**: Production Ready
