import { useCallback, useEffect, useState } from "react";
import { changeVeraControl, getVeraControl } from "../services/api";


const labels = {
  active: "Autonomy active",
  paused: "Autonomy paused",
  emergency_stop: "Emergency stop",
};


export default function VeraControl() {
  const [control, setControl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setControl(await getVeraControl());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || "Control state unavailable");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function change(action, reason) {
    setBusy(true);
    setError("");
    try {
      setControl(await changeVeraControl(action, reason, control?.version));
    } catch (err) {
      setError(err.response?.data?.detail || "Control change failed");
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!control) {
    return <div className="vera-control unavailable">{error || "Loading Vera controls…"}</div>;
  }

  const stopped = control.mode === "emergency_stop";
  const paused = control.mode === "paused";

  return (
    <section className={`vera-control ${control.mode}`} aria-label="Vera autonomy controls">
      <div>
        <span className="control-status-dot" />
        <strong>{labels[control.mode]}</strong>
        {error && <span className="control-error">{error}</span>}
      </div>
      <div className="control-actions">
        {control.mode === "active" && (
          <button type="button" className="control-pause" disabled={busy} onClick={() => change("pause", "Paused from Command Center")}>
            Pause autonomy
          </button>
        )}
        {(paused || stopped) && (
          <button type="button" className="control-resume" disabled={busy} onClick={() => change("resume", "Explicitly resumed from Command Center")}>
            Resume autonomy
          </button>
        )}
        {!stopped && (
          <button type="button" className="control-stop" disabled={busy} onClick={() => change("emergency-stop", "Emergency stop from Command Center")}>
            Emergency stop
          </button>
        )}
      </div>
    </section>
  );
}
