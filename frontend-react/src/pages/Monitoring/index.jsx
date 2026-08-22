import { useCallback, useEffect, useState } from "react";
import {
  getMonitoringNotifications,
  getMonitoringHistory,
  getMonitoringStatus,
  checkMonitoringNow,
  updateMonitoringNotifications,
} from "../../services/api";

function timestamp(value) {
  return value ? new Date(value).toLocaleString() : "Not checked yet";
}

export default function MonitoringPage() {
  const [monitoring, setMonitoring] = useState(null);
  const [error, setError] = useState("");
  const [preferences, setPreferences] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [history, setHistory] = useState([]);
  const [checking, setChecking] = useState(false);
  const [checkMessage, setCheckMessage] = useState("");

  const load = useCallback(async (includePreferences = true) => {
    try {
      const [status, events, notificationPreferences] = await Promise.all([
        getMonitoringStatus(),
        getMonitoringHistory(10),
        includePreferences ? getMonitoringNotifications() : Promise.resolve(null),
      ]);
      setMonitoring(status);
      setHistory(events);
      if (notificationPreferences) setPreferences(notificationPreferences);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Service monitoring unavailable");
    }
  }, []);

  async function checkNow() {
    setChecking(true);
    setCheckMessage("");
    try {
      const result = await checkMonitoringNow();
      setMonitoring(result.status);
      setCheckMessage(result.transition_count
        ? `${result.transition_count} state change${result.transition_count === 1 ? "" : "s"} detected.`
        : "Check complete. No state changes detected.");
      setHistory(await getMonitoringHistory(10));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Service check unavailable");
    } finally {
      setChecking(false);
    }
  }

  function changeService(containerName, field, value) {
    setPreferences((current) => ({
      ...current,
      services: current.services.map((service) => (
        service.container_name === containerName ? { ...service, [field]: value } : service
      )),
    }));
    setSaved("");
  }

  async function savePreferences() {
    setSaving(true);
    try {
      setPreferences(await updateMonitoringNotifications(preferences));
      setSaved("Notification preferences saved.");
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Could not save notification preferences");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(false), 30000);
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
        <div className="monitoring-header-actions">
          <button type="button" className="secondary-button" onClick={() => load(true)}>Refresh</button>
          <button type="button" className="secondary-button" disabled={checking} onClick={checkNow}>
            {checking ? "Checking…" : "Check now"}
          </button>
        </div>
      </header>
      {error && <p className="journal-error">{error}</p>}
      {checkMessage && <p className="monitoring-check-message">{checkMessage}</p>}
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
      <section className="monitoring-history" aria-label="Recent service history">
        <h2>Recent outages and recoveries</h2>
        {history.length === 0 && <p className="answer">No service state changes have been recorded.</p>}
        {history.map((event) => (
          <article className="monitoring-history-event" key={event.id}>
            <span className={`monitoring-state ${event.event === "recovery" ? "running" : "stopped"}`}>{event.event}</span>
            <div>
              <strong>{event.display_name}</strong>
              <small>{event.from_status} → {event.to_status} · {timestamp(event.created_utc)}</small>
            </div>
            <small>{event.alert_sent ? "Discord notified" : "Journal only"}</small>
          </article>
        ))}
      </section>
      {preferences && (
        <section className="monitoring-preferences" aria-label="Notification preferences">
          <div className="monitoring-preferences-heading">
            <div>
              <h2>Discord notifications</h2>
              <p>Monitoring and journal entries continue even when notifications are off.</p>
            </div>
            <label className="monitoring-toggle">
              <input
                type="checkbox"
                checked={preferences.alerts_enabled}
                onChange={(event) => {
                  setPreferences({ ...preferences, alerts_enabled: event.target.checked });
                  setSaved("");
                }}
              />
              Alerts enabled
            </label>
          </div>
          <label className="monitoring-cooldown">
            Alert cooldown
            <select
              value={preferences.cooldown_seconds}
              onChange={(event) => {
                setPreferences({ ...preferences, cooldown_seconds: Number(event.target.value) });
                setSaved("");
              }}
            >
              <option value={0}>No cooldown</option>
              <option value={60}>1 minute</option>
              <option value={300}>5 minutes</option>
              <option value={900}>15 minutes</option>
              <option value={3600}>1 hour</option>
            </select>
          </label>
          <div className="monitoring-preference-list">
            {preferences.services.map((service) => (
              <div className="monitoring-preference-row" key={service.container_name}>
                <strong>{service.display_name}</strong>
                <label>
                  <input
                    type="checkbox"
                    checked={service.outage_alerts_enabled}
                    onChange={(event) => changeService(service.container_name, "outage_alerts_enabled", event.target.checked)}
                  />
                  Outages
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={service.recovery_alerts_enabled}
                    onChange={(event) => changeService(service.container_name, "recovery_alerts_enabled", event.target.checked)}
                  />
                  Recoveries
                </label>
              </div>
            ))}
          </div>
          <div className="monitoring-save-row">
            <button type="button" className="secondary-button" disabled={saving} onClick={savePreferences}>
              {saving ? "Saving…" : "Save notification preferences"}
            </button>
            {saved && <span>{saved}</span>}
          </div>
        </section>
      )}
    </div>
  );
}
