import Panel from "../../components/Panel";

export default function DevelopmentPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Development Workspace</h1>
          <p className="page-subtitle">Code-server, build pipelines, and development tooling.</p>
        </div>
      </header>

      <Panel title="Development Overview">
        <p className="answer">Development workspace will expose code and build workflows in a dedicated view.</p>
      </Panel>
    </div>
  );
}
