"""Engineer Agent – writes real source files and revises based on QA critique."""
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from base_agent import BaseAgent
from data_types import AgentRole, Project, Task, TaskStatus
from logging_config import log_agent_action
from memory import SharedMemory
from public_data import PackageHealthClient, extract_tech_keywords

_pkg_health = PackageHealthClient()


# Packages that must never appear in generated package.json files.
_BANNED_PACKAGES = {
    # Frameworks that aren't plain React/Vite/webpack
    "next", "next-themes", "eslint-config-next", "next-auth",
    "gatsby", "remix", "nuxt", "@remix-run/react",
    # Toast / notification libraries
    "react-toastify", "react-hot-toast", "sonner", "notistack",
    # Component / design-system libraries
    "@mui/material", "@emotion/react", "@emotion/styled", "@mui/icons-material",
    "antd", "@ant-design/icons",
    "@chakra-ui/react", "@chakra-ui/icons",
    "bootstrap", "reactstrap", "react-bootstrap",
    "tailwindcss", "@headlessui/react", "@heroicons/react",
    "semantic-ui-react", "primereact", "mantine", "shadcn",
    # Animation libraries
    "framer-motion", "react-spring",
    # Heavy state / data libraries
    "zustand", "jotai", "recoil", "mobx",
    "@tanstack/react-query", "@tanstack/query-core",
    "redux", "@reduxjs/toolkit", "react-redux",
    # Form / validation libraries
    "react-hook-form", "@hookform/resolvers", "formik", "yup", "zod",
    # Chart / visualization libraries
    "recharts", "chart.js", "react-chartjs-2", "d3",
    # Other heavy packages unlikely to install cleanly
    "puppeteer", "playwright", "electron",
}

# Pinned versions for packages the Engineer is allowed to use.
_SAFE_VERSIONS: Dict[str, str] = {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "styled-components": "^6.1.0",
    "typescript": "^5.2.2",
    "vite": "^5.0.0",
    "@vitejs/plugin-react-swc": "^3.5.0",
    "@vitejs/plugin-react": "^4.2.0",
    "@types/react": "^18.2.14",
    "@types/react-dom": "^18.2.7",
    "@types/styled-components": "^5.1.26",
    "webpack": "^5.88.2",
    "webpack-cli": "^5.1.4",
    "webpack-dev-server": "^4.15.1",
    "ts-loader": "^9.4.4",
    "css-loader": "^6.8.1",
    "style-loader": "^3.3.3",
    "html-webpack-plugin": "^5.5.3",
    "eslint": "^8.47.0",
    "eslint-plugin-react": "^7.33.2",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
}


def _sanitize_package_json(content: str) -> str:
    """Remove banned packages and fix pinned versions in a package.json string."""
    try:
        pkg = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content

    changed = False
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps: Dict[str, str] = pkg.get(section, {})
        if not isinstance(deps, dict):
            continue
        to_remove = [k for k in deps if k in _BANNED_PACKAGES]
        for k in to_remove:
            print(f"[Engineer] Removed banned package '{k}' from {section}")
            del deps[k]
            changed = True
        # Pin versions for known-safe packages
        for name, safe_ver in _SAFE_VERSIONS.items():
            if name in deps and deps[name] != safe_ver:
                print(f"[Engineer] Pinned {name} {deps[name]} -> {safe_ver}")
                deps[name] = safe_ver
                changed = True

    if changed:
        return json.dumps(pkg, indent=2)
    return content


_MVP_SYSTEM = """You are a Senior Frontend Engineer. Generate a compact, professional self-contained HTML dashboard MVP.

Return ONLY valid JSON (no markdown fences):
{
  "html_content": "<!DOCTYPE html>\\n<html lang=\\"en\\">...",
  "mvp_description": "2 sentences describing what the MVP does",
  "features_implemented": ["Feature 1", "Feature 2", "Feature 3"]
}

REQUIREMENTS for the HTML:
- Single file: ALL CSS in <style>, ALL JS in <script> — zero external files or CDN links
- Dark theme: body background #0f172a, cards #1e293b, text #e2e8f0, accent #2563eb
- Font: Inter, system-ui, sans-serif
- Fixed left sidebar (180px) + scrollable main area (CSS flex)
- Page header with project title and a coloured status badge
- 4 KPI stat cards in a row (emoji icon + number + label), domain-specific
- One data table with 5-7 mock rows matching the project domain, with status chips
- One action button (Add) that uses window.prompt() to append a row — keep JS minimal
- Use standard JSON escaping: \\n for newlines, \\" for quotes inside html_content"""


_CODE_GEN_SYSTEM = """You are a Senior Engineer. Describe the implementation plan for this task.

Return ONLY valid JSON (no markdown fences):
{
  "files": [],
  "implementation_summary": "What was built — 2 concise sentences",
  "technical_approach": "Key design decision in 1 sentence",
  "components_created": ["ComponentA"],
  "potential_issues": [],
  "confidence": 0.88
}

Keep implementation_summary under 200 characters. Only include files[] if you have very short
config/type files to show (max 1 file, max 30 lines). No full source implementations."""


_CODE_REVISE_SYSTEM = """You are a Senior Engineer. QA flagged issues — describe how you fixed them.

Return ONLY valid JSON (no markdown fences):
{
  "files": [],
  "revision_summary": "What changed — 1-2 concise sentences",
  "issues_addressed": ["Issue fixed by doing X"],
  "remaining_concerns": [],
  "confidence": 0.87
}

Keep revision_summary under 200 characters. No full source code needed."""


class EngineerAgent(BaseAgent):
    """Implements tasks by writing real source files; revises on QA critique."""

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(AgentRole.ENGINEER, memory)
        self.implementation_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # File writing
    # ------------------------------------------------------------------

    def _write_files(
        self, project_id: str, files: List[Dict[str, str]]
    ) -> List[str]:
        """Write files to output_examples/{project_id}/spa/ and return written paths."""
        if not files:
            return []
        output_dir = Path("output_examples") / project_id / "spa"
        written: List[str] = []
        for f in files:
            if not isinstance(f, dict):
                continue
            rel_path = f.get("path", "")
            content = f.get("content", "")
            if not rel_path or not content:
                continue
            if Path(rel_path).name == "package.json":
                content = _sanitize_package_json(content)
            target = output_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel_path)
        return written

    def _load_file_index(self, project_id: str) -> List[str]:
        raw = self.memory.get_summary(self.role, f"{project_id}:file_index")
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _save_file_index(self, project_id: str, paths: List[str]) -> None:
        self.memory.store_summary(
            self.role, f"{project_id}:file_index", json.dumps(paths)
        )

    # ------------------------------------------------------------------
    # Main task implementation
    # ------------------------------------------------------------------

    async def process_task(self, task: Task, project: Project) -> str:
        """Implement a task: call LLM for code, write files, notify QA."""
        pm_plan = self.memory.get_summary(AgentRole.PROJECT_MANAGER, project.id)
        risk_summary = self.memory.get_summary(AgentRole.RISK_ANALYST, project.id)
        file_index = self._load_file_index(project.id)

        # --- npm/PyPI real public data: library health check ---
        pkg_context = ""
        try:
            tech_text = f"{project.description} {task.description} {pm_plan}"
            tech_kw = extract_tech_keywords(tech_text)
            health = await asyncio.wait_for(
                _pkg_health.check_libraries(tech_kw), timeout=10.0
            )
            pkg_context = _pkg_health.format_for_context(health)
            project.metadata["package_health"] = {
                "checked_packages": [p["name"] for p in health.get("packages_checked", [])],
                "warnings": health.get("warnings", []),
                "sources": health.get("sources", []),
            }
            if health.get("warnings"):
                project.metadata["package_health_warnings"] = health["warnings"]
            self.memory.update_project(project.id, {"metadata": project.metadata})
        except Exception:
            pass  # network failure is non-fatal

        context = (
            f"Project: {project.name}\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Acceptance criteria: {json.dumps(task.metadata.get('acceptance_criteria', []))}\n"
            f"Files already written in this project: {json.dumps(file_index)}\n"
            f"PM plan context: {pm_plan[:300]}\n"
            f"Risk warnings: {risk_summary[:200]}"
            + (f"\n\n{pkg_context}" if pkg_context else "")
        )

        self.log_trace(
            "start_implementation",
            f"Task: {task.title}",
            "Calling LLM for code generation...",
            target_agent=None,
            confidence=0.88,
            status="success",
        )

        llm_result = await self.llm_decide(
            _CODE_GEN_SYSTEM, context, max_tokens=800
        )

        impl_summary = llm_result.get(
            "implementation_summary", f"Implemented {task.title}"
        )
        tech_approach = llm_result.get("technical_approach", "Standard approach.")
        potential_issues = llm_result.get("potential_issues", [])
        confidence = float(llm_result.get("confidence", 0.82))
        files = llm_result.get("files", [])

        # Write files to disk
        written = self._write_files(project.id, files)
        if written:
            updated_index = file_index + [p for p in written if p not in file_index]
            self._save_file_index(project.id, updated_index)

        files_note = (
            f" Wrote {len(written)} file(s): {', '.join(written[:4])}"
            if written
            else ""
        )

        # Store implementation payload for QA to read
        impl_payload = json.dumps({
            "task_id": task.id,
            "task_title": task.title,
            "summary": impl_summary,
            "technical_approach": tech_approach,
            "potential_issues": potential_issues,
            "files_written": written,
            "package_health_warnings": project.metadata.get("package_health_warnings", []),
            "package_health": project.metadata.get("package_health", {}),
        })
        self.memory.store_summary(self.role, task.id, impl_payload)

        output_summary = f"Implemented '{task.title}': {impl_summary[:100]}{files_note}"

        self.log_trace(
            "produce_implementation",
            f"Task: {task.title}",
            output_summary,
            target_agent="qa",
            confidence=confidence,
            status="success",
        )
        self.make_decision(f"Implement {task.title}", tech_approach, project.id)

        self.send_message(
            AgentRole.QA,
            f"Implementation of '{task.title}' ready for QA review.{files_note} "
            f"Summary: {impl_summary[:120]}",
            "request",
            project.id,
        )

        self.implementation_history.append({
            "task": task.id,
            "summary": impl_summary,
            "files": written,
        })

        task.status = TaskStatus.COMPLETED
        task.result = output_summary
        self.update_task(
            project.id, task.id,
            {"status": TaskStatus.COMPLETED, "result": output_summary},
        )

        log_agent_action(
            self.logger, self.role.value, "implement_task",
            {"task": task.title, "files_written": len(written), "confidence": confidence},
            project.id,
        )
        return output_summary

    # ------------------------------------------------------------------
    # Revision after QA critique
    # ------------------------------------------------------------------

    async def revise_implementation(
        self,
        task: Task,
        project: Project,
        qa_issues: List[Dict[str, Any]],
        retry_count: int,
    ) -> str:
        """Revise code files after QA critique; write updated files to disk."""
        qa_critique = self.memory.get_summary(AgentRole.QA, task.id)
        prev_impl = self.memory.get_summary(self.role, task.id)
        file_index = self._load_file_index(project.id)

        context = (
            f"Project: {project.name}\nTask: {task.title}\n"
            f"Previous implementation: {prev_impl[:400]}\n"
            f"QA critique: {qa_critique[:400]}\n"
            f"Issues to fix: {json.dumps(qa_issues[:3])}\n"
            f"Files in project so far: {json.dumps(file_index)}"
        )

        self.log_trace(
            "start_revision",
            f"Addressing {len(qa_issues)} QA issue(s) in '{task.title}'",
            "Calling LLM for revised code...",
            target_agent=None,
            confidence=0.80,
            retry_count=retry_count,
            status="success",
        )

        llm_result = await self.llm_decide(
            _CODE_REVISE_SYSTEM, context, max_tokens=600
        )

        revision_summary = llm_result.get("revision_summary", "Issues addressed.")
        issues_addressed = llm_result.get(
            "issues_addressed", [str(i) for i in qa_issues]
        )
        confidence = float(llm_result.get("confidence", 0.84))
        files = llm_result.get("files", [])

        # Overwrite files with the revised versions
        written = self._write_files(project.id, files)
        if written:
            updated_index = file_index + [p for p in written if p not in file_index]
            self._save_file_index(project.id, updated_index)

        files_note = (
            f" Revised {len(written)} file(s): {', '.join(written[:4])}"
            if written
            else ""
        )

        revised_payload = json.dumps({
            "task_id": task.id,
            "task_title": task.title,
            "summary": revision_summary,
            "issues_addressed": issues_addressed,
            "revision": retry_count,
            "files_revised": written,
        })
        self.memory.store_summary(self.role, task.id, revised_payload)

        output_summary = (
            f"Revised '{task.title}' (attempt {retry_count}): "
            f"{revision_summary[:100]}{files_note}"
        )

        self.log_trace(
            "revise_implementation",
            f"QA issues: {[i.get('description', str(i)) for i in qa_issues[:2]]}",
            output_summary,
            target_agent="qa",
            confidence=confidence,
            retry_count=retry_count,
            status="success",
        )
        self.make_decision(
            f"Revise {task.title} (attempt {retry_count})",
            f"Addressed: {'; '.join(issues_addressed[:2])}",
            project.id,
        )

        self.send_message(
            AgentRole.QA,
            f"Revision {retry_count} of '{task.title}' ready.{files_note} "
            f"Addressed: {'; '.join(issues_addressed[:2])}",
            "feedback",
            project.id,
        )

        self.memory.log_feedback_loop(
            AgentRole.ENGINEER, AgentRole.QA,
            f"Revision {retry_count}: {revision_summary[:100]}",
            project.id, retry_count,
        )

        log_agent_action(
            self.logger, self.role.value, "revise_implementation",
            {"task": task.title, "retry": retry_count, "files_revised": len(written)},
            project.id,
        )
        return output_summary

    # ------------------------------------------------------------------
    # MVP generation
    # ------------------------------------------------------------------

    async def generate_mvp_html(self, project: Project) -> str:
        """Generate a self-contained HTML MVP and write it to output_examples/{project_id}/mvp.html."""
        pm_plan = self.memory.get_summary(AgentRole.PROJECT_MANAGER, project.id)

        context = (
            f"Project Name: {project.name}\n"
            f"Project Description: {project.description}\n"
            f"PM Plan & Tech Stack: {pm_plan[:500]}"
        )

        self.log_trace(
            "generate_mvp",
            f"Project: {project.name}",
            "Calling LLM for self-contained HTML MVP...",
            confidence=0.88,
            status="success",
        )

        llm_result = await self.llm_decide(_MVP_SYSTEM, context, max_tokens=3500)

        html_content = llm_result.get("html_content", "")
        features = llm_result.get("features_implemented", [])
        mvp_desc = llm_result.get("mvp_description", "")

        # Some LLMs over-escape JSON strings — normalise backslash sequences
        if html_content and "\\n" in html_content:
            html_content = (
                html_content
                .replace("\\n", "\n")
                .replace('\\"', '"')
                .replace("\\'", "'")
                .replace("\\t", "\t")
            )

        if not html_content or not html_content.strip().startswith("<!"):
            self.logger.warning("MVP generation returned empty or invalid HTML")
            return ""

        output_dir = Path("output_examples") / project.id
        output_dir.mkdir(parents=True, exist_ok=True)
        mvp_path = output_dir / "mvp.html"
        mvp_path.write_text(html_content, encoding="utf-8")

        self.log_trace(
            "mvp_written",
            f"Features: {features}",
            f"MVP saved to {mvp_path} ({len(html_content)} bytes). {mvp_desc[:120]}",
            confidence=0.90,
            status="success",
        )

        self.make_decision(
            "Generate MVP",
            f"Self-contained HTML MVP created with {len(features)} feature(s): "
            + ", ".join(features[:3]),
            project.id,
        )

        log_agent_action(
            self.logger, self.role.value, "generate_mvp",
            {"project": project.name, "features": len(features), "bytes": len(html_content)},
            project.id,
        )
        return str(mvp_path)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_next_actions(self, project: Project) -> List[Task]:
        eng_tasks = self.memory.get_agent_tasks(AgentRole.ENGINEER, project.id)
        pending = [t for t in eng_tasks if t.status == TaskStatus.PENDING]
        in_progress = [t for t in eng_tasks if t.status == TaskStatus.IN_PROGRESS]
        return (pending + in_progress)[:2]

    def identify_blockers(self, project: Project) -> List[Dict[str, Any]]:
        blockers = []
        for task in project.tasks:
            if task.assigned_to == AgentRole.ENGINEER:
                unmet = [
                    dep for dep in task.dependencies
                    if not any(
                        t.id == dep and t.status == TaskStatus.COMPLETED
                        for t in project.tasks
                    )
                ]
                if unmet:
                    blockers.append({
                        "task": task.title,
                        "blocker": f"Waiting for: {unmet}",
                        "severity": "high" if len(unmet) > 1 else "medium",
                    })
        if blockers:
            self.escalate_issue(
                project.id,
                f"{len(blockers)} implementation blocker(s)",
                AgentRole.PROJECT_MANAGER,
            )
        return blockers
