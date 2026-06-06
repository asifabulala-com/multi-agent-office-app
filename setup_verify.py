#!/usr/bin/env python
"""
Setup and verification script for Multi-Agent PM System

Run this script to:
1. Verify all required files exist
2. Check dependencies
3. Test basic functionality
4. Generate setup summary
"""

import os
import sys
import json
from pathlib import Path

def check_file_exists(file_path: str, file_type: str = "file") -> bool:
    """Check if a file or directory exists"""
    path = Path(file_path)
    if file_type == "dir":
        exists = path.is_dir()
    else:
        exists = path.is_file()
    
    status = "✓" if exists else "✗"
    print(f"  {status} {file_path}")
    return exists

def verify_structure():
    """Verify project structure"""
    print("\n=== VERIFYING PROJECT STRUCTURE ===\n")
    
    required_files = {
        "Core Files": [
            "run.py",
            "requirements.txt",
            ".env",
            ".gitignore",
            "__init__.py",
        ],
        "Agent Implementation": [
            "base_agent.py",
            "project_manager.py",
            "engineer.py",
            "qa_agent.py",
            "risk_analyst.py",
            "stakeholder.py",
        ],
        "System Components": [
            "orchestrator.py",
            "memory.py",
            "types.py",
            "compass_integration.py",
            "logging_config.py",
        ],
        "Documentation": [
            "README.md",
            "QUICKSTART.md",
            "docs/ARCHITECTURE.md",
            "docs/AGENTS.md",
            "docs/COLLABORATION.md",
            "docs/API.md",
            "docs/STRONG_COLLABORATION.md",
        ],
    }
    
    all_exist = True
    for category, files in required_files.items():
        print(f"{category}:")
        for file in files:
            if not check_file_exists(file):
                all_exist = False
        print()
    
    return all_exist

def verify_imports():
    """Verify all imports work"""
    print("=== VERIFYING IMPORTS ===\n")
    
    imports = [
        "types",
        "memory",
        "logging_config",
        "base_agent",
        "project_manager",
        "engineer",
        "qa_agent",
        "risk_analyst",
        "stakeholder",
        "compass_integration",
        "orchestrator",
    ]
    
    failed = []
    for module in imports:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except Exception as e:
            print(f"  ✗ {module}: {str(e)}")
            failed.append(module)
    
    print()
    return len(failed) == 0, failed

def check_dependencies():
    """Check if required packages are installed"""
    print("=== CHECKING DEPENDENCIES ===\n")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "httpx",
        "aiohttp",
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} (not installed)")
            missing.append(package)
    
    print()
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt\n")
    
    return len(missing) == 0

def generate_summary():
    """Generate project summary"""
    print("=== PROJECT SUMMARY ===\n")
    
    summary = {
        "Project": "Multi-Agent Office and Team Simulation System",
        "Version": "1.0.0",
        "Agents": 5,
        "Agent Types": [
            "Project Manager",
            "Engineer",
            "QA",
            "Risk Analyst",
            "Stakeholder"
        ],
        "Key Features": [
            "Multi-agent collaboration with feedback loops",
            "Iterative refinement and quality gates",
            "Escalation chains and decision-making",
            "Shared memory system",
            "Compass integration",
            "Comprehensive logging",
            "FastAPI server on port 8000",
            "Complete documentation"
        ],
        "Files": {
            "Python Modules": 13,
            "Documentation Files": 6,
            "Configuration Files": 3,
        },
        "API Endpoints": [
            "GET /health",
            "POST /run (async)",
            "POST /run-sync",
            "GET /project/{id}",
            "GET /interactions/{id}",
            "GET /status",
            "POST /reset"
        ],
        "Documentation": [
            "README.md - Main documentation",
            "QUICKSTART.md - Quick setup guide",
            "docs/ARCHITECTURE.md - System design",
            "docs/AGENTS.md - Agent specifications",
            "docs/COLLABORATION.md - Collaboration patterns",
            "docs/API.md - API endpoints",
            "docs/STRONG_COLLABORATION.md - Why it's strong"
        ]
    }
    
    print(json.dumps(summary, indent=2))
    print()

def main():
    """Main verification routine"""
    print("\n" + "="*50)
    print("MULTI-AGENT PM SYSTEM - SETUP VERIFICATION")
    print("="*50 + "\n")
    
    # Check structure
    structure_ok = verify_structure()
    
    # Check dependencies
    deps_ok = check_dependencies()
    
    # Check imports
    imports_ok, failed_imports = verify_imports()
    
    # Generate summary
    generate_summary()
    
    # Final status
    print("=== SETUP STATUS ===\n")
    
    if structure_ok and deps_ok and imports_ok:
        print("✓ All checks passed!")
        print("\nNext steps:")
        print("1. python run.py          # Start the API server")
        print("2. curl http://localhost:8000/health  # Test health endpoint")
        print("3. curl http://localhost:8000/docs    # View API documentation")
        print("4. Read docs/QUICKSTART.md for detailed instructions")
        return 0
    else:
        print("✗ Some checks failed:")
        if not structure_ok:
            print("  - Missing required files")
        if not deps_ok:
            print("  - Missing dependencies: pip install -r requirements.txt")
        if failed_imports:
            print(f"  - Import errors: {', '.join(failed_imports)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
