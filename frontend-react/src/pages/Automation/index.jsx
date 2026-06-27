import Panel from "../../components/Panel";

export default function AutomationPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Automation Workspace</h1>
          <p className="page-subtitle">Automation tasks, schedulers, and event triggers.</p>
        </div>
      </header>

      <Panel title="Automation Overview">
        <p className="answer">Automation workspace is ready for workflow orchestration and event-driven tooling.</p>
      </Panel>
    </div>
  );
}
