import { useEffect, useState } from "react";
import { getCalendarEvents, getCalendarStatus, startCalendarOAuth } from "../../services/api";


function displayTime(event) {
  if (event.all_day) return `${event.start} · All day`;
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(event.start));
}


export default function CalendarPage() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadStatus() {
    try { setStatus(await getCalendarStatus()); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Calendar status unavailable"); }
  }
  useEffect(() => { loadStatus(); }, []);

  async function connect() {
    setBusy(true);
    try { window.location.assign(await startCalendarOAuth()); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Calendar authorization could not start"); setBusy(false); }
  }

  async function loadEvents() {
    setBusy(true);
    try { setEvents((await getCalendarEvents(7)).events); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Upcoming events unavailable"); }
    finally { setBusy(false); }
  }

  return (
    <div className="page-content calendar-page">
      <header className="page-header">
        <div><h1>Calendar</h1><p className="page-subtitle">Read-only Google Calendar awareness for Vera.</p></div>
        <button type="button" className="secondary-button" onClick={loadStatus}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="gmail-connection">
        <div className="gmail-connection-heading"><div><small>Connection</small><h2>{status?.connected ? "Connected" : "Not connected"}</h2></div><span className={`monitoring-state ${status?.connected ? "running" : "pending"}`}>{status?.access || "Read only"}</span></div>
        <p>{status?.detail || "Checking Google Calendar…"}</p>
        {status?.account && <p><strong>Account:</strong> {status.account}</p>}
        <div className="gmail-safety-grid">
          <span><small>Read events</small><strong>{status?.authorized ? "Authorized" : "Not authorized"}</strong></span>
          <span><small>Create</small><strong>Blocked</strong></span>
          <span><small>Edit</small><strong>Blocked</strong></span>
          <span><small>Delete</small><strong>Blocked</strong></span>
        </div>
        {!status?.connected && <button type="button" className="secondary-button" disabled={busy || !status?.configured} onClick={connect}>Authorize Calendar read access</button>}
      </section>
      {status?.connected && (
        <section className="panel">
          <div className="calendar-events-heading"><div><h2>Next seven days</h2><p>Titles, times, and locations only.</p></div><button type="button" className="secondary-button" disabled={busy} onClick={loadEvents}>{busy ? "Loading…" : "Load upcoming events"}</button></div>
          <div className="calendar-events">{events.map((event) => <article key={event.id}><time>{displayTime(event)}</time><div><strong>{event.title}</strong>{event.location && <small>{event.location}</small>}</div></article>)}</div>
          {events.length === 0 && <p className="answer">Enable Calendar Agent → Read event titles and times, then load upcoming events.</p>}
        </section>
      )}
    </div>
  );
}
