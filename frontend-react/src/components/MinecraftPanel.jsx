import { useEffect, useState } from "react";
import Panel from "./Panel";

export default function MinecraftPanel() {
  const [status, setStatus] = useState(null);
  const [player, setPlayer] = useState("");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState("");

  async function loadStatus() {
    const res = await fetch("/api/minecraft/status");
    const data = await res.json();
    setStatus(data);
  }

  async function post(url) {
    setResult("Running command...");
    const res = await fetch(url, { method: "POST" });
    const data = await res.json();
    setResult(data.response || data.error || JSON.stringify(data));
    loadStatus();
  }

  async function containerAction(action) {
  setResult(`${action} requested...`);

  const res = await fetch(`/api/minecraft/${action}`, { method: "POST" });
  const data = await res.json();

  setResult(data.ok ? `${action} complete.` : `Failed: ${data.error || data.stderr}`);
  loadStatus();
}

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, 15000);
    return () => clearInterval(timer);
  }, []);

  const players = status?.players ?? [];

  return (
    <Panel title="Minecraft ATM10">
      <div className="list">
        <div className="row">
          <strong>Status</strong>
          <span>{status?.online ? "online" : "offline"}</span>
        </div>

        <div className="row">
          <strong>Players</strong>
          <span>{status ? `${status.player_count} online` : "loading..."}</span>
        </div>

        <div className="row">
          <strong>Online</strong>
          <span>{players.length ? players.join(", ") : "No players online"}</span>
        </div>
      </div>

      <div className="panel-actions">
        <button onClick={() => post("/api/minecraft/save")}>Save World</button>
        <button onClick={loadStatus}>Refresh</button>
      </div>

      <div className="inline-form">
        <input
          value={player}
          onChange={(e) => setPlayer(e.target.value)}
          placeholder="Player name"
        />
        <button disabled={!player} onClick={() => post(`/api/minecraft/op?player=${encodeURIComponent(player)}`)}>
          OP
        </button>
        <button disabled={!player} onClick={() => post(`/api/minecraft/deop?player=${encodeURIComponent(player)}`)}>
          DEOP
        </button>
      </div>

      <div className="inline-form">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Broadcast message"
        />
        <button disabled={!message} onClick={() => post(`/api/minecraft/say?message=${encodeURIComponent(message)}`)}>
          Broadcast
        </button>
      </div>

      <p className="answer">{result || "Minecraft controls ready."}</p>
    </Panel>
  );
}
