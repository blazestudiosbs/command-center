import { useEffect, useState } from "react";
import { executeRelease, getReleaseStatus, prepareRelease } from "../../services/api";

export default function ReleasesPage() {
  const [data, setData] = useState(null);
  const [message, setMessage] = useState("");
  const [deploy, setDeploy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    try { setData(await getReleaseStatus()); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Release status unavailable"); }
  }
  useEffect(() => { refresh(); }, []);

  async function prepare(event) {
    event.preventDefault(); setBusy(true); setNotice("");
    try { await prepareRelease(message, deploy); setMessage(""); setNotice("Release prepared. Review the exact files below before approval."); await refresh(); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Release could not be prepared"); }
    finally { setBusy(false); }
  }

  async function approve(release) {
    if (!window.confirm(`Approve commit and push of ${release.files.length} files${release.deploy_requested ? ", then deploy Command Center" : ""}?`)) return;
    setBusy(true); setNotice("");
    try { const result = await executeRelease(release.id); setNotice(`Committed and pushed ${result.commit_hash.slice(0, 8)}.${result.deployment_started ? " Deployment is starting; this page may reconnect briefly." : ""}`); await refresh(); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Approved release did not complete"); await refresh(); }
    finally { setBusy(false); }
  }

  const releases = data?.releases || [];
  return <div className="page-content releases-page">
    <header className="page-header"><div><h1>Releases</h1><p className="page-subtitle">Commit, push, and deploy only after your explicit approval.</p></div><button className="secondary-button" type="button" onClick={refresh}>Refresh</button></header>
    {error && <p className="journal-error">{error}</p>}{notice && <p className="answer">{notice}</p>}
    <section className="gmail-connection"><div className="gmail-connection-heading"><div><small>Release connection</small><h2>{data?.worker_ready && data?.github_push_configured ? "Ready" : "Setup required"}</h2></div><span className={`monitoring-state ${data?.worker_ready && data?.github_push_configured ? "running" : "pending"}`}>Approval required</span></div><div className="gmail-safety-grid"><span><small>Worker</small><strong>{data?.worker_ready ? "Ready" : "Unavailable"}</strong></span><span><small>GitHub push</small><strong>{data?.github_push_configured ? "Configured" : "Missing secret"}</strong></span><span><small>Branches</small><strong>codex/* only</strong></span><span><small>Force push</small><strong>Blocked</strong></span></div></section>
    <section className="panel release-prepare"><h2>Prepare a release</h2><p>This records the current branch, commit, changed files, and worktree fingerprint. Preparing does not commit, push, or deploy.</p><form onSubmit={prepare}><label>Commit message<input required maxLength="120" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Describe this release" /></label><label className="calendar-check"><input type="checkbox" checked={deploy} onChange={(event) => setDeploy(event.target.checked)} />Deploy Command Center after push</label><button className="primary-button" disabled={busy || !data?.worker_ready || !data?.github_push_configured}>Prepare for approval</button></form><p className="answer">Enable both release permissions under Agent Permissions. Secrets, runtime configuration, non-codex branches, arbitrary remotes, and changed approvals are blocked.</p></section>
    <section className="panel release-list"><h2>Release ledger</h2>{releases.length === 0 ? <p className="answer">No releases have been prepared.</p> : releases.map((release) => <article key={release.id}><div className="release-heading"><div><strong>{release.commit_message}</strong><small>{release.branch} · {new Date(release.created_utc).toLocaleString()}</small></div><span className={`monitoring-state ${release.status === "completed" ? "running" : "pending"}`}>{release.status}</span></div><div className="release-files">{release.files.map((file) => <code key={file}>{file}</code>)}</div>{release.error && <p className="journal-error">{release.error}</p>}{release.status === "pending" && <button className="primary-button" disabled={busy} onClick={() => approve(release)}>Approve commit, push{release.deploy_requested ? " & deploy" : ""}</button>}{release.commit_hash && <p><small>Commit {release.commit_hash}</small></p>}</article>)}</section>
  </div>;
}
