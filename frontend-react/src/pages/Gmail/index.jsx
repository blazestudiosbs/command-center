import { useEffect, useState } from "react";
import {
  disconnectGmail, getGmailLearningStatus, getGmailOrganizerSettings, getGmailStatus,
  learnGmailSender, previewGmailOrganizer, runGmailOrganizer, setGmailOrganizerEnabled, startGmailOAuth,
} from "../../services/api";

const categories = [
  "Accounts/Passwords", "Accounts/Verification", "Accounts/Security",
  "Financial/Taxes", "Financial/Banking", "Financial/Payments", "Financial/Bills",
  "Shopping/Shipping", "Shopping/Receipts", "Shopping/Orders", "Shopping/Promotions",
  "Travel/Flights", "Travel/Hotels", "Travel/Reservations",
  "Personal/Family", "Personal/Medical", "Personal/Education",
  "Subscriptions/Entertainment", "Subscriptions/Newsletters", "Needs Review",
];

export default function GmailPage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [learning, setLearning] = useState(null);
  const [learningMessage, setLearningMessage] = useState("");
  const [organizer, setOrganizer] = useState(null);
  const [runMessage, setRunMessage] = useState("");

  async function load() {
    try {
      const [gmailStatus, learningStatus, organizerSettings] = await Promise.all([
        getGmailStatus(), getGmailLearningStatus(), getGmailOrganizerSettings(),
      ]);
      setStatus(gmailStatus);
      setLearning(learningStatus);
      setOrganizer(organizerSettings);
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

  function chooseCategory(messageId, category) {
    setPreview((current) => ({
      ...current,
      messages: current.messages.map((message) => message.message_id === messageId
        ? { ...message, category, labels: [`Vera/${category}`, message.labels[1]] }
        : message),
    }));
  }

  async function learnSender(message) {
    setLearningMessage(message.message_id);
    try {
      const result = await learnGmailSender(message.sender, message.category);
      setLearning(result.learning);
      setPreview((current) => ({
        ...current,
        messages: current.messages.map((item) => item.message_id === message.message_id
          ? { ...item, confidence: "learned" }
          : item),
      }));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Sender rule could not be learned");
    } finally {
      setLearningMessage("");
    }
  }

  async function toggleOrganizer(enabled) {
    setBusy(true);
    try {
      setOrganizer(await setGmailOrganizerEnabled(enabled));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Organizer setting could not be changed");
    } finally { setBusy(false); }
  }

  async function organizeNow() {
    if (!window.confirm("File current Inbox messages now? Vera will apply labels and remove them from the Inbox.")) return;
    setBusy(true);
    try {
      const result = await runGmailOrganizer();
      setRunMessage(`${result.processed} messages filed; ${result.failed} failed safely.`);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Organizer run failed");
    } finally { setBusy(false); }
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
          <span><small>Access</small><strong>{status?.organizer_authorized ? "Read and organize" : "Read only"}</strong></span>
          <span><small>Send email</small><strong>Blocked</strong></span>
          <span><small>Modify email</small><strong>{status?.organizer_authorized ? "Labels only" : "Blocked"}</strong></span>
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
        {status?.connected && !status?.organizer_authorized && (
          <button type="button" className="secondary-button" disabled={busy} onClick={connect}>Authorize Gmail organization</button>
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
          {learning && (
            <div className="gmail-learning-status">
              <span><small>Learned rules</small><strong>{learning.learned_rule_count}</strong></span>
              <span><small>Cloud review</small><strong>Off</strong></span>
              <span><small>Future monthly cap</small><strong>${learning.monthly_budget_usd.toFixed(2)}</strong></span>
              <span><small>Future weekly limit</small><strong>{learning.weekly_message_limit}</strong></span>
            </div>
          )}
          <div className="gmail-preview-list">
            {(preview?.messages || []).map((message) => (
              <article key={message.message_id}>
                <div><strong>{message.subject}</strong><small>{message.sender}</small></div>
                <div className="gmail-preview-labels">
                  {message.labels.map((label) => <span key={label}>{label}</span>)}
                  <select value={message.category} onChange={(event) => chooseCategory(message.message_id, event.target.value)}>
                    {categories.map((category) => <option key={category} value={category}>{category}</option>)}
                  </select>
                  <button type="button" className="secondary-button" disabled={learningMessage === message.message_id} onClick={() => learnSender(message)}>
                    {learningMessage === message.message_id ? "Learning…" : "Learn this sender"}
                  </button>
                  <small>{message.confidence === "learned" ? "Learned sender rule" : message.confidence === "high" ? "High-confidence match" : "Needs review"} · Will remove from Inbox</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      {status?.connected && status?.organizer_authorized && organizer && (
        <section className="gmail-organizer-preview">
          <div className="gmail-organizer-heading">
            <div><h2>Automatic filing</h2><p>Applies Vera labels, then removes successfully filed mail from Inbox.</p></div>
            <label className="agent-switch">
              <input type="checkbox" checked={organizer.enabled} disabled={busy} onChange={(event) => toggleOrganizer(event.target.checked)} />
              {organizer.enabled ? "On" : "Off"}
            </label>
          </div>
          <button type="button" className="secondary-button" disabled={busy || !organizer.enabled} onClick={organizeNow}>File Inbox now</button>
          {runMessage && <p className="answer">{runMessage}</p>}
        </section>
      )}
    </div>
  );
}
