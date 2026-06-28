import { useCallback, useEffect, useState } from "react";
import Panel from "../../components/Panel";
import { getDevelopmentStatus } from "../../services/api";

const toolLabels = [
  ["codex_cli_available", "Codex CLI"],
  ["node_available", "Node"],
  ["npm_available", "npm"],
  ["python_available", "Python"],
  ["git_available", "Git"],
  ["docker_available", "Docker SDK"],
];

function StatusBadge({ active, children }) {
  return <span className={`dev-badge ${active ? "good" : "muted"}`}>{children}</span>;
}

function ToolHealth({ status }) {
  return (
    <div className="dev-tool-grid">
      {toolLabels.map(([key, label]) => {
        const available = Boolean(status?.[key]);
        return (
          <div className="dev-tool-card" key={key}>
            <span>{label}</span>
            <StatusBadge active={available}>{available ? "Available" : "Unavailable"}</StatusBadge>
          </div>
        );
      })}
    </div>
  );
}

function PlaceholderList({ items }) {
  return (
    <div className="dev-placeholder-list">
      {items.map((item) => (
        <div className="dev-placeholder-row" key={item.title}>
          <div>
            <strong>{item.title}</strong>
            <span>{item.detail}</span>
          </div>
          <StatusBadge active={false}>{item.status}</StatusBadge>
        </div>
      ))}
    </div>
  );
}

function RecentCommits({ commits }) {
  if (!commits?.length) {
    return <p className="answer">No recent commits available from this repository path.</p>;
  }

  return (
    <div className="dev-commit-list">
      {commits.map((commit) => (
        <div className="dev-commit-row" key={`${commit.hash}-${commit.message}`}>
          <code>{commit.hash}</code>
          <div>
            <strong>{commit.message}</strong>
            <span>{commit.author} - {commit.relative_time}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DevelopmentPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDevelopmentStatus();
      setStatus(data);
      setError("");
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const codeServerRunning = Boolean(status?.code_server?.running);
  const gitStatus = status?.git?.status || "unknown";
  const codeServerUrl = status?.code_server_url || "http://192.168.50.10:8443";

  return (
    <div className="page-content development-page">
      <header className="page-header">
        <div>
          <h1>Development Workspace</h1>
          <p className="page-subtitle">Code Server, repository health, build readiness, and task orchestration foundations.</p>
        </div>
        <div className="dev-header-actions">
          <div>
            <div className="label">Last Updated</div>
            <strong>{lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Not loaded"}</strong>
          </div>
          <button disabled={loading} onClick={loadStatus}>{loading ? "Refreshing..." : "Refresh"}</button>
        </div>
      </header>

      {error ? <div className="action-result failure">Development status error: {error}</div> : null}

      <section className="dev-overview-grid">
        <div className="card dev-overview-card">
          <div className="label">Code Server</div>
          <strong>{codeServerRunning ? "Running" : status?.code_server?.exists ? "Stopped" : "Missing"}</strong>
          <StatusBadge active={codeServerRunning}>{status?.code_server?.state || "unknown"}</StatusBadge>
        </div>
        <div className="card dev-overview-card">
          <div className="label">Repository</div>
          <strong>{status?.repository_path || "/opt/command-center"}</strong>
          <StatusBadge active={gitStatus === "clean"}>{gitStatus}</StatusBadge>
        </div>
        <div className="card dev-overview-card">
          <div className="label">Branch</div>
          <strong>{status?.git?.branch || "unknown"}</strong>
          <StatusBadge active={Boolean(status?.git?.branch && status.git.branch !== "unknown")}>Git</StatusBadge>
        </div>
      </section>

      <section className="workspace-grid">
        <div className="workspace-column">
          <Panel title="Workspace Overview">
            <div className="dev-kv-list">
              <div>
                <span>Repository Path</span>
                <strong>{status?.repository_path || "/opt/command-center"}</strong>
              </div>
              <div>
                <span>Code Server Container</span>
                <strong>{status?.code_server?.name || "code-server"}</strong>
              </div>
              <div>
                <span>Docker Access</span>
                <StatusBadge active={Boolean(status?.docker_available)}>{status?.docker_available ? "Available" : "Unavailable"}</StatusBadge>
              </div>
            </div>
            <div className="panel-actions">
              <a className="button-link" href={codeServerUrl} target="_blank" rel="noreferrer">Open Code Server</a>
            </div>
          </Panel>

          <Panel title="Tool Health">
            <ToolHealth status={status} />
          </Panel>

          <Panel title="Git Status">
            <div className="dev-kv-list">
              <div>
                <span>Branch</span>
                <strong>{status?.git?.branch || "unknown"}</strong>
              </div>
              <div>
                <span>Working Tree</span>
                <StatusBadge active={gitStatus === "clean"}>{gitStatus}</StatusBadge>
              </div>
            </div>
            <RecentCommits commits={status?.git?.recent_commits} />
          </Panel>
        </div>

        <div className="workspace-column">
          <Panel title="Current Task">
            <PlaceholderList items={[{ title: "No active task", detail: "Task execution state will appear here once orchestration is enabled.", status: "Placeholder" }]} />
          </Panel>

          <Panel title="Task Queue">
            <PlaceholderList items={[
              { title: "Queued tasks", detail: "Planned Codex and build jobs will be listed here.", status: "Empty" },
              { title: "Build requests", detail: "Future build commands will be tracked without exposing secrets.", status: "Planned" },
            ]} />
          </Panel>

          <Panel title="Recent Tasks">
            <PlaceholderList items={[{ title: "No task history yet", detail: "Completed task records will appear in this workspace later.", status: "Pending" }]} />
          </Panel>

          <Panel title="Codex Runner">
            <p className="answer">Codex task execution is not enabled yet.</p>
            <div className="panel-actions">
              <button disabled type="button">Run with Codex</button>
            </div>
          </Panel>
        </div>
      </section>
    </div>
  );
}
