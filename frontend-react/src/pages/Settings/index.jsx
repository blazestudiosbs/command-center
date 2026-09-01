import { useEffect, useState } from "react";
import { getHouseholdMembers, getPendingVoiceIdentities, linkPendingVoiceIdentity } from "../../services/api";

export default function SettingsPage() {
  const [members, setMembers] = useState([]);
  const [pending, setPending] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [householdMembers, identities] = await Promise.all([getHouseholdMembers(), getPendingVoiceIdentities()]);
      setMembers(householdMembers);
      setPending(identities);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Voice identities are unavailable.");
    }
  }

  useEffect(() => { load(); }, []);

  async function link(identity, memberId) {
    setBusy(true);
    try {
      await linkPendingVoiceIdentity(identity.id, memberId);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "The Echo profile could not be linked.");
    } finally {
      setBusy(false);
    }
  }

  const owner = members.find((member) => member.role === "owner");
  return (
    <div className="page-content">
      <header className="page-header">
        <div><h1>Settings</h1><p className="page-subtitle">Command Center preferences and household access.</p></div>
        <button type="button" className="secondary-button" onClick={load} disabled={busy}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="panel">
        <h2>Echo voice profiles</h2>
        <p className="answer">Review an Echo profile before assigning it to a Vera household member. Linking is recorded in the audit journal.</p>
        {pending.length === 0 && <p className="answer">No Echo profiles are waiting to be linked.</p>}
        <div className="monitoring-services">
          {pending.map((identity) => <article className="monitoring-service" key={identity.id}>
            <div><strong>Amazon Alexa</strong><small>Profile {identity.fingerprint} · heard {identity.seen_count} times</small></div>
            <div className="monitoring-service-state"><span className="monitoring-state stopped">Pending</span><small>Last heard {new Date(identity.last_seen_utc).toLocaleString()}</small></div>
            <button type="button" className="secondary-button" disabled={busy || !owner} onClick={() => link(identity, owner.id)}>Link to {owner?.display_name || "owner"}</button>
          </article>)}
        </div>
      </section>
    </div>
  );
}
