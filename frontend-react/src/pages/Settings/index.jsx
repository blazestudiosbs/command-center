import Panel from "../../components/Panel";

export default function SettingsPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Settings Workspace</h1>
          <p className="page-subtitle">Application settings, preferences, and platform configuration.</p>
        </div>
      </header>

      <Panel title="Settings Overview">
        <p className="answer">Settings workspace will centralize configuration and workspace preferences.</p>
      </Panel>
    </div>
  );
}
