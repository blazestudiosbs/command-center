import { useCallback, useEffect, useState } from "react";
import { getMonitoringStatus } from "../../services/api";

function timestamp(value) {
  return value ? new Date(value).toLocaleString() : "Not checked yet";
}

export default function MonitoringPage() {
  const [monitoring, setMonitoring] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setMonitoring(await getMonitoringStatus());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Service monitoring unavailable");
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const summary = monitoring?.summary;
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Service Monitoring</h1>
          <p className="page-subtitle">Read-only container awareness with alerts only when a service changes state.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="home-status" aria-label="Monitoring summary">
        <span><small>Healthy</small><strong>{summary?.healthy ?? "—"}</strong></span>
        <span><small>Unavailable</small><strong>{summary?.unavailable ?? "—"}</strong></span>
        <span><small>Services</small><strong>{summary?.total ?? "—"}</strong></span>
        <span><small>Automatic restarts</small><strong>Off</strong></span>
      </section>
      {monitoring && (
        <p className="answer">
          Checks run every {monitoring.interval_seconds} seconds. Discord alerts are {monitoring.discord_alerts_configured ? "configured" : "not configured"}.
        </p>
      )}
      <section className="monitoring-services" aria-label="Monitored services">
        {(monitoring?.services || []).map((service) => (
          <article className="monitoring-service" key={service.container_name}>
            <div>
              <strong>{service.display_name}</strong>
              <small>{service.container_name}</small>
            </div>
            <div className="monitoring-service-state">
              <span className={`monitoring-state ${service.status}`}>{service.status}</span>
              <small>Checked {timestamp(service.last_checked_utc)}</small>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
