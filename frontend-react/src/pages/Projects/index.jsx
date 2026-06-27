import Panel from "../../components/Panel";

export default function ProjectsPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Projects Workspace</h1>
          <p className="page-subtitle">Project summaries, roadmaps, and task overviews.</p>
        </div>
      </header>

      <Panel title="Project Summary">
        <p className="answer">Projects workspace will provide dedicated tracking and status details.</p>
      </Panel>
    </div>
  );
}
