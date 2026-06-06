#!/usr/bin/env python
"""
Standalone test runner for multi-agent PM system
Executes a sample project without needing FastAPI server
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from memory import SharedMemory
from orchestrator import AgentOrchestrator
from data_types import Project


async def run_test_project():
    """Run a test project execution"""
    
    print("\n" + "="*80)
    print("MULTI-AGENT PM SYSTEM - TEST EXECUTION")
    print("="*80 + "\n")
    
    # Create shared memory and orchestrator
    memory = SharedMemory()
    orchestrator = AgentOrchestrator(memory)
    orchestrator.initialize_agents()
    
    # Define test project
    project_id = "test_webapp_001"
    project_name = "E-Commerce Web Application"
    description = "Build a complete e-commerce web application with product catalog, shopping cart, and checkout"
    
    print(f"📋 PROJECT DETAILS")
    print(f"  ID: {project_id}")
    print(f"  Name: {project_name}")
    print(f"  Description: {description}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Create project
        print("🏗️  Creating project...")
        project = orchestrator.create_project(project_id, project_name, description)
        print(f"✓ Project created successfully")
        print()
        
        # Run workflow
        print("⚙️  Running multi-agent workflow...")
        print("-" * 80)
        result = await orchestrator.run_workflow(project)
        print("-" * 80)
        print()
        
        # Display results
        print("📊 EXECUTION RESULTS")
        print(f"  Status: {result['status']}")
        print(f"  Iterations: {result['iterations']}")
        print()
        
        # Show interactions summary
        interactions = result.get("interactions", {})
        messages = interactions.get("messages", [])
        decisions = interactions.get("decisions", [])
        
        print(f"📞 AGENT INTERACTIONS")
        print(f"  Total Messages: {len(messages)}")
        print(f"  Decision Points: {len(decisions)}")
        print()
        
        if messages:
            print(f"📬 Message Exchange Details:")
            for i, msg in enumerate(messages[:10], 1):  # Show first 10 messages
                timestamp = msg.get("timestamp", "N/A")
                sender = msg.get("sender", "Unknown")
                receiver = msg.get("receiver", "Unknown")
                content = msg.get("content", "")[:60]
                print(f"  {i}. [{timestamp}] {sender} → {receiver}")
                print(f"     {content}...")
        print()
        
        # Show compass evaluation
        compass_eval = result.get("compass_evaluation", {})
        print(f"🧭 COMPASS EVALUATION")
        print(f"  Status: {compass_eval.get('status', 'Unknown')}")
        if compass_eval.get('score'):
            print(f"  Score: {compass_eval.get('score')}")
        if compass_eval.get('feedback'):
            print(f"  Feedback: {compass_eval.get('feedback')}")
        print()
        
        # Show project state
        print(f"📋 PROJECT STATE")
        print(f"  Status: {project.status}")
        print(f"  Total Tasks: {len(project.tasks)}")
        if project.tasks:
            print(f"  Task Breakdown:")
            for task in project.tasks[:5]:
                status_emoji = "✓" if task.status == "completed" else "○" if task.status == "pending" else "◐"
                print(f"    {status_emoji} {task.title} [{task.status}]")
                if len(project.tasks) > 5:
                    print(f"    ... and {len(project.tasks) - 5} more tasks")
        print()
        
        # Show execution timeline
        print(f"⏱️  EXECUTION PHASES")
        print(f"  ✓ Planning Phase")
        print(f"  ✓ Execution Phase (Iterations: {result['iterations']})")
        print(f"  ✓ Evaluation Phase")
        print(f"  ✓ Finalization Phase")
        print()
        
        # Complete response JSON
        print("="*80)
        print("COMPLETE API RESPONSE (JSON)")
        print("="*80)
        print(json.dumps(result, indent=2, default=str))
        print()
        
        # Save to file
        output_file = Path(__file__).parent / "test_output.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"✓ Results saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "="*80)
    print("TEST EXECUTION COMPLETED SUCCESSFULLY")
    print("="*80 + "\n")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_test_project())
    sys.exit(exit_code)
