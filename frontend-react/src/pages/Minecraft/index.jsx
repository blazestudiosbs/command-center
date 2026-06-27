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
  minecraftKick,
  minecraftBan,
  minecraftSay,
  getMinecraftLogs,
  sendMinecraftCommand,
} from "../../services/api";

function formatPercent(value) {
  return value == null ? "unknown" : `${value}%`;
}

function formatBytes(bytes) {
  if (bytes == null) return "unknown";
  const gib = bytes / 1024 / 1024 / 1024;
  if (gib >= 1) return `${gib.toFixed(1)} GB`;
  const mib = bytes / 1024 / 1024;
  return `${mib.toFixed(0)} MB`;
}

function formatRam(status) {
  if (!status) return "Loading...";
  const percent = formatPercent(status.ram_usage);
  if (status.ram_usage_bytes == null) return percent;
  if (status.ram_limit_bytes == null) return `${formatBytes(status.ram_usage_bytes)} (${percent})`;
  return `${formatBytes(status.ram_usage_bytes)} / ${formatBytes(status.ram_limit_bytes)} (${percent})`;
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

function isRconNoise(line) {
  const lower = line.toLowerCase();
  return (
    (lower.includes("rcon client") && (lower.includes("started") || lower.includes("shutting down"))) ||
    lower.includes("rcon listener") ||
    lower.includes("rcon running")
  );
}

function getLogClass(line) {
  const lower = line.toLowerCase();

  if (line.includes("ERROR") || lower.includes("error") || lower.includes("exception") || lower.includes("fatal")) return "log-line log-error";
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

function MinecraftPlayerRow({ player, selected, onSelect }) {
  return (
    <button
      className={`player-row player-select ${selected ? "selected" : ""}`.trim()}
      onClick={() => onSelect(player)}
      type="button"
    >
      <div className="player-row-meta">
        <span className="player-row-name">{player}</span>
        {selected ? <span className="player-selected-label">Selected</span> : null}
      </div>
    </button>
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
          <strong>{commandResult.ok ? "Command result" : "Command failed"}</strong>
          <div className="command-result-body">
            {commandResult.command ? <span className="command-result-command">/{commandResult.command}</span> : null}
            <span>{resultText(commandResult, "Command completed.")}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function MinecraftPage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState("");
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
      const nextLogs = Array.isArray(data.stdout) ? data.stdout : (data.stdout || "").split("\n").filter(Boolean);
      setLogs(nextLogs.filter((line) => !isRconNoise(line)));
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

  const handlePlayerAction = async (apiFn, label, successText = "Complete.") => {
    if (!selectedPlayer) return;
    await runAction(() => apiFn(selectedPlayer), label, successText);
  };

  const handleStop = () => {
    if (!window.confirm("Stop the Minecraft server? Online players will be disconnected.")) return;
    runAction(minecraftStop, "Stop", "Server stop requested.");
  };

  const handleRestart = () => {
    if (!window.confirm("Restart the Minecraft server now? Online players will be disconnected temporarily.")) return;
    runAction(minecraftRestart, "Restart", "Server restart requested.");
  };

  const handleBan = () => {
    if (!selectedPlayer) return;
    if (!window.confirm(`Ban ${selectedPlayer} from the Minecraft server?`)) return;
    runAction(() => minecraftBan(selectedPlayer), "Ban", "Player banned.");
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
  const running = Boolean(status?.running ?? status?.online);
  const stateLabel = status?.state ?? (online ? "Running" : "Offline");
  const players = Array.isArray(status?.players) ? status.players : [];
  const actionRunning = actionState.status === "running";
  const selectedPlayerOnline = selectedPlayer && players.includes(selectedPlayer);
  const playerActionDisabled = !selectedPlayerOnline || !online || actionRunning;

  useEffect(() => {
    if (selectedPlayer && !players.includes(selectedPlayer)) {
      setSelectedPlayer("");
    }
  }, [players, selectedPlayer]);

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
            <span className={`status-badge ${running ? "online" : "offline"}`}>
              {stateLabel}
            </span>
          </div>
          <div>
            <div className="label">Server Type</div>
            <div>{status?.server_type ?? status?.version ?? "ATM10 / NeoForge"}</div>
          </div>
        </div>
      </header>

      {statusError ? <div className="action-result failure">Status error: {statusError}</div> : null}

      <section className="status-cards-grid">
        <StatusCard label="State" value={statusLoading ? "Loading..." : stateLabel} tone={running ? "online" : "offline"} />
        <StatusCard label="Players" value={status ? `${status.player_count ?? 0}${status.max_players ? ` / ${status.max_players}` : ""}` : "Loading..."} />
        <StatusCard label="RAM" value={formatRam(status)} />
        <StatusCard label="CPU Usage" value={formatPercent(status?.cpu_usage)} />
        <StatusCard label="Uptime" value={status?.uptime ?? "unknown"} />
        <StatusCard label="Server Type" value={status?.server_type ?? status?.version ?? "ATM10 / NeoForge"} />
      </section>

      <section className="workspace-grid">
        <Panel title="Player List" className="panel-fullwidth">
          <div className="player-list-panel">
            {players.length ? (
              players.map((player) => (
                <MinecraftPlayerRow
                  key={player}
                  player={player}
                  selected={selectedPlayer === player}
                  onSelect={setSelectedPlayer}
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

          <div className="selected-player-panel">
            <div>
              <div className="label">Selected player</div>
              <strong>{selectedPlayer || "No player selected"}</strong>
            </div>
            <div className="player-row-actions">
              <button disabled={playerActionDisabled} onClick={() => handlePlayerAction(minecraftOp, "OP")}>OP</button>
              <button disabled={playerActionDisabled} onClick={() => handlePlayerAction(minecraftDeop, "DEOP")}>DEOP</button>
              <button disabled={playerActionDisabled} onClick={() => handlePlayerAction(minecraftKick, "Kick", "Player kicked.")}>Kick</button>
              <button disabled={playerActionDisabled} onClick={handleBan}>Ban</button>
            </div>
          </div>
        </Panel>

        <Panel title="Server Actions" className="panel-fullwidth">
          <div className="server-actions">
            <button disabled={actionRunning || running} onClick={() => runAction(minecraftStart, "Start", "Server start requested.")}>Start</button>
            <button disabled={actionRunning || !online} onClick={handleRestart}>Restart</button>
            <button disabled={actionRunning || !online} onClick={handleStop}>Stop</button>
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
