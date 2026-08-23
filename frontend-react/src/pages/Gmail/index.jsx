import { useEffect, useState } from "react";
import {
  disconnectGmail, getGmailLearningStatus, getGmailOrganizerSettings, getGmailStatus,
  getGmailAutomationRules, getGmailCloudSuggestions, learnGmailSender, previewGmailOrganizer,
  reviewGmailAutomationRule, reviewGmailCloudSuggestion,
  runGmailCloudLearning, runGmailOrganizer, setGmailCloudLearningEnabled,
  setGmailOrganizerEnabled, startGmailOAuth,
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
  const [suggestions, setSuggestions] = useState([]);
  const [automationRules, setAutomationRules] = useState([]);

  async function load() {
    try {
      const [gmailStatus, learningStatus, organizerSettings, cloudSuggestions, rules] = await Promise.all([
        getGmailStatus(), getGmailLearningStatus(), getGmailOrganizerSettings(), getGmailCloudSuggestions(), getGmailAutomationRules(),
      ]);
      setStatus(gmailStatus);
      setLearning(learningStatus);
      setOrganizer(organizerSettings);
      setSuggestions(cloudSuggestions);
      setAutomationRules(rules);
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

  async function authorizePermanentDelete() {
    setBusy(true);
    try {
      const authorizationUrl = await startGmailOAuth(true);
      window.location.assign(authorizationUrl);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Permanent-delete authorization could not start");
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

  async function toggleCloudLearning(enabled) {
    setBusy(true);
    try {
      setLearning(await setGmailCloudLearningEnabled(enabled));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Cloud learning setting could not be changed");
    } finally { setBusy(false); }
  }

  async function reviewUncertainMail() {
    setBusy(true);
    try {
      const result = await runGmailCloudLearning();
      setRunMessage(result.status === "no_candidates"
        ? "No uncertain messages need cloud review."
        : `${result.reviewed} uncertain messages reviewed; ${result.suggestions} suggestions await your approval.`);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Cloud review failed safely");
    } finally { setBusy(false); }
  }

  async function decideSuggestion(id, approve) {
    setBusy(true);
    try {
      await reviewGmailCloudSuggestion(id, approve);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Suggestion could not be reviewed");
    } finally { setBusy(false); }
  }

  async function decideAutomationRule(id, approve) {
    if (approve && !window.confirm("Activate this permanent-delete rule? Matching Gmail messages cannot be recovered.")) return;
    setBusy(true);
    try {
      await reviewGmailAutomationRule(id, approve);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Gmail rule could not be reviewed");
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
          <span><small>Cloud processing</small><strong>{learning?.cloud_permission_enabled ? "Permission enabled" : "Off"}</strong></span>
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
              <span><small>Cloud review</small><strong>{learning.cloud_review_enabled ? "On" : "Off"}</strong></span>
              <span><small>Monthly use</small><strong>${learning.monthly_spent_usd.toFixed(4)} / ${learning.monthly_budget_usd.toFixed(2)}</strong></span>
              <span><small>Weekly use</small><strong>{learning.weekly_messages_reviewed} / {learning.weekly_message_limit}</strong></span>
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
      {status?.connected && learning && (
        <section className="gmail-organizer-preview">
          <div className="gmail-organizer-heading">
            <div>
              <h2>Occasional cloud learning</h2>
              <p>Only uncertain sender and subject metadata is sent. Bodies are always blocked, and suggestions never become rules without your approval.</p>
            </div>
            <label className="agent-switch">
              <input type="checkbox" checked={learning.cloud_review_enabled} disabled={busy} onChange={(event) => toggleCloudLearning(event.target.checked)} />
              {learning.cloud_review_enabled ? "On" : "Off"}
            </label>
          </div>
          {!learning.cloud_permission_enabled && <p className="answer">Enable Gmail Agent → Send uncertain sender/subject to cloud AI in Agent Permissions first.</p>}
          <button type="button" className="secondary-button" disabled={busy || !learning.cloud_review_enabled} onClick={reviewUncertainMail}>Review uncertain mail now</button>
          {suggestions.filter((item) => item.status === "pending").map((item) => (
            <article key={item.id} className="gmail-cloud-suggestion">
              <div><strong>{item.sender}</strong><small>Suggested: Vera/{item.suggested_category}</small><p>{item.reason}</p></div>
              <div>
                <button type="button" className="secondary-button" disabled={busy} onClick={() => decideSuggestion(item.id, true)}>Approve rule</button>
                <button type="button" className="secondary-button" disabled={busy} onClick={() => decideSuggestion(item.id, false)}>Reject</button>
              </div>
            </article>
          ))}
          {learning.pending_suggestion_count === 0 && <p className="answer">No cloud suggestions are waiting for approval.</p>}
        </section>
      )}
      {status?.connected && (
        <section className="gmail-organizer-preview">
          <div className="gmail-organizer-heading">
            <div>
              <h2>Requested Gmail rules</h2>
              <p>Rules Vera understands from conversation appear here for validation and approval.</p>
            </div>
          </div>
          {automationRules.map((rule) => (
            <article key={rule.id} className="gmail-cloud-suggestion">
              <div>
                <strong>{rule.sender}</strong>
                <small>Permanently delete existing and future matches · {rule.status}</small>
                <p>{rule.validation_note}</p>
                {rule.status === "active" && <p>{rule.deleted_count} messages permanently deleted so far.</p>}
              </div>
              {rule.status === "pending" && (
                <div>
                  <button type="button" className="secondary-button" disabled={busy} onClick={() => decideAutomationRule(rule.id, true)}>Approve destructive rule</button>
                  <button type="button" className="secondary-button" disabled={busy} onClick={() => decideAutomationRule(rule.id, false)}>Reject</button>
                </div>
              )}
            </article>
          ))}
          {automationRules.some((rule) => rule.status === "pending") && !status?.permanent_delete_authorized && (
            <button type="button" className="secondary-button" disabled={busy} onClick={authorizePermanentDelete}>Authorize permanent deletion with Google</button>
          )}
          {automationRules.length === 0 && <p className="answer">No Gmail rules have been requested through Vera.</p>}
        </section>
      )}
    </div>
  );
}
