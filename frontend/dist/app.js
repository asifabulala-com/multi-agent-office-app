const statusOutput = document.getElementById("statusOutput");
const resultSummary = document.getElementById("resultSummary");
const resultJson = document.getElementById("resultJson");
const projectForm = document.getElementById("projectForm");
const refreshStatus = document.getElementById("refreshStatus");
const deptFilters = document.getElementById("deptFilters");
const projectGrid = document.getElementById("projectGrid");

let allProjects = [];
let selectedProjectId = null;

// ── Dataset ──────────────────────────────────────────────────────────────────

async function loadDataset() {
    try {
        const res = await fetch("/dataset");
        if (!res.ok) throw new Error("Dataset unavailable");
        const data = await res.json();
        allProjects = data.projects;
        buildDeptFilters(data.departments);
        renderCards(allProjects);
    } catch (err) {
        projectGrid.innerHTML = `<div class="dataset-loading">Could not load dataset: ${err.message}</div>`;
    }
}

function buildDeptFilters(departments) {
    departments.forEach(dept => {
        const btn = document.createElement("button");
        btn.className = "dept-btn";
        btn.dataset.dept = dept;
        btn.textContent = dept;
        btn.addEventListener("click", () => filterByDept(dept, btn));
        deptFilters.appendChild(btn);
    });

    deptFilters.querySelector('[data-dept=""]').addEventListener("click", (e) => {
        filterByDept("", e.currentTarget);
    });
}

function filterByDept(dept, clickedBtn) {
    deptFilters.querySelectorAll(".dept-btn").forEach(b => b.classList.remove("active"));
    clickedBtn.classList.add("active");
    const filtered = dept ? allProjects.filter(p => p.department === dept) : allProjects;
    renderCards(filtered);
}

function renderCards(projects) {
    if (!projects.length) {
        projectGrid.innerHTML = `<div class="dataset-loading">No projects found.</div>`;
        return;
    }
    projectGrid.innerHTML = projects.map(p => `
        <div class="project-card${selectedProjectId === p.project_id ? " selected" : ""}"
             data-id="${p.project_id}"
             title="${p.description.slice(0, 120)}…">
            <div class="card-dept">${p.department}</div>
            <div class="card-name">${p.project_name}</div>
            <div class="card-id">${p.project_id}</div>
        </div>
    `).join("");

    projectGrid.querySelectorAll(".project-card").forEach(card => {
        card.addEventListener("click", () => selectProject(card.dataset.id));
    });
}

function selectProject(projectId) {
    const project = allProjects.find(p => p.project_id === projectId);
    if (!project) return;

    selectedProjectId = projectId;

    document.getElementById("projectId").value = project.project_id;
    document.getElementById("projectName").value = project.project_name;
    document.getElementById("projectDescription").value = project.description;

    // Highlight selected card
    projectGrid.querySelectorAll(".project-card").forEach(c => {
        c.classList.toggle("selected", c.dataset.id === projectId);
    });

    // Scroll form into view
    document.getElementById("projectForm").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Status ───────────────────────────────────────────────────────────────────

async function fetchStatus() {
    try {
        statusOutput.textContent = "Loading system status...";
        const response = await fetch("/status");
        if (!response.ok) throw new Error(`Status request failed: ${response.status}`);
        const data = await response.json();
        statusOutput.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        statusOutput.textContent = `Unable to fetch status: ${error.message}`;
    }
}

function formatResult(data) {
    const compass = data.compass_evaluation || {};
    const lines = [
        `Project : ${data.project_id}`,
        `Status  : ${data.status}`,
        `Iterations: ${data.iterations}`,
        `Compass : ${compass.status || "unknown"}`,
        `Messages: ${data.interactions?.messages?.length ?? 0}`,
    ];
    if (data.mvp_url) {
        lines.push(`\n MVP ready → opening in browser…`);
    }
    return lines.join("\n");
}

function injectResultLinks(mvpUrl, reportUrl) {
    const existing = document.getElementById("mvpLinkBar");
    if (existing) existing.remove();
    if (!mvpUrl && !reportUrl) return;
    const bar = document.createElement("div");
    bar.id = "mvpLinkBar";
    bar.className = "mvp-link-bar";
    let html = "";
    if (reportUrl) {
        html += `<a href="${reportUrl}" target="_blank" class="mvp-open-btn" style="background:#0ea5e9;">📄 Open Report →</a>`;
    }
    if (mvpUrl) {
        html += `<a href="${mvpUrl}" target="_blank" class="mvp-open-btn">🚀 Open MVP →</a>`;
    }
    bar.innerHTML = `<span class="mvp-label">Simulation complete</span>${html}`;
    document.getElementById("resultSummary").after(bar);
}

// ── Run ──────────────────────────────────────────────────────────────────────

async function postRun(formData) {
    try {
        resultSummary.textContent = "Running simulation...";
        resultJson.textContent = "{}";

        // Use async /run endpoint + poll /status to avoid socket timeout on long simulations
        const runResp = await fetch("/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(formData),
        });
        if (!runResp.ok) {
            const errorText = await runResp.text();
            throw new Error(errorText || `Request failed with ${runResp.status}`);
        }
        const data = await runResp.json();
        resultSummary.textContent = formatResult(data);
        resultJson.textContent = JSON.stringify(data, null, 2);
        injectResultLinks(data.mvp_url || "", data.report_url || "");
        await fetchStatus();
    } catch (error) {
        resultSummary.textContent = `Execution failed: ${error.message}`;
        resultJson.textContent = "{}";
    }
}

projectForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = {
        project_id: document.getElementById("projectId").value.trim(),
        project_name: document.getElementById("projectName").value.trim(),
        description: document.getElementById("projectDescription").value.trim(),
    };
    postRun(formData);
});

refreshStatus.addEventListener("click", fetchStatus);

// ── Init ─────────────────────────────────────────────────────────────────────
fetchStatus();
loadDataset();
