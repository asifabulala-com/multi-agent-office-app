"""FastAPI server + CLI entry point for the multi-agent PM system.

HTTP:  POST /run  (port 8000)
CLI:   python run.py --input input_examples/input_1.json [--output out.json]
"""
import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
load_dotenv()

# Add app/ to sys.path so all intra-package imports (from base_agent import ...)
# resolve correctly without requiring changes inside the package files.
sys.path.insert(0, str(Path(__file__).parent / "app"))

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from logging_config import setup_logging
from memory import SharedMemory
from orchestrator import AgentOrchestrator
import trace_logger


# Setup logging
setup_logging("agent_interactions.log")
logger = logging.getLogger("api")

# Initialize FastAPI app
app = FastAPI(
    title="Multi-Agent Office Simulation System",
    description="AI agents collaborating on project management",
    version="1.0.0"
)

# Serve frontend static files (index.html loads /static/app.js and /static/styles.css)
ROOT_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=ROOT_DIR / "frontend" / "dist"), name="static")

# Serve docs folder (submission_demo.html + img screenshots)
# Access at: http://localhost:8000/docs/submission_demo.html
app.mount("/docs", StaticFiles(directory=ROOT_DIR / "docs"), name="docs")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend() -> HTMLResponse:
    """Serve the single-page frontend application."""
    index_file = ROOT_DIR / "frontend" / "dist" / "index.html"
    return HTMLResponse(index_file.read_text(encoding="utf-8"))

@app.get("/demo", response_class=HTMLResponse)
async def serve_demo() -> HTMLResponse:
    """Serve the submission demo presentation (same-origin so live iframe works)."""
    demo_file = ROOT_DIR / "docs" / "submission_demo.html"
    return HTMLResponse(demo_file.read_text(encoding="utf-8"))

# Global state
memory: SharedMemory = SharedMemory()
orchestrator: AgentOrchestrator = AgentOrchestrator(memory)
orchestrator.initialize_agents()


SAMPLE_MODE = os.getenv("SAMPLE_MODE", "false").lower() == "true"

_SAMPLE_PROJECT = {
    "project_id": "SampleProject001",
    "project_name": "Sample Web Application",
    "description": (
        "Build a modern web application with user authentication, "
        "a REST API, and a React frontend. Use FastAPI and PostgreSQL."
    ),
}


class ProjectRequest(BaseModel):
    """Request model for project execution.

    Accepts both the domain-specific schema and the guide's recommended schema:
      Domain:  {"project_id": "...", "project_name": "...", "description": "..."}
      Guide:   {"input": "...", "use_case_id": "...", "context": {...}}
    When both are supplied, domain fields take precedence.
    """
    # Domain-specific fields
    project_id: str = ""
    project_name: str = ""
    description: str = ""
    # Guide-recommended fields
    input: str = ""
    use_case_id: str = ""
    context: Dict[str, Any] = {}


class ExecutionResponse(BaseModel):
    """Response model for execution"""
    project_id: str
    trace_id: str
    status: str
    agents_used: List[str]
    result: Dict[str, Any]
    collaboration: Dict[str, Any]
    log_path: str
    iterations: int
    compass_evaluation: Dict[str, Any]
    interactions: Dict[str, Any]
    output_app: Dict[str, Any] = {}
    mvp_url: str = ""
    report_url: str = ""


def _output_app_info(project_id: str) -> Dict[str, Any]:
    """Return run instructions if the Engineer wrote a deployable React app."""
    spa_dir = Path("output_examples") / project_id / "spa"
    pkg_path = spa_dir / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception:
        pkg = {}
    scripts = pkg.get("scripts", {})
    # Vite uses "dev", webpack uses "start" — prefer whichever exists
    if "dev" in scripts and "start" not in scripts:
        start_cmd = "npm run dev"
        port = 5173
    else:
        start_cmd = "npm start"
        port = 3000
    abs_path = str(spa_dir.resolve())
    return {
        "path": abs_path,
        "url": f"http://localhost:{port}",
        "start_cmd": start_cmd,
        "commands": [
            f'cd "{abs_path}"',
            "npm install",
            start_cmd,
        ],
        "note": "Requires Node.js 18+. Run in a separate terminal while the PM server is running.",
    }


def _print_output_app(info: Dict[str, Any], project_id: str) -> None:
    if not info:
        return
    print("")
    print("=" * 56)
    print("  GENERATED APP READY")
    print("=" * 56)
    print(f"  Project : {project_id}")
    print(f"  Path    : {info['path']}")
    print(f"  URL     : {info['url']}")
    print("")
    print("  Run in a NEW terminal window:")
    for cmd in info["commands"]:
        print(f"    {cmd}")
    print("=" * 56)
    print("")


def _launch_output_app(info: Dict[str, Any]) -> None:
    """Install deps and start the generated React app; open browser when ready."""
    if not info:
        return
    path = info["path"]
    url = info["url"]
    node_modules = Path(path) / "node_modules"

    start_cmd = info.get("start_cmd", "npm start")

    try:
        print(f"[Output App] npm install — this may take ~30s...")
        result = subprocess.run(
            "npm install",
            cwd=path,
            shell=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            print(f"[Output App] npm install failed:\n{result.stderr[:400]}")
            print(f"[Output App] Run manually: cd \"{path}\" && npm install && {start_cmd}")
            return
        print("[Output App] npm install complete.")

        print(f"[Output App] Starting dev server at {url} ...")
        subprocess.Popen(
            start_cmd,
            cwd=path,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for webpack-dev-server to boot, then open browser
        time.sleep(8)
        webbrowser.open(url)
        print(f"[Output App] Browser opened at {url}")

    except Exception as exc:
        print(f"[Output App] Auto-launch failed: {exc}")
        print(f"[Output App] Run manually: cd \"{path}\" && npm install && npm start")


def _launch_output_app_async(info: Dict[str, Any]) -> None:
    """Start the launch sequence in a background thread so the API responds immediately."""
    if not info:
        return
    thread = threading.Thread(target=_launch_output_app, args=(info,), daemon=True)
    thread.start()


def _save_output_json(result: Dict[str, Any], project_id: str) -> str:
    """Write the run result to output_examples/output_{project_id}.json and return the path."""
    try:
        out_dir = ROOT_DIR / "output_examples"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"output_{project_id}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        logger.info(f"Output JSON saved: {out_path}")
        return str(out_path)
    except Exception as exc:
        logger.error(f"Failed to save output JSON: {exc}")
        return ""


@app.get("/dataset")
async def get_dataset(department: str = "") -> Dict[str, Any]:
    """Return projects from the telecom dataset, optionally filtered by department."""
    dataset_path = ROOT_DIR / "dataset" / "telecom_projects.json"
    projects = json.loads(dataset_path.read_text(encoding="utf-8"))
    if department:
        projects = [p for p in projects if p.get("department", "").lower() == department.lower()]
    departments = sorted({p["department"] for p in json.loads(dataset_path.read_text(encoding="utf-8"))})
    return {"projects": projects, "total": len(projects), "departments": departments}


@app.get("/submission_demo", response_class=HTMLResponse)
async def serve_submission_demo() -> HTMLResponse:
    """Serve the Pitch Day submission demo presentation."""
    demo_path = ROOT_DIR / "docs" / "submission_demo.html"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="submission_demo.html not found in docs/")
    return HTMLResponse(demo_path.read_text(encoding="utf-8"))


@app.get("/mvp/{project_id}", response_class=HTMLResponse)
async def serve_mvp(project_id: str) -> HTMLResponse:
    """Serve the generated MVP HTML for a project."""
    mvp_path = ROOT_DIR / "output_examples" / project_id / "mvp.html"
    if not mvp_path.exists():
        raise HTTPException(status_code=404, detail="MVP not generated yet for this project")
    return HTMLResponse(mvp_path.read_text(encoding="utf-8"))


@app.get("/report/{run_id}", response_class=HTMLResponse)
async def serve_report(run_id: str) -> HTMLResponse:
    """Serve the generated HTML agent report for a run."""
    report_path = ROOT_DIR / "reports" / f"report_{run_id}.html"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for run {run_id}")
    return HTMLResponse(report_path.read_text(encoding="utf-8"))


def _open_mvp_in_browser(project_id: str, delay: float = 2.0) -> None:
    """Wait briefly then open the MVP in the default browser."""
    def _open():
        time.sleep(delay)
        url = f"http://localhost:8000/mvp/{project_id}"
        webbrowser.open(url)
        print(f"[MVP] Opened in browser: {url}")
    threading.Thread(target=_open, daemon=True).start()


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Multi-Agent PM System",
        "version": "1.0.0"
    }


@app.post("/run")
async def run_project(request: ProjectRequest) -> ExecutionResponse:
    """
    Run multi-agent project simulation and evaluation
    
    This endpoint:
    1. Creates a project with the specified parameters
    2. Initializes all agents (PM, Engineer, QA, Risk Analyst, Stakeholder)
    3. Runs the collaborative workflow with multiple feedback loops
    4. Evaluates results using Compass
    5. Returns complete execution trace and agent interactions
    
    The workflow includes:
    - Planning phase: Project planning and risk assessment
    - Execution phase: Multi-iteration development with QA feedback loops
    - Evaluation phase: Quality gate checks
    - Finalization: Compass submission and evaluation
    """
    try:
        # Resolve dual-schema: guide format (input/use_case_id) falls back when
        # domain fields (project_id/description) are not supplied.
        description = request.description or request.input
        project_id = request.project_id or request.use_case_id or ""
        project_name = request.project_name or project_id

        # SAMPLE_MODE: fill in missing fields from bundled sample project
        if SAMPLE_MODE and not description:
            project_id = project_id or _SAMPLE_PROJECT["project_id"]
            project_name = project_name or _SAMPLE_PROJECT["project_name"]
            description = _SAMPLE_PROJECT["description"]
            logger.info("SAMPLE_MODE: using sample project description")

        if not project_id or not description:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Provide project_id + description, or input + use_case_id, "
                    "or set SAMPLE_MODE=true"
                )
            )
        logger.info(f"Starting project execution: {project_id}")
        logger.info(f"Project: {project_name}")

        project = orchestrator.create_project(project_id, project_name, description)
        result = await orchestrator.run_workflow(project)

        logger.info(f"Project execution completed: {project_id}")

        # Persist full result to output_examples/output_{project_id}.json
        _save_output_json(result, project_id)

        output_app = _output_app_info(project_id)
        _print_output_app(output_app, project_id)
        _launch_output_app_async(output_app)

        # Auto-open MVP in browser if generated
        mvp_path = result.get("mvp_path", "")
        mvp_url = ""
        if mvp_path and Path(mvp_path).exists():
            mvp_url = f"http://localhost:8000/mvp/{project_id}"
            _open_mvp_in_browser(project_id)
            logger.info(f"MVP ready: {mvp_url}")

        # Report URL
        run_id = result.get("run_id", "")
        report_url = ""
        if run_id:
            report_file = ROOT_DIR / "reports" / f"report_{run_id}.html"
            if report_file.exists():
                report_url = f"http://localhost:8000/report/{run_id}"
                logger.info(f"Report ready: {report_url}")

        return ExecutionResponse(
            project_id=result["project_id"],
            trace_id=result.get("trace_id", ""),
            status="success",
            agents_used=result.get("agents_used", []),
            result=result.get("result", {}),
            collaboration=result.get("collaboration", {}),
            log_path=result.get("log_path", "logs/agent_trace.jsonl"),
            iterations=result["iterations"],
            compass_evaluation=result["compass_evaluation"],
            interactions=result["interactions"],
            output_app=output_app,
            mvp_url=mvp_url,
            report_url=report_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project execution failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Project execution failed: {str(e)}"
        )


@app.post("/run-sync")
def run_project_sync(request: ProjectRequest) -> ExecutionResponse:
    """
    Synchronous version of project execution endpoint
    """
    try:
        project_name = request.project_name or request.project_id
        logger.info(f"Starting synchronous project execution: {request.project_id}")

        project = orchestrator.create_project(
            request.project_id,
            project_name,
            request.description
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(orchestrator.run_workflow(project))
        loop.close()

        logger.info(f"Synchronous project execution completed: {request.project_id}")

        # Persist full result to output_examples/output_{project_id}.json
        _save_output_json(result, request.project_id)

        output_app = _output_app_info(request.project_id)
        _print_output_app(output_app, request.project_id)
        _launch_output_app_async(output_app)

        # Auto-open MVP in browser if generated
        mvp_path = result.get("mvp_path", "")
        mvp_url = ""
        if mvp_path and Path(mvp_path).exists():
            mvp_url = f"http://localhost:8000/mvp/{request.project_id}"
            _open_mvp_in_browser(request.project_id)
            logger.info(f"MVP ready: {mvp_url}")

        # Report URL
        run_id = result.get("run_id", "")
        report_url = ""
        if run_id:
            report_file = ROOT_DIR / "reports" / f"report_{run_id}.html"
            if report_file.exists():
                report_url = f"http://localhost:8000/report/{run_id}"
                logger.info(f"Report ready: {report_url}")

        return ExecutionResponse(
            project_id=result["project_id"],
            trace_id=result.get("trace_id", ""),
            status=result["status"],
            agents_used=result.get("agents_used", []),
            result=result.get("result", {}),
            collaboration=result.get("collaboration", {}),
            log_path=result.get("log_path", "logs/agent_trace.jsonl"),
            iterations=result["iterations"],
            compass_evaluation=result["compass_evaluation"],
            interactions=result["interactions"],
            output_app=output_app,
            mvp_url=mvp_url,
            report_url=report_url,
        )
        
    except Exception as e:
        logger.error(f"Synchronous project execution failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Project execution failed: {str(e)}"
        )


@app.get("/project/{project_id}")
async def get_project(project_id: str) -> Dict[str, Any]:
    """Get project details and current state"""
    try:
        project = memory.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return project.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/interactions/{project_id}")
async def get_interactions(project_id: str) -> Dict[str, Any]:
    """Get all agent interactions for a project"""
    try:
        interactions = memory.get_project_messages(project_id)
        return {
            "project_id": project_id,
            "interactions": interactions,
            "count": len(interactions)
        }
        
    except Exception as e:
        logger.error(f"Failed to get interactions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """Get current system status"""
    try:
        all_interactions = memory.get_all_interactions()
        
        return {
            "status": "running",
            "agents_initialized": len(orchestrator.agents),
            "projects": len(memory.projects),
            "total_messages": len(all_interactions["messages"]),
            "total_decisions": len(all_interactions["decisions"]),
            "feedback_loops": len(all_interactions["feedback_loops"]),
            "agents": list(orchestrator.agents.keys())
        }
        
    except Exception as e:
        logger.error(f"Failed to get status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset")
async def reset_system() -> Dict[str, str]:
    """Reset the system"""
    try:
        memory.clear()
        return {"status": "success", "message": "System reset complete"}
        
    except Exception as e:
        logger.error(f"Failed to reset system: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_cli(input_path: str, output_path: str) -> None:
    """CLI entry: run one project from a JSON file and write results."""
    with open(input_path, encoding="utf-8") as fh:
        payload = json.load(fh)

    cli_memory = SharedMemory()
    cli_orchestrator = AgentOrchestrator(cli_memory)
    cli_orchestrator.initialize_agents()

    project = cli_orchestrator.create_project(
        payload["project_id"],
        payload["project_name"],
        payload["description"],
    )
    result = await cli_orchestrator.run_workflow(project)

    out = json.dumps(result, indent=2, default=str)
    if output_path:
        Path(output_path).write_text(out, encoding="utf-8")
        print(f"Results written to {output_path}")
    else:
        print(out)

    print(f"\nAgent trace log: logs/agent_trace.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent PM System")
    parser.add_argument("--input", "-i", help="Path to input JSON file")
    parser.add_argument("--output", "-o", default="", help="Path to output JSON file")
    parser.add_argument("--server", action="store_true", help="Start HTTP server (default if no --input)")
    args = parser.parse_args()

    if args.input:
        asyncio.run(_run_cli(args.input, args.output))
    else:
        logger.info("Starting Multi-Agent PM System API Server")
        logger.info("Server: http://0.0.0.0:8000  |  Docs: http://0.0.0.0:8000/docs")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info",
                    timeout_keep_alive=300, h11_max_incomplete_event_size=16*1024*1024)
