# Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Python 3.9+
- pip

### Installation

1. **Navigate to project directory**
```bash
cd multi_agent_pm
```

2. **Create virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

### Running the System

1. **Start the API server**
```bash
python run.py
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

2. **In another terminal, test the system**
```bash
# Health check
curl http://localhost:8000/health

# Run a project
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "demo_001",
    "project_name": "Demo Project",
    "description": "Multi-agent collaboration demo"
  }'
```

3. **View results**
```bash
# Get execution details
curl http://localhost:8000/project/demo_001

# View agent interactions
curl http://localhost:8000/interactions/demo_001

# Check system status
curl http://localhost:8000/status
```

### Check Logs

```bash
# View agent interactions log
tail -f agent_interactions.log

# Or open directly
cat agent_interactions.log | python -m json.tool
```

## API Documentation

- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **API Reference**: See `docs/API.md`

## Project Structure

```
multi_agent_pm/
├── run.py              Main server (START HERE)
├── orchestrator.py     Agent coordination
├── base_agent.py       Base agent class
├── project_manager.py  Agent #1
├── engineer.py         Agent #2
├── qa_agent.py         Agent #3
├── risk_analyst.py     Agent #4
├── stakeholder.py      Agent #5
├── memory.py           Shared context
├── types.py            Data models
├── compass_integration.py  Compass API
├── logging_config.py   Logging setup
├── README.md           Full documentation
└── docs/
    ├── ARCHITECTURE.md    System design
    ├── AGENTS.md          Agent specs
    ├── COLLABORATION.md   Collaboration patterns
    ├── API.md             API endpoints
    └── STRONG_COLLABORATION.md  Why it's strong
```

## Key Files to Review

1. **run.py** - FastAPI server with /run endpoint
2. **orchestrator.py** - Workflow orchestration
3. **docs/COLLABORATION.md** - Collaboration patterns
4. **docs/STRONG_COLLABORATION.md** - Why this is strong

## Common Commands

### Development
```bash
# Run server with auto-reload
uvicorn run:app --reload

# Run on different port
python run.py  # or: uvicorn run:app --port 8001
```

### Testing
```bash
# Run test project
curl -X POST http://localhost:8000/run-sync \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test1", "project_name": "Test", "description": "Test"}'
```

### Cleanup
```bash
# Reset all projects
curl -X POST http://localhost:8000/reset

# Remove virtual environment
rm -rf venv
```

## Troubleshooting

### Port Already in Use
```bash
# Find and kill process using port 8000
lsof -i :8000
kill -9 <PID>

# Or use different port
uvicorn run:app --port 8001
```

### Module Not Found
```bash
# Make sure you're in virtual environment
which python
# Should show: .../venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt
```

### Import Errors
```bash
# Make sure PYTHONPATH includes current directory
export PYTHONPATH="${PYTHONPATH}:."
python run.py
```

## Next Steps

1. **Read the documentation**:
   - `README.md` - Complete overview
   - `docs/ARCHITECTURE.md` - System design
   - `docs/AGENTS.md` - Agent specifications
   - `docs/COLLABORATION.md` - Collaboration patterns

2. **Run the API**:
   - Start `python run.py`
   - Visit http://localhost:8000/docs for interactive docs
   - Test POST /run endpoint

3. **Examine the code**:
   - `orchestrator.py` - Workflow coordination
   - `base_agent.py` - Agent base class
   - Individual agent files for specific implementations

4. **Check the logs**:
   - View `agent_interactions.log` for detailed execution traces
   - Each interaction is logged with timestamps and metadata

5. **Try the examples**:
   - Run test projects with different IDs
   - Observe feedback loops and iterations
   - Verify Compass integration

## Configuration

### Environment Variables (.env)

```env
# Compass Integration
COMPASS_API_KEY=demo-key
COMPASS_BASE_URL=https://compass.g42.ai/api

# API Configuration
API_PORT=8000
API_HOST=0.0.0.0
LOG_LEVEL=INFO
```

### System Parameters

In `orchestrator.py`:
```python
self.max_iterations = 5  # Maximum execution iterations
```

In `qa_agent.py`:
```python
self.test_coverage_target = 80  # Percentage
```

## Performance Tips

- Reduce `max_iterations` in orchestrator for faster execution
- Use `/run-sync` for testing, `/run` for async execution
- Monitor `agent_interactions.log` for performance bottlenecks

## What You're Running

This is a **strong multi-agent collaboration system** with:

✅ **5 specialized agents** (PM, Engineer, QA, Risk, Stakeholder)  
✅ **Feedback loops** (QA tests, Engineer fixes, QA re-tests)  
✅ **Escalation chains** (Engineer → PM → Stakeholder)  
✅ **Shared memory** (All agents access same context)  
✅ **Iterative refinement** (Multiple cycles until quality gates met)  
✅ **Real decision-making** (12+ decision points)  
✅ **Compass integration** (Evaluation submission)  
✅ **Comprehensive logging** (Every interaction traced)  

## Support

- Check `agent_interactions.log` for detailed logs
- Review documentation in `docs/`
- Examine source code for implementation details
- Visit http://localhost:8000/docs for API details

---

**Happy multi-agent collaboration testing!**
