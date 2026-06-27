import Panel from "../../components/Panel";

export default function InfrastructurePage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Infrastructure Workspace</h1>
          <p className="page-subtitle">Infrastructure summaries and management tools.</p>
        </div>
      </header>

      <Panel title="Infrastructure Overview">
        <p className="answer">This workspace will host router, network, and infrastructure controls.</p>
      </Panel>
    </div>
  );
}
