"""Public data integration — O*NET, BLS, NIST NVD, npm/PyPI.

Real public data sources used to enrich agent reasoning:

  ONetClient        — O*NET 28.3 Database (U.S. Dept of Labor, CC BY 4.0)
                      Workforce risk: talent pool, demand, availability per technology.
                      Used by: Risk Analyst (resource availability risk)

  BLSClient         — BLS OES May 2023 (U.S. Dept of Labor, Public Domain)
                      Occupation wages for project cost estimation.
                      Used by: Project Manager (team cost in project plan)

  NISTCVEClient     — NIST National Vulnerability Database REST API 2.0 (Public Domain)
                      Known CVEs for technologies in the project stack.
                      Used by: Risk Analyst (security risk) + QA Agent (critique context)

  PackageHealthClient — npm Registry API + PyPI JSON API (both public, no auth)
                      Library maintenance health: last release, download volume.
                      Used by: Engineer (library validation before implementation)
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ── Bundled data paths ────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"
_ONET_PATH = _DATA_DIR / "onet_tech_skills.json"
_BLS_PATH  = _DATA_DIR / "bls_wage_data.json"

_AVAILABILITY_RISK_LABEL = {
    "low":    "LOW — large talent pool, readily available",
    "medium": "MEDIUM — moderate competition for skilled developers",
    "high":   "HIGH — limited specialists, expect recruitment delays",
}
_DEMAND_LABEL = {"very_high": "Very High", "high": "High", "medium": "Medium", "low": "Low"}


# ══════════════════════════════════════════════════════════════════════════════
# ONetClient — O*NET 28.3 workforce intelligence
# ══════════════════════════════════════════════════════════════════════════════

class ONetClient:
    """O*NET 28.3 Database — talent pool, demand, availability risk per technology.

    Ships bundled data so it works with zero credentials.
    Set ONET_USERNAME + ONET_PASSWORD for live O*NET Web Services lookups.
    """

    def __init__(self) -> None:
        self._username = os.getenv("ONET_USERNAME", "")
        self._password = os.getenv("ONET_PASSWORD", "")
        self._bundled: Dict[str, Any] = self._load_json(_ONET_PATH, {"technologies": []})

    def assess_tech_stack(self, tech_keywords: List[str]) -> Dict[str, Any]:
        findings, high_risk, medium_risk = [], [], []
        for kw in tech_keywords:
            m = self._match(kw)
            if not m:
                continue
            findings.append({
                "technology":         m["name"],
                "demand_level":       _DEMAND_LABEL.get(m["demand_level"], m["demand_level"]),
                "talent_pool":        m["talent_pool"],
                "availability_risk":  _AVAILABILITY_RISK_LABEL.get(m["availability_risk"], m["availability_risk"]),
                "occupation_count":   m["occupation_count"],
                "notes":              m["notes"],
            })
            if m["availability_risk"] == "high":
                high_risk.append(m["name"])
            elif m["availability_risk"] == "medium":
                medium_risk.append(m["name"])

        overall = "high" if len(high_risk) >= 2 else ("medium" if high_risk or len(medium_risk) >= 2 else "low")
        src = self._bundled.get("source", "O*NET 28.3 Database")
        return {
            "findings": findings,
            "technologies_matched": len(findings),
            "high_risk_technologies": high_risk,
            "medium_risk_technologies": medium_risk,
            "overall_resource_risk": overall,
            "citation": (
                f"Source: {src} — {self._bundled.get('attribution', 'U.S. Dept of Labor, ETA')}. "
                f"License: {self._bundled.get('license', 'CC BY 4.0')}."
            ),
        }

    def format_for_risk_context(self, tech_keywords: List[str]) -> str:
        r = self.assess_tech_stack(tech_keywords)
        if not r["findings"]:
            return ""
        lines = ["=== O*NET WORKFORCE INTELLIGENCE (real public data) ===",
                 f"Source: O*NET 28.3 Database, U.S. Dept of Labor (CC BY 4.0)", ""]
        for f in r["findings"]:
            lines.append(f"• {f['technology']}: demand={f['demand_level']}, "
                         f"pool={f['talent_pool']}, risk={f['availability_risk'].split('—')[0].strip()}")
        if r["high_risk_technologies"]:
            lines.append(f"\nHIGH availability risk: {', '.join(r['high_risk_technologies'])}"
                         " — specialized skills with limited supply.")
        lines.append(f"Overall resource risk: {r['overall_resource_risk'].upper()}")
        lines.append("=== END O*NET DATA ===")
        return "\n".join(lines)

    def _match(self, keyword: str) -> Optional[Dict[str, Any]]:
        kw = keyword.lower().strip()
        for t in self._bundled.get("technologies", []):
            if kw == t["name"].lower():
                return t
            if any(kw in a or a in kw for a in t.get("aliases", [])):
                return t
        return None

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


# ══════════════════════════════════════════════════════════════════════════════
# BLSClient — BLS OES May 2023 wage data
# ══════════════════════════════════════════════════════════════════════════════

class BLSClient:
    """U.S. Bureau of Labor Statistics OES May 2023 — annual wages by occupation.

    Public domain. https://www.bls.gov/oes/
    """

    def __init__(self) -> None:
        self._data: Dict[str, Any] = self._load()
        self._by_soc: Dict[str, Dict[str, Any]] = {
            o["soc_code"]: o for o in self._data.get("occupations", [])
        }
        self._role_map: Dict[str, str] = self._data.get("role_mapping", {})

    def estimate_project_cost(self, team_size: int, roles: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return annual team cost estimate based on BLS median wages.

        roles: list of agent role strings e.g. ["engineer","qa","engineer","devops"]
        Falls back to team_size × software developer median if roles not given.
        """
        if not roles:
            roles = ["engineer"] * team_size

        breakdown: List[Dict[str, Any]] = []
        total = 0
        for role in roles:
            soc = self._role_map.get(role, "15-1252")
            occ = self._by_soc.get(soc, {})
            wage = occ.get("annual_median_wage", 124200)
            breakdown.append({
                "role":   role,
                "occupation": occ.get("title", "Software Developer"),
                "soc_code":   soc,
                "annual_median_wage_usd": wage,
            })
            total += wage

        return {
            "team_size": len(roles),
            "estimated_annual_cost_usd": total,
            "estimated_annual_cost_formatted": f"${total:,.0f}",
            "breakdown": breakdown,
            "source": self._data.get("source", "BLS OES May 2023"),
            "survey": self._data.get("survey", "May 2023"),
            "bls_url": self._data.get("url", "https://www.bls.gov/oes/"),
            "license": self._data.get("license", "Public Domain — U.S. Government work"),
        }

    def format_for_plan_context(self, team_size: int, roles: Optional[List[str]] = None) -> str:
        r = self.estimate_project_cost(team_size, roles)
        lines = [
            "=== BLS WAGE DATA — PROJECT COST ESTIMATE (real public data) ===",
            f"Source: {r['source']} | {r['bls_url']}",
            f"Team size: {r['team_size']} people",
            f"Estimated annual team cost: {r['estimated_annual_cost_formatted']} (USD, BLS median wages)",
        ]
        for b in r["breakdown"]:
            lines.append(f"  • {b['occupation']} (SOC {b['soc_code']}): ${b['annual_median_wage_usd']:,.0f}/yr")
        lines.append("=== END BLS DATA ===")
        return "\n".join(lines)

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(_BLS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"occupations": [], "role_mapping": {}}


# ══════════════════════════════════════════════════════════════════════════════
# NISTCVEClient — NIST National Vulnerability Database REST API 2.0
# ══════════════════════════════════════════════════════════════════════════════

class NISTCVEClient:
    """NIST NVD REST API 2.0 — publicly known CVEs for technology keywords.

    Public domain. https://nvd.nist.gov/developers/vulnerabilities
    No API key required (rate-limited to 5 req/30s; set NIST_API_KEY for higher limits).
    """

    _BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    _TIMEOUT = 5.0
    _MAX_RESULTS = 3

    # Technologies worth checking (excludes generic terms that produce noisy results)
    _CHECKABLE = {
        "python", "fastapi", "django", "flask", "spring", "node.js", "express",
        "react", "vue", "angular", "postgresql", "mysql", "redis", "mongodb",
        "servicenow", "salesforce", "sap", "kafka", "docker", "kubernetes",
        "terraform", "aws", "azure", "jenkins", "gitlab", "nginx", "apache",
    }

    def __init__(self) -> None:
        self._api_key = os.getenv("NIST_API_KEY", "")

    async def check_tech_stack(self, tech_keywords: List[str]) -> Dict[str, Any]:
        """Fetch recent HIGH/CRITICAL CVEs for up to 3 technologies in the stack."""
        checkable = [t for t in tech_keywords if t.lower() in self._CHECKABLE][:3]
        if not checkable:
            return {"cves_found": [], "checked": [], "source": "NIST NVD", "error": None}

        all_cves: List[Dict[str, Any]] = []
        errors: List[str] = []
        headers = {"apiKey": self._api_key} if self._api_key else {}

        async with httpx.AsyncClient(timeout=self._TIMEOUT, verify=False) as client:
            for tech in checkable:
                try:
                    resp = await client.get(
                        self._BASE,
                        params={
                            "keywordSearch": tech,
                            "resultsPerPage": self._MAX_RESULTS,
                            "cvssV3Severity": "HIGH",
                        },
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("vulnerabilities", []):
                            cve = item.get("cve", {})
                            cve_id = cve.get("id", "")
                            desc = next(
                                (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"),
                                ""
                            )
                            metrics = cve.get("metrics", {})
                            severity = "UNKNOWN"
                            score = None
                            for v in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                                if v in metrics and metrics[v]:
                                    cvss = metrics[v][0].get("cvssData", {})
                                    severity = cvss.get("baseSeverity", severity)
                                    score = cvss.get("baseScore", score)
                                    break
                            if cve_id:
                                all_cves.append({
                                    "cve_id":      cve_id,
                                    "technology":  tech,
                                    "severity":    severity,
                                    "score":       score,
                                    "description": desc[:200],
                                    "url":         f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                                })
                    await asyncio.sleep(0.7)  # respect rate limit
                except Exception as exc:
                    errors.append(f"{tech}: {exc}")

        critical = [c for c in all_cves if c["severity"] in ("CRITICAL", "HIGH")]
        return {
            "cves_found": critical[:6],
            "total_found": len(critical),
            "checked_technologies": checkable,
            "source": "NIST National Vulnerability Database (NVD) REST API 2.0",
            "url": "https://nvd.nist.gov/",
            "license": "Public Domain — U.S. Government work",
            "errors": errors,
        }

    def format_for_context(self, cve_result: Dict[str, Any]) -> str:
        cves = cve_result.get("cves_found", [])
        if not cves:
            return ""
        lines = [
            "=== NIST NVD SECURITY DATA (real public data) ===",
            f"Source: {cve_result['source']} | {cve_result['url']}",
            f"HIGH/CRITICAL CVEs found for stack technologies:",
        ]
        for c in cves[:4]:
            lines.append(f"• {c['cve_id']} [{c['severity']}] ({c['technology']}): {c['description'][:120]}")
        lines.append("=== END NIST DATA ===")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# PackageHealthClient — npm Registry + PyPI JSON API
# ══════════════════════════════════════════════════════════════════════════════

class PackageHealthClient:
    """npm Registry API + PyPI JSON API — package maintenance health checks.

    Both APIs are public and require no authentication.
    npm:  https://registry.npmjs.org/{package}
    PyPI: https://pypi.org/pypi/{package}/json
    """

    _TIMEOUT = 4.0
    _STALE_MONTHS = 18  # flag packages with no release in 18+ months
    _LOW_DOWNLOADS = 5000  # flag packages below this weekly download threshold

    # Common libraries worth checking — maps alias → canonical npm/PyPI name
    _NPM_PACKAGES = {
        "react": "react", "react 18": "react", "next.js": "next", "vue": "vue",
        "typescript": "typescript", "express": "express", "node.js": "express",
        "webpack": "webpack", "vite": "vite", "angular": "@angular/core",
    }
    _PYPI_PACKAGES = {
        "python": None,  # skip — not a package
        "fastapi": "fastapi", "django": "django", "flask": "flask",
        "sqlalchemy": "sqlalchemy", "pydantic": "pydantic", "uvicorn": "uvicorn",
        "langchain": "langchain", "langgraph": "langgraph",
        "pandas": "pandas", "numpy": "numpy", "scikit-learn": "scikit-learn",
    }

    async def check_libraries(self, tech_keywords: List[str]) -> Dict[str, Any]:
        """Check health of npm/PyPI packages mentioned in the tech stack."""
        npm_checks, pypi_checks = [], []
        kw_lower = [k.lower() for k in tech_keywords]

        for kw in kw_lower:
            if kw in self._NPM_PACKAGES and self._NPM_PACKAGES[kw]:
                npm_checks.append(self._NPM_PACKAGES[kw])
            if kw in self._PYPI_PACKAGES and self._PYPI_PACKAGES[kw]:
                pypi_checks.append(self._PYPI_PACKAGES[kw])

        results: List[Dict[str, Any]] = []
        warnings: List[str] = []

        async with httpx.AsyncClient(timeout=self._TIMEOUT, verify=False) as client:
            for pkg in npm_checks[:3]:
                info = await self._check_npm(client, pkg)
                if info:
                    results.append(info)
                    if info.get("stale"):
                        warnings.append(f"{pkg} (npm): last release {info['last_release']} — consider alternatives")

            for pkg in pypi_checks[:3]:
                info = await self._check_pypi(client, pkg)
                if info:
                    results.append(info)
                    if info.get("stale"):
                        warnings.append(f"{pkg} (PyPI): last release {info['last_release']} — verify active maintenance")

        return {
            "packages_checked": results,
            "warnings": warnings,
            "healthy_count": sum(1 for r in results if not r.get("stale")),
            "stale_count":   sum(1 for r in results if r.get("stale")),
            "sources": ["npm Registry API (https://registry.npmjs.org)",
                        "PyPI JSON API (https://pypi.org/pypi/{pkg}/json)"],
        }

    def format_for_context(self, health: Dict[str, Any]) -> str:
        pkgs = health.get("packages_checked", [])
        if not pkgs:
            return ""
        lines = [
            "=== PACKAGE HEALTH CHECK (real public data) ===",
            "Sources: npm Registry API | PyPI JSON API",
        ]
        for p in pkgs:
            status = "⚠ STALE" if p.get("stale") else "✓ Active"
            lines.append(f"• {p['name']} ({p['registry']}): {status} — "
                         f"last release {p['last_release']}, v{p['latest_version']}")
        if health.get("warnings"):
            lines.append("\nLibrary warnings for Engineer:")
            for w in health["warnings"]:
                lines.append(f"  ⚠ {w}")
        lines.append("=== END PACKAGE HEALTH ===")
        return "\n".join(lines)

    async def _check_npm(self, client: httpx.AsyncClient, pkg: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await client.get(f"https://registry.npmjs.org/{pkg}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            times = data.get("time", {})
            latest = data.get("dist-tags", {}).get("latest", "")
            last_rel = times.get(latest) or times.get("modified", "")
            stale = self._is_stale(last_rel)
            return {
                "name": pkg, "registry": "npm",
                "latest_version": latest,
                "last_release": last_rel[:10] if last_rel else "unknown",
                "stale": stale,
            }
        except Exception:
            return None

    async def _check_pypi(self, client: httpx.AsyncClient, pkg: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await client.get(f"https://pypi.org/pypi/{pkg}/json")
            if resp.status_code != 200:
                return None
            data = resp.json()
            info = data.get("info", {})
            latest = info.get("version", "")
            releases = data.get("releases", {})
            last_rel = ""
            if latest in releases and releases[latest]:
                last_rel = releases[latest][-1].get("upload_time", "")
            stale = self._is_stale(last_rel)
            return {
                "name": pkg, "registry": "PyPI",
                "latest_version": latest,
                "last_release": last_rel[:10] if last_rel else "unknown",
                "stale": stale,
            }
        except Exception:
            return None

    def _is_stale(self, date_str: str) -> bool:
        if not date_str:
            return False
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            months = (now - dt).days / 30
            return months >= self._STALE_MONTHS
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def extract_tech_keywords(text: str) -> List[str]:
    """Extract likely technology names from free-form text."""
    candidates = [
        "Python", "Java", "React", "TypeScript", "PostgreSQL", "MySQL", "Redis",
        "ServiceNow", "Docker", "Kubernetes", "AWS", "Vue", "Django", "Node.js",
        "Active Directory", "Salesforce", "SAP", "Kafka", "Terraform", "Flutter",
        "FastAPI", "Spring Boot", "Next.js", "Angular", "Flask", "MongoDB",
        "Azure", "Jenkins", "Nginx", "Apache", "GraphQL", "Elasticsearch",
    ]
    text_lower = text.lower()
    return [c for c in candidates if c.lower() in text_lower]
