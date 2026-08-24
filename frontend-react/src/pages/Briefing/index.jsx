import { useEffect, useState } from "react";
import {
  getDailyBriefingStatus,
  previewDailyBriefing,
  sendDailyBriefing,
  updateDailyBriefingSettings,
} from "../../services/api";

const sections = [
  ["include_calendar", "Today’s calendar"],
  ["include_gmail", "Recent unread Gmail"],
  ["include_infrastructure", "Server and service health"],
  ["include_backups", "Latest backup"],
  ["include_approvals", "Pending approvals"],
];

export default function BriefingPage() {
  const [status, setStatus] = useState(null);
  const [settings, setSettings] = useState(null);
  const [preview, setPreview] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getDailyBriefingStatus()
      .then((result) => { setStatus(result); setSettings(result.settings); })
      .catch((err) => setError(err.response?.data?.detail || "Daily briefing is unavailable."));
  }, []);

  async function save() {
    setBusy(true); setMessage(""); setError("");
    try {
      setSettings(await updateDailyBriefingSettings(settings));
      setMessage("Daily briefing settings saved.");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save briefing settings.");
    } finally { setBusy(false); }
  }

  async function makePreview() {
    setBusy(true); setMessage(""); setError("");
    try { setPreview((await previewDailyBriefing()).message); }
    catch (err) { setError(err.response?.data?.detail || "Could not generate the briefing."); }
    finally { setBusy(false); }
  }

  async function sendNow() {
    setBusy(true); setMessage(""); setError("");
    try {
      const result = await sendDailyBriefing();
      setPreview(result.message);
      setMessage("Briefing sent to Discord.");
    } catch (err) { setError(err.response?.data?.detail || "Could not send the briefing."); }
    finally { setBusy(false); }
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Daily Briefing</h1>
          <p className="page-subtitle">A local, read-only morning summary delivered to Discord.</p>
        </div>
      </header>
      {error && <p className="journal-error">{error}</p>}
      {message && <p className="monitoring-check-message">{message}</p>}
      {settings && <>
        <section className="monitoring-preferences" aria-label="Daily briefing settings">
          <div className="monitoring-preferences-heading">
            <div><h2>Schedule</h2><p>Runs once each day in America/Detroit. It never changes mail, events, or server settings.</p></div>
            <label className="monitoring-toggle"><input type="checkbox" checked={settings.enabled} onChange={(event) => setSettings({ ...settings, enabled: event.target.checked })} /> Enabled</label>
          </div>
          <label className="monitoring-cooldown">Delivery time<input type="time" value={settings.delivery_time} onChange={(event) => setSettings({ ...settings, delivery_time: event.target.value })} /></label>
          <div className="monitoring-preference-list">
            {sections.map(([key, label]) => <div className="monitoring-preference-row" key={key}><strong>{label}</strong><label><input type="checkbox" checked={settings[key]} onChange={(event) => setSettings({ ...settings, [key]: event.target.checked })} /> Include</label></div>)}
          </div>
          <div className="monitoring-save-row"><button type="button" className="secondary-button" disabled={busy} onClick={save}>{busy ? "Working…" : "Save settings"}</button></div>
        </section>
        <section className="monitoring-history" aria-label="Briefing preview">
          <h2>Preview and delivery test</h2>
          <p className="answer">Discord is {status?.discord_configured ? "configured" : "not configured"}. Generate permission and delivery permission are managed on Agent Permissions.</p>
          <div className="monitoring-header-actions"><button type="button" className="secondary-button" disabled={busy} onClick={makePreview}>Preview</button><button type="button" className="secondary-button" disabled={busy || !status?.discord_configured} onClick={sendNow}>Send test now</button></div>
          {preview && <pre className="answer" style={{ whiteSpace: "pre-wrap" }}>{preview}</pre>}
        </section>
      </>}
    </div>
  );
}
