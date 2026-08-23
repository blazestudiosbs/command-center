import { useEffect, useState } from "react";
import { getProjectAwareness } from "../../services/api";


export default function ProjectsPage() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try { setOverview(await getProjectAwareness()); setError(""); }
    catch (err) { setError(err.response?.data?.detail || err.message || "Project awareness unavailable"); }
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="page-content projects-page">
      <header className="page-header">
        <div><h1>Projects</h1><p className="page-subtitle">Read-only awareness of active projects and repository state.</p></div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      {overview && <div className="project-awareness-note"><strong>Local repository awareness</strong><span>No fetch, push, issue, or pull-request operations are performed.</span></div>}
      <section className="project-awareness-grid">
        {(overview?.projects || []).map((project) => {
          const repository = project.repository;
          return (
            <article className="project-awareness-card" key={project.name}>
              <div className="project-awareness-heading">
                <div><h2>{project.name}</h2><p>{project.type} · {project.priority} priority</p></div>
                <span className={`dev-badge ${project.status === "active" ? "good" : "muted"}`}>{project.status}</span>
              </div>
              {!project.linked && <p className="project-unlinked">No local repository path is linked yet.</p>}
              {project.linked && !repository && <p className="project-unlinked">The development worker could not read this repository.</p>}
              {repository && (
                <>
                  <div className="project-repo-facts">
                    <span><small>Branch</small><strong>{repository.branch}</strong></span>
                    <span><small>Worktree</small><strong>{repository.worktree}</strong></span>
                    <span><small>Changed files</small><strong>{repository.changed_file_count}</strong></span>
                    <span><small>Tracking</small><strong>{repository.ahead ?? "—"} ahead · {repository.behind ?? "—"} behind</strong></span>
                  </div>
                  {repository.latest_commit && <div className="project-latest-commit"><code>{repository.latest_commit.hash}</code><div><strong>{repository.latest_commit.message}</strong><small>{repository.latest_commit.created_utc}</small></div></div>}
                  {repository.github_url && <a className="button-link project-github-link" href={repository.github_url} target="_blank" rel="noreferrer">Open GitHub repository</a>}
                  <small className="project-tracking-note">{repository.remote_state_note}</small>
                </>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}
