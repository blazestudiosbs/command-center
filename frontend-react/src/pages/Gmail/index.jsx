import { useEffect, useState } from "react";
import { disconnectGmail, getGmailStatus, previewGmailOrganizer, startGmailOAuth } from "../../services/api";

export default function GmailPage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  async function load() {
    try {
      setStatus(await getGmailStatus());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Gmail status unavailable");
    }
  }

  useEffect(() => { load(); }, []);

  async function connect() {
    setBusy(true);
    try {
      const authorizationUrl = await startGmailOAuth();
      window.location.assign(authorizationUrl);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Gmail connection could not start");
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Gmail from Vera? This removes the locally stored authorization token.")) return;
    setBusy(true);
    try {
      await disconnectGmail();
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Gmail could not be disconnected");
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    setBusy(true);
    try {
      setPreview(await previewGmailOrganizer());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Organizer preview unavailable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Gmail</h1>
          <p className="page-subtitle">Private, read-only email connection for Vera.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="gmail-connection">
        <div className="gmail-connection-heading">
          <div>
            <small>Connection</small>
            <h2>{status?.status?.replaceAll("_", " ") || "Loading"}</h2>
          </div>
          <span className={`monitoring-state ${status?.connected ? "running" : "pending"}`}>
            {status?.connected ? "Connected" : "Not connected"}
          </span>
        </div>
        <p>{status?.detail}</p>
        {status?.email_address && <p><strong>Account:</strong> {status.email_address}</p>}
        <div className="gmail-safety-grid">
          <span><small>Access</small><strong>Read only</strong></span>
          <span><small>Send email</small><strong>Blocked</strong></span>
          <span><small>Modify email</small><strong>Blocked</strong></span>
          <span><small>Cloud processing</small><strong>Not connected</strong></span>
        </div>
        {!status?.connected && (
          <button type="button" className="secondary-button" disabled={busy || !status?.configured} onClick={connect}>
            {busy ? "Opening Google…" : "Connect Gmail read-only"}
          </button>
        )}
        {status?.connected && (
          <button type="button" className="secondary-button" disabled={busy} onClick={disconnect}>
            {busy ? "Disconnecting…" : "Disconnect Gmail"}
          </button>
        )}
      </section>
      <p className="answer">Inbox reading and the Gmail agent will remain disabled until this connection is verified.</p>
      {status?.connected && (
        <section className="gmail-organizer-preview">
          <div className="gmail-organizer-heading">
            <div>
              <h2>Organizer simulation</h2>
              <p>Preview sender and category labels. This does not change Gmail.</p>
            </div>
            <button type="button" className="secondary-button" disabled={busy} onClick={loadPreview}>
              {busy ? "Loading…" : "Preview organization"}
            </button>
          </div>
          {preview && <p className="answer">{preview.message_count} inbox messages analyzed locally. No changes made.</p>}
          <div className="gmail-preview-list">
            {(preview?.messages || []).map((message) => (
              <article key={message.message_id}>
                <div><strong>{message.subject}</strong><small>{message.sender}</small></div>
                <div className="gmail-preview-labels">
                  {message.labels.map((label) => <span key={label}>{label}</span>)}
                  <small>Will remove from Inbox</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
