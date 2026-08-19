import { useCallback, useEffect, useRef, useState } from "react";
import Panel from "../../components/Panel";
import {
  getPlexLogs,
  getPlexStatus,
  plexRestart,
  plexStart,
  plexStop,
} from "../../services/api";

const PLEX_WEB_URL = "http://192.168.50.10:32400/web";

function formatPercent(value) {
  return value == null ? "unknown" : `${value}%`;
}

function formatBytes(bytes) {
  if (bytes == null) return "unknown";
  const gib = bytes / 1024 / 1024 / 1024;
  if (gib >= 1) return `${gib.toFixed(1)} GB`;
  const mib = bytes / 1024 / 1024;
  return `${mib.toFixed(0)} MB`;
}

function formatRam(status) {
  if (!status) return "Loading...";
  const percent = formatPercent(status.ram_usage);
  if (status.ram_usage_bytes == null) return percent;
  if (status.ram_limit_bytes == null) return `${formatBytes(status.ram_usage_bytes)} (${percent})`;
  return `${formatBytes(status.ram_usage_bytes)} / ${formatBytes(status.ram_limit_bytes)} (${percent})`;
}

function formatTime(date) {
  if (!date) return "not updated yet";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function resultText(response, fallback) {
  if (!response) return fallback;
  if (response.ok) return response.stdout || fallback;
  return response.error || response.stderr || JSON.stringify(response);
}

function getLogClass(line) {
  const lower = line.toLowerCase();
  if (lower.includes("error") || lower.includes("exception") || lower.includes("fatal") || lower.includes("critical") || lower.includes("failed")) {
    return "plex-log-line plex-log-error";
  }
  if (lower.includes("warn")) return "plex-log-line plex-log-warn";
  return "plex-log-line";
}

function StatusCard({ label, value, tone = "" }) {
  return (
    <div className={`card status-card ${tone}`.trim()}>
      <div className="label">{label}</div>
      <strong>{value}</strong>
    </div>
  );
}

function PlexLogs({ logs, loading, error, lastUpdated }) {
  const outputRef = useRef(null);

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [logs]);

  return (
    <div className="plex-console">
      <div className="plex-console-toolbar">
        <span>{loading ? "Refreshing logs..." : `Last updated: ${formatTime(lastUpdated)}`}</span>
        {error ? <span className="plex-console-error">{error}</span> : null}
      </div>

      <div className="plex-console-output" ref={outputRef} role="log" aria-live="polite">
        {logs.length ? (
          logs.map((line, index) => (
            <div className={getLogClass(line)} key={`${index}-${line.slice(0, 32)}`}>
              {line}
            </div>
          ))
        ) : (
          <div className="plex-log-line muted">{loading ? "Loading Plex logs..." : "No Plex logs available."}</div>
        )}
      </div>
    </div>
  );
}

export default function PlexPage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState("");
  const [logs, setLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(true);
  const [logsError, setLogsError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [actionState, setActionState] = useState({ status: "idle", message: "" });
  const tail = 220;

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await getPlexStatus();
      setStatus(data);
      setStatusError("");
    } catch (err) {
      setStatusError(err.message);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const data = await getPlexLogs(tail);
      if (!data.ok) {
        setLogsError(data.error || "Failed to load Plex logs.");
      } else {
        setLogsError("");
      }
      setLogs(Array.isArray(data.stdout) ? data.stdout : (data.stdout || "").split("\n").filter(Boolean));
      setLastUpdated(new Date());
    } catch (err) {
      setLogsError(err.message);
    } finally {
      setLogsLoading(false);
    }
  }, [tail]);

  const refreshPlex = useCallback(async () => {
    await Promise.all([loadStatus(), loadLogs()]);
  }, [loadLogs, loadStatus]);

  const runAction = useCallback(async (actionFn, label, successText) => {
    setActionState({ status: "running", message: `${label}: Running...` });

    try {
      const response = await actionFn();
      const ok = Boolean(response.ok);
      setActionState({
        status: ok ? "success" : "failure",
        message: ok ? `${label}: ${successText}` : `${label} failed: ${resultText(response, "Unknown error")}`,
      });
      return response;
    } catch (err) {
      setActionState({ status: "failure", message: `${label} failed: ${err.message}` });
      return { ok: false, error: err.message };
    } finally {
      await refreshPlex();
    }
  }, [refreshPlex]);

  const handleStop = () => {
    if (!window.confirm("Stop the Plex server? Active streams may be interrupted.")) return;
    runAction(plexStop, "Stop", "Plex stop requested.");
  };

  const handleRestart = () => {
    if (!window.confirm("Restart the Plex server now? Active streams may be interrupted temporarily.")) return;
    runAction(plexRestart, "Restart", "Plex restart requested.");
  };

  useEffect(() => {
    refreshPlex();
    const timer = setInterval(refreshPlex, 5000);
    return () => clearInterval(timer);
  }, [refreshPlex]);

  const running = Boolean(status?.running);
  const actionRunning = actionState.status === "running";
  const webUrl = status?.web_url || PLEX_WEB_URL;

  return (
    <div className="page-content plex-page">
      <header className="page-header">
        <div>
          <h1>Plex Workspace</h1>
          <p className="page-subtitle">Dedicated Plex Media Server administration and live container logs.</p>
        </div>
        <div className="plex-status-header">
          <div>
            <div className="label">Server</div>
            <div>{status?.container_name ?? "plex"}</div>
          </div>
          <div>
            <div className="label">State</div>
            <span className={`status-badge ${running ? "online" : "offline"}`}>
              {status?.state ?? (running ? "Running" : "Offline")}
            </span>
          </div>
          <a className="plex-open-link" href={webUrl} target="_blank" rel="noreferrer">
            Open Plex
          </a>
        </div>
      </header>

      {statusError ? <div className="action-result failure">Status error: {statusError}</div> : null}

      <section className="status-cards-grid">
        <StatusCard label="State" value={statusLoading ? "Loading..." : status?.state ?? (running ? "Running" : "Offline")} tone={running ? "online" : "offline"} />
        <StatusCard label="Web URL" value={webUrl} />
        <StatusCard label="RAM" value={formatRam(status)} />
        <StatusCard label="CPU" value={formatPercent(status?.cpu_usage)} />
        <StatusCard label="Uptime" value={status?.uptime ?? "unknown"} />
      </section>

      <Panel title="Server Actions" className="panel-fullwidth">
        <div className="plex-actions">
          <button disabled={actionRunning || running} onClick={() => runAction(plexStart, "Start", "Plex start requested.")}>Start</button>
          <button disabled={actionRunning || !running} onClick={handleRestart}>Restart</button>
          <button disabled={actionRunning || !running} onClick={handleStop}>Stop</button>
          <a className="button-link" href={webUrl} target="_blank" rel="noreferrer">Open Plex</a>
        </div>

        <div className="plex-details-grid">
          <div>
            <div className="label">Container State</div>
            <strong>{status?.container_state ?? "unknown"}</strong>
          </div>
          <div>
            <div className="label">Web URL</div>
            <a href={webUrl} target="_blank" rel="noreferrer">{webUrl}</a>
          </div>
        </div>

        {actionState.message ? (
          <div className={`action-result ${actionState.status}`}>
            {actionState.message}
          </div>
        ) : null}
      </Panel>

      <Panel title="Plex Logs" className="panel-fullwidth">
        <PlexLogs
          logs={logs}
          loading={logsLoading}
          error={logsError}
          lastUpdated={lastUpdated}
        />
      </Panel>
    </div>
  );
}
