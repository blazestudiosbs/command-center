import { useState } from "react";
import Panel from "./Panel";

export default function AlertTestPanel() {
  const [result, setResult] = useState("");

  async function sendTestAlert() {
    setResult("Sending test alert...");

    try {
      const res = await fetch("/api/alerts/test", { method: "POST" });
      const data = await res.json();

      if (data.sent) {
        setResult("Test alert sent successfully.");
      } else {
        setResult(`Alert failed: ${data.error || data.response || "Unknown error"}`);
      }
    } catch (err) {
      setResult(`Alert failed: ${err.message}`);
    }
  }

  return (
    <Panel title="Alerts">
      <button onClick={sendTestAlert}>Send Test Alert</button>
      <p className="answer">{result || "Use this to verify Discord alerts are working."}</p>
    </Panel>
  );
}
