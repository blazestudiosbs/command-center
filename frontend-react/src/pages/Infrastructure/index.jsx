import { useEffect, useState } from "react";
import { getBackupStatus, getInfrastructureStatus, setBackupEnabled, updateInfrastructureSettings } from "../../services/api";


export default function InfrastructurePage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [backup, setBackup] = useState(null);

  async function load() {
    try {
      const [infrastructure, backupStatus] = await Promise.all([getInfrastructureStatus(), getBackupStatus()]);
      setStatus(infrastructure); setBackup(backupStatus); setError("");
    }
    catch (err) { setError(err.response?.data?.detail || err.message || "Infrastructure agents unavailable"); }
  }

  useEffect(() => { load(); }, []);

  async function change(field, enabled) {
    setBusy(true);
    try {
      const settings = await updateInfrastructureSettings(
        field === "updates" ? enabled : status.settings.security_updates_enabled,
        field === "health" ? enabled : status.settings.health_checks_enabled,
      );
      setStatus((current) => ({ ...current, settings }));
      setError("");
    } catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setBusy(false); }
  }

  async function changeBackup(enabled) {
    setBusy(true);
    try {
      const settings = await setBackupEnabled(enabled);
      setBackup((current) => ({ ...current, settings }));
      setError("");
    } catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setBusy(false); }
  }

  const health = status?.health;
  const updates = status?.updates;
  const issues = health?.issues || [];

  return (
    <div className="page-content infrastructure-page">
      <header className="page-header">
        <div><h1>Infrastructure</h1><p className="page-subtitle">Safe host maintenance and read-only issue detection.</p></div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      {!status?.installed && <section className="infrastructure-install"><strong>Host agents are not installed yet</strong><p>Deploy the systemd timers once to activate scheduled updates and health checks.</p></section>}
      {status && (
        <>
          <section className="infrastructure-summary">
            <span><small>Health</small><strong>{health.status.replaceAll("_", " ")}</strong></span>
            <span><small>Root disk</small><strong>{health.metrics?.disk_used_percent ?? "—"}%</strong></span>
            <span><small>Memory</small><strong>{health.metrics?.used_percent ?? "—"}%</strong></span>
            <span><small>Active issues</small><strong>{issues.length}</strong></span>
          </section>
          <section className="agent-permission-grid">
            <article className="agent-permission-card">
              <div className="agent-permission-heading">
                <div><h2>Infrastructure Update Agent</h2><p>Ubuntu security updates every Monday at 3:00 AM Detroit time. Automatic reboot is blocked.</p></div>
                <label className="agent-switch"><input type="checkbox" disabled={busy} checked={status.settings.security_updates_enabled} onChange={(event) => change("updates", event.target.checked)} />{status.settings.security_updates_enabled ? "On" : "Off"}</label>
              </div>
              <div className="infrastructure-facts"><span><small>Last run</small><strong>{updates.completed_utc || "Never"}</strong></span><span><small>Result</small><strong>{updates.status}</strong></span><span><small>Reboot required</small><strong>{updates.reboot_required ? "Yes — manual" : "No"}</strong></span></div>
            </article>
            <article className="agent-permission-card">
              <div className="agent-permission-heading">
                <div><h2>Infrastructure Health Agent</h2><p>Checks disk, memory, failed system services, containers, and recent system errors every 15 minutes.</p></div>
                <label className="agent-switch"><input type="checkbox" disabled={busy} checked={status.settings.health_checks_enabled} onChange={(event) => change("health", event.target.checked)} />{status.settings.health_checks_enabled ? "On" : "Off"}</label>
              </div>
              <div className="infrastructure-facts"><span><small>Last check</small><strong>{health.checked_utc || "Never"}</strong></span><span><small>Recent errors</small><strong>{health.recent_error_count ?? "—"}</strong></span><span><small>Repairs</small><strong>Observation only</strong></span></div>
            </article>
            <article className="agent-permission-card">
              <div className="agent-permission-heading">
                <div><h2>Backup & Recovery Agent</h2><p>Creates verified daily backups at 2:30 AM Detroit time. Restore is always manual.</p></div>
                <label className="agent-switch"><input type="checkbox" disabled={busy} checked={backup?.settings.enabled ?? false} onChange={(event) => changeBackup(event.target.checked)} />{backup?.settings.enabled ? "On" : "Off"}</label>
              </div>
              <div className="infrastructure-facts">
                <span><small>Last backup</small><strong>{backup?.last_backup.completed_utc || "Never"}</strong></span>
                <span><small>Verification</small><strong>{backup?.last_backup.verified ? "Passed" : backup?.last_backup.status || "Not installed"}</strong></span>
                <span><small>Retention</small><strong>{backup?.settings.daily_retention ?? 14} daily · {backup?.settings.weekly_retention ?? 8} weekly</strong></span>
              </div>
              <p className="backup-safety-note">Secrets are excluded. Database tokens remain encrypted. Automatic restore is blocked.</p>
            </article>
          </section>
          <section className="panel">
            <h2>Detected issues</h2>
            {issues.length === 0 && <p className="answer">No active infrastructure issues were found.</p>}
            <div className="infrastructure-issues">{issues.map((issue, index) => <article key={`${issue.kind}-${index}`} className={issue.severity}><strong>{issue.kind}</strong><p>{issue.detail}</p></article>)}</div>
          </section>
        </>
      )}
    </div>
  );
}
