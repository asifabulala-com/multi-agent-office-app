import { useEffect, useMemo, useState } from "react";

interface ProjectRequest {
  project_id: string;
  project_name: string;
  description: string;
}

interface ExecutionResult {
  project_id: string;
  status: string;
  iterations: number;
  compass_evaluation: Record<string, unknown>;
  interactions: {
    messages: Array<Record<string, unknown>>;
    decisions: Array<Record<string, unknown>>;
    feedback_loops: Record<string, unknown>;
  };
}

function App() {
  const [statusText, setStatusText] = useState("Loading system status...");
  const [projectId, setProjectId] = useState("demo-project-01");
  const [projectName, setProjectName] = useState("AI Office Simulation");
  const [description, setDescription] = useState("Simulate multi-agent planning, execution, QA and risk management.");
  const [execution, setExecution] = useState<ExecutionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStatus = async () => {
    try {
      const response = await fetch("/status");
      if (!response.ok) throw new Error(`Status fetch failed: ${response.status}`);
      const data = await response.json();
      setStatusText(JSON.stringify(data, null, 2));
    } catch (err) {
      setStatusText(`Unable to fetch status: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  useEffect(() => {
    handleStatus();
  }, []);

  const handleRun = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setExecution(null);

    const payload: ProjectRequest = {
      project_id: projectId,
      project_name: projectName,
      description,
    };

    try {
      const response = await fetch("/run-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed ${response.status}`);
      }

      const result: ExecutionResult = await response.json();
      setExecution(result);
      await handleStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const summaryText = useMemo(() => {
    if (!execution) return "No execution yet.";
    return `Project ${execution.project_id} completed with status ${execution.status} after ${execution.iterations} iteration(s). Compass status: ${execution.compass_evaluation?.status ?? "unknown"}`;
  }, [execution]);

  return (
    <div className="app-shell">
      <div className="header-row">
        <div>
          <h1>Multi-Agent PM Dashboard</h1>
          <p>Submit a project, inspect agent collaboration, and visualize the multi-agent workflow.</p>
        </div>
        <button onClick={handleStatus} type="button">
          Refresh Status
        </button>
      </div>

      <section className="panel">
        <h2>Launch Simulation</h2>
        <form onSubmit={handleRun}>
          <label htmlFor="project-id">Project ID</label>
          <input
            id="project-id"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            required
          />

          <label htmlFor="project-name">Project Name</label>
          <input
            id="project-name"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            required
          />

          <label htmlFor="project-description">Description</label>
          <textarea
            id="project-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />

          <button type="submit" disabled={loading}>
            {loading ? "Running..." : "Run Simulation"}
          </button>
        </form>
      </section>

      <section className="panel status-card">
        <h2>System Status</h2>
        <pre>{statusText}</pre>
      </section>

      <section className="panel summary-card">
        <h2>Execution Result</h2>
        <pre>{error ? `Error: ${error}` : summaryText}</pre>
        {execution && (
          <details>
            <summary>View full execution payload</summary>
            <pre>{JSON.stringify(execution, null, 2)}</pre>
          </details>
        )}
      </section>
    </div>
  );
}

export default App;
