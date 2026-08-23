import { useEffect, useState } from "react";
import { confirmCalendarChange, getCalendarEvents, getCalendarStatus, prepareCalendarChange, startCalendarOAuth } from "../../services/api";

function displayTime(event) {
  if (event.all_day) return `${event.start} · All day`;
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(event.start));
}

function localInput(value, allDay) {
  if (!value) return "";
  if (allDay) return value.slice(0, 10);
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

const emptyForm = { title: "", start: "", end: "", location: "", all_day: false };

export default function CalendarPage() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [selectedId, setSelectedId] = useState("");
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadStatus() {
    try { setStatus(await getCalendarStatus()); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Calendar status unavailable"); }
  }
  useEffect(() => { loadStatus(); }, []);

  async function connect(write = false) {
    setBusy(true);
    try { window.location.assign(await startCalendarOAuth(write)); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Calendar authorization could not start"); setBusy(false); }
  }

  async function loadEvents() {
    setBusy(true);
    try { setEvents((await getCalendarEvents(31)).events); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Upcoming events unavailable"); }
    finally { setBusy(false); }
  }

  function chooseEvent(event) {
    setSelectedId(event.id);
    setForm({ title: event.title, start: localInput(event.start, event.all_day), end: localInput(event.end, event.all_day), location: event.location || "", all_day: event.all_day });
    setPending(null); setNotice("");
  }

  function startCreate() {
    setSelectedId(""); setForm(emptyForm); setPending(null); setNotice("");
  }

  async function prepare(event) {
    event.preventDefault(); setBusy(true); setPending(null); setNotice("");
    try {
      const change = await prepareCalendarChange({ action: selectedId ? "edit" : "create", event_id: selectedId || null, ...form });
      setPending(change); setError("");
    } catch (err) { setError(err.response?.data?.detail || err.message || "Calendar preview could not be prepared"); }
    finally { setBusy(false); }
  }

  async function confirm() {
    setBusy(true);
    try {
      const result = await confirmCalendarChange(pending.id);
      setPending(null); setNotice(result.action === "edit" ? "Event updated in Google Calendar." : "Event created in Google Calendar.");
      await loadEvents();
    } catch (err) { setError(err.response?.data?.detail || err.message || "Calendar change was not completed"); setBusy(false); }
  }

  return (
    <div className="page-content calendar-page">
      <header className="page-header"><div><h1>Calendar</h1><p className="page-subtitle">Read events and make only the changes you explicitly confirm.</p></div><button type="button" className="secondary-button" onClick={loadStatus}>Refresh</button></header>
      {error && <p className="journal-error">{error}</p>}{notice && <p className="answer">{notice}</p>}
      <section className="gmail-connection">
        <div className="gmail-connection-heading"><div><small>Connection</small><h2>{status?.connected ? "Connected" : "Not connected"}</h2></div><span className={`monitoring-state ${status?.connected ? "running" : "pending"}`}>{status?.write_authorized ? "Create + edit" : "Read only"}</span></div>
        <p>{status?.detail || "Checking Google Calendar…"}</p>{status?.account && <p><strong>Account:</strong> {status.account}</p>}
        <div className="gmail-safety-grid"><span><small>Read events</small><strong>{status?.authorized ? "Authorized" : "Not authorized"}</strong></span><span><small>Create</small><strong>{status?.can_create ? "Confirmation required" : "Blocked"}</strong></span><span><small>Edit</small><strong>{status?.can_edit ? "Confirmation required" : "Blocked"}</strong></span><span><small>Delete</small><strong>Blocked</strong></span></div>
        {!status?.connected && <button type="button" className="secondary-button" disabled={busy || !status?.configured} onClick={() => connect(false)}>Authorize Calendar read access</button>}
        {status?.connected && !status?.write_authorized && <button type="button" className="secondary-button" disabled={busy} onClick={() => connect(true)}>Authorize creation and editing</button>}
      </section>
      {status?.connected && <section className="panel">
        <div className="calendar-events-heading"><div><h2>Next 31 days</h2><p>Select an existing event to edit it.</p></div><button type="button" className="secondary-button" disabled={busy} onClick={loadEvents}>{busy ? "Loading…" : "Load events"}</button></div>
        <div className="calendar-events">{events.map((event) => <article key={event.id} className={selectedId === event.id ? "selected" : ""}><time>{displayTime(event)}</time><div><strong>{event.title}</strong>{event.location && <small>{event.location}</small>}</div>{status?.write_authorized && <button type="button" className="secondary-button" onClick={() => chooseEvent(event)}>Edit</button>}</article>)}</div>
        {events.length === 0 && <p className="answer">Enable Calendar Agent → Read event titles and times, then load events.</p>}
      </section>}
      {status?.write_authorized && <section className="panel calendar-change-panel">
        <div className="calendar-events-heading"><div><h2>{selectedId ? "Edit selected event" : "Create an event"}</h2><p>No change reaches Google until you review and confirm it.</p></div>{selectedId && <button type="button" className="secondary-button" onClick={startCreate}>Create instead</button>}</div>
        <form className="calendar-change-form" onSubmit={prepare}>
          <label>Title<input value={form.title} maxLength="300" required onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="calendar-check"><input type="checkbox" checked={form.all_day} onChange={(e) => setForm({ ...form, all_day: e.target.checked, start: "", end: "" })} />All-day event</label>
          <label>Start<input type={form.all_day ? "date" : "datetime-local"} value={form.start} required onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
          <label>End<input type={form.all_day ? "date" : "datetime-local"} value={form.end} required onChange={(e) => setForm({ ...form, end: e.target.value })} /></label>
          <label>Location<input value={form.location} maxLength="500" onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
          <button className="primary-button" disabled={busy} type="submit">Review {selectedId ? "edit" : "new event"}</button>
        </form>
        <p className="answer">The matching Calendar Agent {selectedId ? "edit" : "create"} permission must also be enabled. Event deletion remains unavailable, and Vera will not email guests about these changes.</p>
      </section>}
      {pending && <section className="panel calendar-confirm-panel"><h2>Confirm this {pending.action}</h2>{pending.before && <p><strong>Current:</strong> {pending.before.title} · {displayTime(pending.before)}</p>}<p><strong>New:</strong> {pending.after.title} · {pending.after.start} to {pending.after.end}{pending.after.location ? ` · ${pending.after.location}` : ""}</p><p>This confirmation expires in 15 minutes.</p><div className="calendar-confirm-actions"><button type="button" className="primary-button" disabled={busy} onClick={confirm}>{busy ? "Saving…" : `Confirm ${pending.action}`}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setPending(null)}>Cancel</button></div></section>}
    </div>
  );
}
