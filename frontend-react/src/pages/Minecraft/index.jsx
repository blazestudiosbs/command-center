import { useCallback, useEffect, useRef, useState } from "react";
import Panel from "../../components/Panel";
import {
  getMinecraftStatus,
  minecraftStart,
  minecraftStop,
  minecraftRestart,
  minecraftSave,
  minecraftOp,
  minecraftDeop,
  minecraftSay,
  getMinecraftLogs,
  sendMinecraftCommand,
} from "../../services/api";

function formatPercent(value) {
  return value == null ? "unknown" : `${value}%`;
}

function formatTime(date) {
  if (!date) return "not updated yet";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function resultText(response, fallback) {
  if (!response) return fallback;
  if (response.ok) return response.response || response.stdout || fallback;
  return response.error || response.stderr || JSON.stringify(response);
}

function getLogClass(line) {
  const lower = line.toLowerCase();

  if (line.includes("ERROR") || lower.includes("error")) return "log-line log-error";
  if (line.includes("WARN") || lower.includes("warn")) return "log-line log-warn";
  if (lower.includes("can't keep up")) return "log-line log-performance";
  if (lower.includes("joined the game")) return "log-line log-join";
  if (lower.includes("left the game") || lower.includes("disconnected")) return "log-line log-leave";
  return "log-line";
}

function StatusCard({ label, value, tone = "" }) {
  return (
    <div className={`card status-card ${tone}`.trim()}>
      <div className="label">{label}</div>
      <strong>{value}</strong>
    </div>
  );
}

function MinecraftPlayerRow({ player, disabled, onOp, onDeop, onKick, onBan }) {
  return (
    <div className="player-row">
      <div className="player-row-meta">
        <span className="player-row-name">{player}</span>
      </div>
      <div className="player-row-actions">
        <button disabled={disabled} onClick={() => onOp(player)}>OP</button>
        <button disabled={disabled} onClick={() => onDeop(player)}>DEOP</button>
        <button disabled={disabled} onClick={() => onKick(player)}>Kick</button>
        <button disabled={disabled} onClick={() => onBan(player)}>Ban</button>
      </div>
    </div>
  );
}

function TerminalConsole({ logs, loading, error, lastUpdated, command, onCommandChange, onSend, commandResult, disabled }) {
  const outputRef = useRef(null);

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [logs]);

  const handleSubmit = (event) => {
    event.preventDefault();
    onSend();
  };

  return (
    <div className="terminal-console">
      <div className="console-toolbar">
        <span>{loading ? "Refreshing logs..." : `Last updated: ${formatTime(lastUpdated)}`}</span>
        {error ? <span className="console-error">{error}</span> : null}
      </div>

      <div className="console-output" ref={outputRef} role="log" aria-live="polite">
        {logs.length ? (
          logs.map((line, index) => (
            <div className={getLogClass(line)} key={`${index}-${line.slice(0, 24)}`}>
              {line}
            </div>
          ))
        ) : (
          <div className="log-line muted">{loading ? "Loading logs..." : "No logs available."}</div>
        )}
      </div>

      <form className="inline-form console-command" onSubmit={handleSubmit}>
        <input
          value={command}
          onChange={(event) => onCommandChange(event.target.value)}
          placeholder="RCON command"
        />
        <button disabled={disabled || !command.trim()} type="submit">Send</button>
      </form>

      {commandResult ? (
        <div className={`action-result ${commandResult.ok ? "success" : "failure"}`}>
          {resultText(commandResult, "Command completed.")}
        </div>
      ) : null}
    </div>
  );
}

export default function MinecraftPage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState("");
  const [playerName, setPlayerName] = useState("");
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [logs, setLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(true);
  const [logsError, setLogsError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [command, setCommand] = useState("");
  const [commandResult, setCommandResult] = useState(null);
  const [actionState, setActionState] = useState({ label: "", status: "idle", message: "" });
  const tail = 240;

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await getMinecraftStatus();
      setStatus(data);
      setStatusError("");
    } catch (err) {
      setStatusError(err.message);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const data = await getMinecraftLogs(tail);
      if (!data.ok) {
        setLogsError(data.error || "Failed to load logs.");
      } else {
        setLogsError("");
      }
      setLogs(Array.isArray(data.stdout) ? data.stdout : (data.stdout || "").split("\n").filter(Boolean));
      setLastUpdated(new Date());
    } catch (err) {
      setLogsError(err.message);
    } finally {
      setLogsLoading(false);
    }
  }, [tail]);

  const refreshMinecraft = useCallback(async () => {
    await Promise.all([loadStatus(), loadLogs()]);
  }, [loadLogs, loadStatus]);

  const runAction = useCallback(async (actionFn, label, successText) => {
    setActionState({ label, status: "running", message: `${label}: Running...` });
    setCommandResult(null);

    try {
      const response = await actionFn();
      const ok = Boolean(response.ok);
      setActionState({
        label,
        status: ok ? "success" : "failure",
        message: ok ? `${label}: ${successText}` : `${label} failed: ${resultText(response, "Unknown error")}`,
      });
      return response;
    } catch (err) {
      setActionState({ label, status: "failure", message: `${label} failed: ${err.message}` });
      return { ok: false, error: err.message };
    } finally {
      await refreshMinecraft();
    }
  }, [refreshMinecraft]);

  const handlePlayerAction = async (apiFn, player, label) => {
    if (!player.trim()) return;
    await runAction(() => apiFn(player.trim()), label, "Complete.");
  };

  const handleBroadcast = async () => {
    const message = broadcastMessage.trim();
    if (!message) return;
    await runAction(() => minecraftSay(message), "Broadcast", "Message sent.");
    setBroadcastMessage("");
  };

  const handleSendCommand = async () => {
    const nextCommand = command.trim();
    if (!nextCommand) return;

    setActionState({ label: "Command", status: "running", message: "Command: Running..." });
    setCommandResult(null);

    try {
      const response = await sendMinecraftCommand(nextCommand);
      setCommandResult(response);
      setActionState({
        label: "Command",
        status: response.ok ? "success" : "failure",
        message: response.ok ? "Command: Sent." : `Command failed: ${resultText(response, "Unknown error")}`,
      });
    } catch (err) {
      const response = { ok: false, error: err.message };
      setCommandResult(response);
      setActionState({ label: "Command", status: "failure", message: `Command failed: ${err.message}` });
    } finally {
      setCommand("");
      await refreshMinecraft();
    }
  };

  useEffect(() => {
    refreshMinecraft();
    const timer = setInterval(refreshMinecraft, 3000);
    return () => clearInterval(timer);
  }, [refreshMinecraft]);

  const online = Boolean(status?.online);
  const players = Array.isArray(status?.players) ? status.players : [];
  const actionRunning = actionState.status === "running";

  return (
    <div className="page-content minecraft-page">
      <header className="page-header">
        <div>
          <h1>Minecraft Workspace</h1>
          <p className="page-subtitle">Live server administration for ATM10.</p>
        </div>
        <div className="minecraft-status-header">
          <div>
            <div className="label">Server</div>
            <div>{status?.server_name ?? "ATM10"}</div>
          </div>
          <div>
            <div className="label">State</div>
            <span className={`status-badge ${online ? "online" : "offline"}`}>
              {online ? "Running" : "Offline"}
            </span>
          </div>
          <div>
            <div className="label">Server Type</div>
            <div>{status?.version ?? "ATM10"}</div>
          </div>
        </div>
      </header>

      {statusError ? <div className="action-result failure">Status error: {statusError}</div> : null}

      <section className="status-cards-grid">
        <StatusCard label="State" value={statusLoading ? "Loading..." : online ? "Running" : "Offline"} tone={online ? "online" : "offline"} />
        <StatusCard label="Players Online" value={status ? `${status.player_count ?? 0}` : "Loading..."} />
        <StatusCard label="RAM Usage" value={formatPercent(status?.ram_usage)} />
        <StatusCard label="CPU Usage" value={formatPercent(status?.cpu_usage)} />
        <StatusCard label="Uptime" value={status?.uptime ?? "unknown"} />
        <StatusCard label="Server Type" value="ATM10" />
      </section>

      <section className="workspace-grid">
        <Panel title="Player List" className="panel-fullwidth">
          <div className="player-list-panel">
            {players.length ? (
              players.map((player) => (
                <MinecraftPlayerRow
                  key={player}
                  player={player}
                  disabled={!online || actionRunning}
                  onOp={(name) => handlePlayerAction(minecraftOp, name, "OP")}
                  onDeop={(name) => handlePlayerAction(minecraftDeop, name, "DEOP")}
                  onKick={(name) => runAction(() => sendMinecraftCommand(`/kick ${name}`), "Kick", "Player kicked.")}
                  onBan={(name) => runAction(() => sendMinecraftCommand(`/ban ${name}`), "Ban", "Player banned.")}
                />
              ))
            ) : (
              <div className="player-row">
                <div className="player-row-meta">
                  <span className="player-row-name">No players online</span>
                </div>
              </div>
            )}
          </div>

          <div className="inline-form">
            <input
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              placeholder="Player name"
            />
            <button disabled={!playerName.trim() || actionRunning} onClick={() => handlePlayerAction(minecraftOp, playerName, "OP")}>OP</button>
            <button disabled={!playerName.trim() || actionRunning} onClick={() => handlePlayerAction(minecraftDeop, playerName, "DEOP")}>DEOP</button>
            <button disabled={!playerName.trim() || actionRunning} onClick={() => runAction(() => sendMinecraftCommand(`/kick ${playerName.trim()}`), "Kick", "Player kicked.")}>Kick</button>
            <button disabled={!playerName.trim() || actionRunning} onClick={() => runAction(() => sendMinecraftCommand(`/ban ${playerName.trim()}`), "Ban", "Player banned.")}>Ban</button>
          </div>
        </Panel>

        <Panel title="Server Actions" className="panel-fullwidth">
          <div className="server-actions">
            <button disabled={actionRunning} onClick={() => runAction(minecraftStart, "Start", "Server start requested.")}>Start</button>
            <button disabled={actionRunning} onClick={() => runAction(minecraftRestart, "Restart", "Server restart requested.")}>Restart</button>
            <button disabled={actionRunning || !online} onClick={() => runAction(minecraftStop, "Stop", "Server stop requested.")}>Stop</button>
            <button disabled={actionRunning || !online} onClick={() => runAction(minecraftSave, "Save World", "World save requested.")}>Save World</button>
          </div>

          <div className="inline-form">
            <input
              value={broadcastMessage}
              onChange={(e) => setBroadcastMessage(e.target.value)}
              placeholder="Broadcast message"
            />
            <button disabled={!broadcastMessage.trim() || actionRunning} onClick={handleBroadcast}>Broadcast</button>
          </div>

          {actionState.message ? (
            <div className={`action-result ${actionState.status}`}>
              {actionState.message}
            </div>
          ) : null}
        </Panel>
      </section>

      <Panel title="Live Console" className="panel-fullwidth">
        <TerminalConsole
          logs={logs}
          loading={logsLoading}
          error={logsError}
          lastUpdated={lastUpdated}
          command={command}
          onCommandChange={setCommand}
          onSend={handleSendCommand}
          commandResult={commandResult}
          disabled={actionRunning}
        />
      </Panel>
    </div>
  );
}
