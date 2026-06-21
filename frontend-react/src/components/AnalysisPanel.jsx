import Panel from "./Panel";

export default function AnalysisPanel({ analysis, loading, onAnalyze }) {
  return (
    <Panel title="AI Analysis">
      <button onClick={onAnalyze}>
        {loading ? "Analyzing..." : "Analyze Status"}
      </button>
      <p className="answer">
        {analysis || "Analyze current system health and risks."}
      </p>
    </Panel>
  );
}
