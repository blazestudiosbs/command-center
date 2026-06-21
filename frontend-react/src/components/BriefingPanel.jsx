import Panel from "./Panel";

export default function BriefingPanel({ briefing, loading, onGenerate }) {
  return (
    <Panel title="Daily Briefing">
      <button onClick={onGenerate}>
        {loading ? "Generating..." : "Generate Briefing"}
      </button>
      <p className="answer">
        {briefing || "Generate a project and infrastructure briefing."}
      </p>
    </Panel>
  );
}
