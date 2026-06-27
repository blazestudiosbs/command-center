import Panel from "../../components/Panel";

export default function PlexPage() {
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Plex Workspace</h1>
          <p className="page-subtitle">Media server status, library overview, and playback controls.</p>
        </div>
      </header>

      <Panel title="Plex Overview">
        <p className="answer">Plex workspace is ready for future dedicated integration and controls.</p>
      </Panel>
    </div>
  );
}
