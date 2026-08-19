import { useCallback, useEffect, useRef, useState } from "react";
import Panel from "../../components/Panel";
import {
  completeTask,
  completeTaskPhase,
  createTask,
  deleteTask,
  failTask,
  failTaskPhase,
  getDevelopmentStatus,
  getTaskEvents,
  getTaskLogs,
  getTasks,
  getWorkersStatus,
  initializeTaskPhases,
  retryTask,
  runTaskCommand,
  runTaskRebuild,
  runTaskValidation,
  setTaskExecutionStage,
  startTask,
  startTaskPhase,
  updateTask,
} from "../../services/api";

const toolLabels = [
  ["codex_cli_available", "Codex CLI"],
  ["node_available", "Node"],
  ["npm_available", "npm"],
  ["python_available", "Python"],
  ["git_available", "Git"],
  ["docker_available", "Docker SDK"],
];

const emptyForm = {
  project: "Command Center",
  workspace: "Development",
  title: "",
  goal: "",
  constraints: "",
  execution_mode: "safe_edit",
  allowed_paths: "",
  validation_commands: "python3 -m py_compile backend/app.py\ncd frontend-react && npm run build",
  requires_manual_approval: false,
  priority: "medium",
};

const executionModeLabels = {
  read_only: "Read Only",
  safe_edit: "Safe Edit",
  full_agent: "Full Agent",
};

const executionStages = ["Queued", "Planning", "Reading", "Editing", "Building", "Testing", "Review", "Completed"];

const activeStages = new Set(["Planning", "Reading", "Editing", "Building", "Testing"]);

const commandLabels = {
  backend_compile: "Backend compile",
  frontend_build: "Frontend build",
  clear_frontend: "Clear static frontend",
  copy_frontend_dist: "Copy frontend dist",
  docker_compose_build: "Docker compose rebuild",
  git_diff_stat: "Git diff stat",
  git_status_short: "Git status",
};

const workerCapabilityLabels = {
  git: "Git",
  docker: "Docker",
  python: "Python",
  node: "Node",
  npm: "npm",
  jq: "jq",
  validation: "Validation",
  rebuild: "Rebuild",
  diff: "Diff",
};

const workerToolLabels = {
  git: "Git",
  docker: "Docker",
  python: "Python",
  node: "Node",
  npm: "npm",
  jq: "jq",
};

function StatusBadge({ active, tone = "", children }) {
  return <span className={`dev-badge ${tone || (active ? "good" : "muted")}`}>{children}</span>;
}

function priorityTone(priority) {
  if (priority === "high") return "hot";
  if (priority === "medium") return "info";
  return "muted";
}

function workerTone(status) {
  if (status === "Ready") return "good";
  if (status === "Starting" || status === "Busy") return "info";
  if (status === "Degraded" || status === "Offline") return "hot";
  return "muted";
}

function workerLabel(status) {
  if (status === "Ready") return "Worker Ready";
  if (status === "Starting") return "Worker Booting";
  if (status === "Busy") return "Worker Busy";
  if (status === "Degraded") return "Worker Degraded";
  return "Worker Offline";
}

function formatDate(value) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatElapsed(value) {
  if (!value) return "Not started";
  const started = new Date(value).getTime();
  if (Number.isNaN(started)) return "Unknown";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function currentStage(task) {
  if (!task) return "Queued";
  if (task.execution_stage) return task.execution_stage;
  if (task.status === "Running") return "Planning";
  return task.status || "Queued";
}

function stageProgress(stage) {
  const index = executionStages.indexOf(stage);
  if (index < 0) return 0;
  return Math.round((index / (executionStages.length - 1)) * 100);
}

function nextManualStage(stage) {
  const manualStages = ["Planning", "Reading", "Editing", "Building", "Testing", "Review"];
  const index = manualStages.indexOf(stage);
  if (index < 0 || index === manualStages.length - 1) return null;
  return manualStages[index + 1];
}

function parseLogEntries(logs) {
  if (!logs) return [];
  return logs.split("\n").map((line) => {
    const match = line.match(/^\[(.+?)\]\s*(.*)$/);
    if (!match) return { time: "--:--:--", message: line };
    const date = new Date(match[1]);
    const time = Number.isNaN(date.getTime()) ? match[1] : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return { time, message: match[2] };
  }).filter((entry) => entry.message.trim());
}

function eventTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function eventLabel(event) {
  const commandLabel = commandLabels[event.data?.command_key];
  if (event.type === "command_started") return `Started ${commandLabel || event.message}`;
  if (event.type === "command_finished") return `Finished ${commandLabel || event.message}`;
  if (event.type === "command_output") return event.message;
  if (event.type === "diff_preview") return "Git diff stat updated";
  if (event.type === "stage_changed") return event.message;
  if (event.type === "error") return `Error: ${event.message}`;
  return event.message;
}

function latestDiffStat(events) {
  const event = [...events].reverse().find((item) => item.type === "diff_preview" && item.data?.stat);
  return event?.data?.stat || "";
}

function recentCommandOutput(events) {
  return events.filter((event) => event.type === "command_output" && event.message).slice(-5);
}

function taskHistory(task) {
  if (!task) return [];
  const entries = [{ label: "Created", value: task.created_utc }];
  if (task.started_utc) entries.push({ label: "Started", value: task.started_utc });
  if (task.completed_utc) entries.push({ label: "Completed", value: task.completed_utc });
  entries.push({ label: "Current Status", value: task.status });
  return entries;
}

function policyList(value, fallbackText) {
  return value?.length ? (
    <ul>
      {value.map((item) => <li key={item}>{item}</li>)}
    </ul>
  ) : <p>{fallbackText}</p>;
}

function ToolHealth({ status }) {
  return (
    <div className="dev-tool-grid">
      {toolLabels.map(([key, label]) => {
        const available = Boolean(status?.[key]);
        return (
          <div className="dev-tool-card" key={key}>
            <span>{label}</span>
            <StatusBadge active={available}>{available ? "Available" : "Unavailable"}</StatusBadge>
          </div>
        );
      })}
    </div>
  );
}

function WorkerManager({ worker, loading, error }) {
  const status = worker?.status || "Offline";
  const tools = worker?.tools || {};
  const capabilities = worker?.capabilities || [];

  return (
    <div className={`worker-manager ${status.toLowerCase()}`}>
      {error ? <div className="action-result failure">Worker status error: {error}</div> : null}
      <header className="worker-manager-header">
        <div>
          <span className="dev-active-label">Development Worker</span>
          <h3>{worker?.name || "development-worker"}</h3>
          <p>{loading ? "Checking worker status..." : worker?.status_message || "Worker status has not loaded yet."}</p>
        </div>
        <StatusBadge active={status === "Ready"} tone={workerTone(status)}>{workerLabel(status)}</StatusBadge>
      </header>

      <section className="worker-state-grid">
        <div>
          <span>Online</span>
          <StatusBadge active={Boolean(worker?.online)}>{worker?.online ? "Online" : "Offline"}</StatusBadge>
        </div>
        <div>
          <span>Ready</span>
          <StatusBadge active={Boolean(worker?.ready)}>{worker?.ready ? "Ready" : "Not Ready"}</StatusBadge>
        </div>
        <div>
          <span>Current Task</span>
          <strong>{worker?.current_task || "None"}</strong>
        </div>
        <div>
          <span>Last Heartbeat</span>
          <strong>{formatDate(worker?.last_heartbeat)}</strong>
        </div>
      </section>

      <section className="worker-section">
        <div className="worker-section-title">Capabilities</div>
        <div className="worker-capability-grid">
          {capabilities.map((capability) => (
            <div className="worker-chip" key={capability}>{workerCapabilityLabels[capability] || capability}</div>
          ))}
        </div>
      </section>

      <section className="worker-section">
        <div className="worker-section-title">Tool Health</div>
        <div className="worker-tool-grid">
          {Object.entries(workerToolLabels).map(([key, label]) => {
            const available = Boolean(tools[key]);
            return (
              <div className="worker-tool-card" key={key}>
                <span>{label}</span>
                <StatusBadge active={available}>{available ? "Healthy" : "Missing"}</StatusBadge>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function RecentCommits({ commits }) {
  if (!commits?.length) {
    return <p className="answer">No recent commits available from this repository path.</p>;
  }

  return (
    <div className="dev-commit-list">
      {commits.map((commit) => (
        <div className="dev-commit-row" key={`${commit.hash}-${commit.message}`}>
          <code>{commit.hash}</code>
          <div>
            <strong>{commit.message}</strong>
            <span>{commit.author} - {commit.relative_time}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function TaskCountSummary({ counts }) {
  return (
    <section className="dev-task-counts" aria-label="Task status summary">
      {Object.entries(counts).map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

function ActiveTaskBanner({ task, busy, onViewLog, onComplete, onFail }) {
  if (!task) {
    return (
      <section className="dev-active-banner idle">
        <div>
          <span className="dev-active-label">Active Task</span>
          <strong>No active task</strong>
        </div>
      </section>
    );
  }

  return (
    <section className="dev-active-banner running">
      <div className="dev-active-main">
        <span className="dev-running-dot" aria-hidden="true" />
        <div>
          <span className="dev-active-label">Active Task</span>
          <strong>{task.title}</strong>
          <p>Task is running in manual execution mode</p>
        </div>
      </div>
      <div className="dev-active-meta">
        <div>
          <span>Project</span>
          <strong>{task.project}</strong>
        </div>
        <div>
          <span>Workspace</span>
          <strong>{task.workspace}</strong>
        </div>
        <div>
          <span>Started</span>
          <strong>{formatDate(task.started_utc)}</strong>
        </div>
        <StatusBadge active>{task.status}</StatusBadge>
      </div>
      <div className="dev-active-actions">
        <button type="button" onClick={() => onViewLog(task)}>View Log</button>
        <button disabled={busy} type="button" onClick={() => onComplete(task)}>{busy ? "Saving..." : "Complete"}</button>
        <button disabled={busy} type="button" onClick={() => onFail(task)}>{busy ? "Saving..." : "Fail"}</button>
      </div>
    </section>
  );
}

function StageTimeline({ stage }) {
  return (
    <div className="dev-stage-timeline">
      {executionStages.map((item) => (
        <div className={`dev-stage-step ${item === stage ? "active" : ""} ${executionStages.indexOf(item) < executionStages.indexOf(stage) ? "done" : ""}`} key={item}>
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

function PhasePanel({ task, phaseBusy, onPhaseAction }) {
  const phases = task?.phases || [];

  return (
    <section className="mission-phases-panel">
      <div className="mission-phases-header">
        <div>
          <span className="dev-active-label">Phases</span>
          <strong>Phase controls are manual until worker execution is enabled.</strong>
        </div>
      </div>
      {phases.length ? (
        <div className="mission-phase-list">
          {phases.map((phase) => (
            <div className={`mission-phase-row ${phase.status?.toLowerCase() || "pending"}`} key={phase.name}>
              <div>
                <strong>{phase.name}</strong>
                <StatusBadge active={phase.status === "Completed"} tone={phase.status === "Failed" ? "hot" : phase.status === "Running" ? "info" : ""}>{phase.status}</StatusBadge>
              </div>
              <div className="mission-phase-times">
                <span>Started: {formatDate(phase.started_utc)}</span>
                <span>Completed: {formatDate(phase.completed_utc)}</span>
              </div>
              {phase.summary ? <p>{phase.summary}</p> : null}
              <div className="mission-phase-actions">
                <button disabled={!task || phaseBusy} type="button" onClick={() => onPhaseAction(task, phase.name, "start")}>{phaseBusy ? "Saving..." : "Start Phase"}</button>
                <button disabled={!task || phaseBusy} type="button" onClick={() => onPhaseAction(task, phase.name, "complete")}>{phaseBusy ? "Saving..." : "Complete Phase"}</button>
                <button disabled={!task || phaseBusy} type="button" onClick={() => onPhaseAction(task, phase.name, "fail")}>{phaseBusy ? "Saving..." : "Fail Phase"}</button>
              </div>
            </div>
          ))}
        </div>
      ) : <p>No phases initialized.</p>}
    </section>
  );
}

function MissionControl({ task, events, eventError, busy, commandBusy, phaseBusy, workerStatus, workerMessage, lastUpdated, onViewLog, onComplete, onFail, onNextStage, onRunValidation, onRunRebuild, onRunDiffStat, onRefreshEvents, onPhaseAction }) {
  const stage = currentStage(task);
  const progress = stageProgress(stage);
  const isActive = task?.status === "Running" || activeStages.has(stage);
  const isReview = stage === "Review" || task?.status === "Review";
  const nextStage = nextManualStage(stage);
  const statusText = isReview ? "Awaiting Review" : task?.status || "Idle";
  const diffStat = latestDiffStat(events);
  const outputLines = recentCommandOutput(events);
  const backendWorkerState = workerStatus?.status || "Offline";
  const workerState = commandBusy ? "Busy" : backendWorkerState;
  const workerReady = Boolean(workerStatus?.ready) && workerState === "Ready";
  const workerReason = commandBusy ? "Worker is running an allowlisted command." : workerStatus?.status_message || "Worker status is unavailable.";
  const workerTools = workerStatus?.tools || {};
  const workerActionDisabled = !task || commandBusy || !workerReady;

  return (
    <div className="mission-control">
      <header className="mission-header">
        <div>
          <span className="dev-active-label">Mission Control</span>
          <h3>{task ? task.title : "No active task"}</h3>
          <p>{task ? "Manual mode: no automated worker is running." : "No active task"}</p>
        </div>
        <div className="mission-run-state">
          <span className={isActive && !isReview ? "dev-running-dot" : "dev-idle-dot"} aria-hidden="true" />
          <StatusBadge active={Boolean(isActive || isReview)} tone={task?.status === "Failed" ? "hot" : isReview ? "info" : ""}>{statusText}</StatusBadge>
        </div>
      </header>

      {task ? (
        <section className="mission-manual-notice">
          <strong>Manual mode: no automated worker is running.</strong>
          <span>Use Next Stage to update progress. Codex execution remains disabled.</span>
        </section>
      ) : null}

      <section className="mission-worker-actions">
        <div>
          <span className="dev-active-label">Worker Actions</span>
          <strong>{workerLabel(workerState)}</strong>
          <StatusBadge active={workerReady} tone={workerTone(workerState)}>{workerState}</StatusBadge>
          <p>These buttons execute allowlisted commands inside development-worker. Codex remains disabled.</p>
          <div className="mission-worker-tools">
            {Object.entries({ git: "git", docker: "docker", python: "python", node: "node", npm: "npm", jq: "jq" }).map(([key, label]) => (
              <StatusBadge key={key} active={Boolean(workerTools[key])}>{label}</StatusBadge>
            ))}
          </div>
        </div>
        <div className="mission-worker-buttons">
          <button disabled={workerActionDisabled} type="button" onClick={() => onRunValidation(task)}>{commandBusy ? "Running..." : "Run Validation"}</button>
          <button disabled={workerActionDisabled} type="button" onClick={() => onRunRebuild(task)}>{commandBusy ? "Running..." : "Run Rebuild"}</button>
          <button disabled={workerActionDisabled} type="button" onClick={() => onRunDiffStat(task)}>{commandBusy ? "Running..." : "Run Diff Stat"}</button>
          <button disabled={!task || commandBusy} type="button" onClick={() => onRefreshEvents(task)}>{commandBusy ? "Refreshing..." : "Refresh Events"}</button>
        </div>
        {!workerReady ? <div className={`action-result ${workerState === "Starting" || workerState === "Busy" ? "running" : "failure"}`}>{workerReason}</div> : null}
        {workerMessage?.text ? <div className={`action-result ${workerMessage.tone}`}>{workerMessage.text}</div> : null}
      </section>

      <section className="mission-summary-grid">
        <div>
          <span>Project</span>
          <strong>{task?.project || "None"}</strong>
        </div>
        <div>
          <span>Workspace</span>
          <strong>{task?.workspace || "None"}</strong>
        </div>
        <div>
          <span>Elapsed Time</span>
          <strong>{formatElapsed(task?.started_utc)}</strong>
        </div>
        <div>
          <span>Execution Stage</span>
          <strong>{isReview ? "Awaiting Review" : stage}</strong>
        </div>
        <div>
          <span>Last Updated</span>
          <strong>{lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Not loaded"}</strong>
        </div>
      </section>

      <section className="mission-progress-card">
        <div className="mission-progress-header">
          <span>Progress</span>
          <strong>{progress}%</strong>
        </div>
        <div className="mission-progress-track">
          <div style={{ width: `${progress}%` }} />
        </div>
        <StageTimeline stage={stage} />
      </section>

      <PhasePanel task={task} phaseBusy={phaseBusy} onPhaseAction={onPhaseAction} />

      <section className="mission-grid">
        <div className="mission-card mission-feed">
          <h4>Worker Event Stream</h4>
          {eventError ? <div className="action-result failure">Worker event error: {eventError}</div> : null}
          {events.length ? (
            <div className="mission-feed-list">
              {events.map((event, index) => (
                <div className={`mission-event-row ${event.type}`} key={`${event.utc}-${event.type}-${index}`}>
                  <time>{eventTime(event.utc)}</time>
                  <span>{eventLabel(event)}</span>
                </div>
              ))}
            </div>
          ) : <p>No worker activity yet.</p>}
        </div>

        <div className="mission-card">
          <h4>Recent Changes</h4>
          {diffStat ? (
            <div className="mission-change-list">
              <div>
                <strong>git diff --stat</strong>
                <pre>{diffStat}</pre>
              </div>
            </div>
          ) : <p>No diff stat yet. Run git diff --stat to populate this panel.</p>}
        </div>

        <div className="mission-card">
          <h4>Execution Output</h4>
          {outputLines.length ? (
            <div className="mission-output-lines">
              {outputLines.map((event, index) => <pre key={`${event.utc}-${index}`}>{event.message}</pre>)}
            </div>
          ) : <p>No command output yet.</p>}
        </div>

        <div className="mission-card">
          <h4>Current File</h4>
          <div className="mission-current-file">
            <span>Currently Reading</span>
            <strong>backend/services/advisor_service.py</strong>
          </div>
        </div>
      </section>

      {isReview ? (
        <section className="mission-approval-panel">
          <div>
            <span className="dev-active-label">Approval Panel</span>
            <strong>Awaiting Review</strong>
          </div>
          <div className="dev-task-actions">
            <button type="button">Approve</button>
            <button type="button">Reject</button>
            <button type="button">Request Changes</button>
          </div>
        </section>
      ) : null}

      <section className="mission-actions">
        <button disabled={!task} type="button" onClick={() => onViewLog(task)}>View Log</button>
        <button className="mission-secondary-action" disabled={!task || !nextStage || busy || commandBusy} type="button" onClick={() => onNextStage(task, nextStage)}>{nextStage ? `Manual Stage: ${nextStage}` : "Manual Stage"}</button>
        <button disabled={!task || busy} type="button" onClick={() => onComplete(task)}>{busy ? "Saving..." : "Complete"}</button>
        <button disabled={!task || busy} type="button" onClick={() => onFail(task)}>{busy ? "Saving..." : "Fail"}</button>
      </section>
    </div>
  );
}

function TaskCard({ task, onView, onEdit, onDelete, onStart, onComplete, onFail, onRetry, busy }) {
  return (
    <article className={`dev-task-card ${task.status === "Running" ? "running" : ""}`}>
      <div className="dev-task-card-header">
        <div>
          <strong>{task.title}</strong>
          <span>{task.project} / {task.workspace}</span>
        </div>
        <StatusBadge tone={priorityTone(task.priority)}>{task.priority}</StatusBadge>
      </div>
      <div className="dev-task-meta">
        <span>Status</span>
        <StatusBadge active={task.status === "Completed"} tone={task.status === "Failed" ? "hot" : ""}>{task.status}</StatusBadge>
        <span>Created</span>
        <strong>{formatDate(task.created_utc)}</strong>
      </div>
      <div className="dev-task-actions">
        <button type="button" onClick={() => onView(task)}>View</button>
        {task.status === "Queued" ? <button disabled={busy} type="button" onClick={() => onStart(task)}>{busy ? "Starting..." : "Start"}</button> : null}
        {task.status === "Running" ? <button disabled={busy} type="button" onClick={() => onComplete(task)}>{busy ? "Saving..." : "Complete"}</button> : null}
        {task.status === "Running" ? <button disabled={busy} type="button" onClick={() => onFail(task)}>{busy ? "Saving..." : "Fail"}</button> : null}
        {task.status === "Failed" ? <button disabled={busy} type="button" onClick={() => onRetry(task)}>{busy ? "Retrying..." : "Retry"}</button> : null}
        <button type="button" onClick={() => onEdit(task)}>Edit</button>
        <button type="button" onClick={() => onDelete(task)}>Delete</button>
      </div>
    </article>
  );
}

function TaskList({ tasks, emptyText, onView, onEdit, onDelete, onStart, onComplete, onFail, onRetry, busyTaskId }) {
  if (!tasks.length) {
    return <p className="answer">{emptyText}</p>;
  }

  return (
    <div className="dev-task-list">
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onView={onView}
          onEdit={onEdit}
          onDelete={onDelete}
          onStart={onStart}
          onComplete={onComplete}
          onFail={onFail}
          onRetry={onRetry}
          busy={busyTaskId === task.id}
        />
      ))}
    </div>
  );
}

function TaskDialog({ form, mode, saving, error, onChange, onSave, onCancel }) {
  return (
    <div className="dev-dialog-backdrop" role="presentation">
      <form className="dev-task-dialog" onSubmit={onSave}>
        <header>
          <h2>{mode === "edit" ? "Edit Task" : "New Task"}</h2>
          <button type="button" onClick={onCancel}>Cancel</button>
        </header>
        {error ? <div className="action-result failure">{error}</div> : null}
        <label>
          <span>Project</span>
          <input value={form.project} onChange={(event) => onChange("project", event.target.value)} />
        </label>
        <label>
          <span>Workspace</span>
          <input value={form.workspace} onChange={(event) => onChange("workspace", event.target.value)} />
        </label>
        <label>
          <span>Title</span>
          <input required value={form.title} onChange={(event) => onChange("title", event.target.value)} />
        </label>
        <label>
          <span>Goal</span>
          <textarea required rows="4" value={form.goal} onChange={(event) => onChange("goal", event.target.value)} />
        </label>
        <label>
          <span>Constraints</span>
          <textarea rows="4" value={form.constraints} onChange={(event) => onChange("constraints", event.target.value)} placeholder="One constraint per line" />
        </label>
        <div className="dev-policy-warning">Remote tasks should avoid interactive approvals. Use Safe Edit for phone-launched work.</div>
        <label>
          <span>Execution Mode</span>
          <select value={form.execution_mode} onChange={(event) => onChange("execution_mode", event.target.value)}>
            <option value="read_only">Read Only</option>
            <option value="safe_edit">Safe Edit</option>
            <option value="full_agent">Full Agent</option>
          </select>
        </label>
        <label>
          <span>Allowed Paths</span>
          <textarea rows="3" value={form.allowed_paths} onChange={(event) => onChange("allowed_paths", event.target.value)} placeholder="One path per line" />
        </label>
        <label>
          <span>Validation Commands</span>
          <textarea rows="3" value={form.validation_commands} onChange={(event) => onChange("validation_commands", event.target.value)} placeholder="One command per line" />
        </label>
        <label className="dev-checkbox-label">
          <input type="checkbox" checked={form.requires_manual_approval} onChange={(event) => onChange("requires_manual_approval", event.target.checked)} />
          <span>Requires Manual Approval</span>
        </label>
        <label>
          <span>Priority</span>
          <select value={form.priority} onChange={(event) => onChange("priority", event.target.value)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <div className="panel-actions">
          <button disabled={saving} type="submit">{saving ? "Saving..." : "Save"}</button>
          <button disabled={saving} type="button" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  );
}

function TaskDetailPanel({ task, onEdit, onDelete, onRetry, busy }) {
  if (!task) {
    return <p className="answer">Select a task to review its goal, constraints, history, and result summary.</p>;
  }

  return (
    <div className="dev-task-detail">
      <div className="dev-task-card-header">
        <div>
          <strong>{task.title}</strong>
          <span>{task.project} / {task.workspace}</span>
        </div>
        <StatusBadge tone={priorityTone(task.priority)}>{task.priority}</StatusBadge>
      </div>
      <section>
        <h3>Goal</h3>
        <p>{task.goal}</p>
      </section>
      <section>
        <h3>Constraints</h3>
        {policyList(task.constraints, "No constraints recorded.")}
      </section>
      <section>
        <h3>Execution Policy</h3>
        <div className="dev-policy-grid">
          <div>
            <span>Mode</span>
            <strong>{executionModeLabels[task.execution_mode] || executionModeLabels.safe_edit}</strong>
          </div>
          <div>
            <span>Manual Approval</span>
            <strong>{task.requires_manual_approval ? "Required" : "Not required"}</strong>
          </div>
        </div>
        <h4>Allowed Paths</h4>
        {policyList(task.allowed_paths, "No path restrictions recorded.")}
        <h4>Validation Commands</h4>
        {policyList(task.validation_commands, "No validation commands recorded.")}
      </section>
      <section>
        <h3>History</h3>
        <div className="dev-history-list">
          {taskHistory(task).map((entry) => (
            <div key={`${entry.label}-${entry.value}`}>
              <span>{entry.label}</span>
              <strong>{entry.label === "Current Status" ? entry.value : formatDate(entry.value)}</strong>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3>Result Summary</h3>
        <p>{task.result_summary || "No result summary yet."}</p>
      </section>
      <div className="dev-task-actions">
        {task.status === "Failed" ? <button disabled={busy} type="button" onClick={() => onRetry(task)}>{busy ? "Retrying..." : "Retry"}</button> : null}
        <button type="button" onClick={() => onEdit(task)}>Edit</button>
        <button type="button" onClick={() => onDelete(task)}>Delete</button>
      </div>
    </div>
  );
}

function TaskLogViewer({ task, logs, loading, error }) {
  const logRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, task?.id]);

  if (!task) {
    return <p className="answer">Select a task to view its execution log.</p>;
  }

  if (loading) {
    return <p className="answer">Loading task log...</p>;
  }

  if (error) {
    return <div className="action-result failure">Task log error: {error}</div>;
  }

  return <pre className="dev-task-log" ref={logRef}>{logs || "No log entries yet."}</pre>;
}

export default function DevelopmentPage() {
  const [status, setStatus] = useState(null);
  const [workersStatus, setWorkersStatus] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [workersLoading, setWorkersLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [error, setError] = useState("");
  const [workerError, setWorkerError] = useState("");
  const [taskError, setTaskError] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [taskLogs, setTaskLogs] = useState("");
  const [taskEvents, setTaskEvents] = useState([]);
  const [taskLogError, setTaskLogError] = useState("");
  const [taskEventError, setTaskEventError] = useState("");
  const [taskLogsLoading, setTaskLogsLoading] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState("");
  const [commandBusyTaskId, setCommandBusyTaskId] = useState("");
  const [phaseBusyTaskId, setPhaseBusyTaskId] = useState("");
  const [workerMessage, setWorkerMessage] = useState(null);
  const [dialogMode, setDialogMode] = useState(null);
  const [editingTaskId, setEditingTaskId] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDevelopmentStatus();
      setStatus(data);
      setError("");
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const data = await getTasks();
      setTasks(Array.isArray(data) ? data : []);
      setTaskError("");
    } catch (err) {
      setTaskError(err.message);
    } finally {
      setTasksLoading(false);
    }
  }, []);

  const loadWorkers = useCallback(async () => {
    setWorkersLoading(true);
    try {
      const data = await getWorkersStatus();
      setWorkersStatus(data);
      setWorkerError("");
    } catch (err) {
      setWorkerError(err.message);
    } finally {
      setWorkersLoading(false);
    }
  }, []);

  const loadTaskLogs = useCallback(async (taskId) => {
    if (!taskId) {
      setTaskLogs("");
      setTaskLogError("");
      return;
    }

    setTaskLogsLoading(true);
    try {
      const logs = await getTaskLogs(taskId);
      setTaskLogs(logs || "");
      setTaskLogError("");
    } catch (err) {
      setTaskLogs("");
      setTaskLogError(err.response?.data?.detail || err.message);
    } finally {
      setTaskLogsLoading(false);
    }
  }, []);

  const loadTaskEvents = useCallback(async (taskId) => {
    if (!taskId) {
      setTaskEvents([]);
      setTaskEventError("");
      return;
    }

    try {
      const events = await getTaskEvents(taskId);
      setTaskEvents(Array.isArray(events) ? events : []);
      setTaskEventError("");
    } catch (err) {
      setTaskEvents([]);
      setTaskEventError(err.response?.data?.detail || err.message);
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([loadStatus(), loadWorkers(), loadTasks()]);
  }, [loadStatus, loadWorkers, loadTasks]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const codeServerRunning = Boolean(status?.code_server?.running);
  const workerStatus = workersStatus?.development_worker || null;
  const gitStatus = status?.git?.status || "unknown";
  const codeServerUrl = status?.code_server_url || "http://192.168.50.10:8443";
  const taskCounts = {
    Queued: tasks.filter((task) => task.status === "Queued").length,
    Running: tasks.filter((task) => task.status === "Running" || activeStages.has(currentStage(task))).length,
    Review: tasks.filter((task) => task.status === "Review").length,
    Completed: tasks.filter((task) => task.status === "Completed").length,
    Failed: tasks.filter((task) => task.status === "Failed").length,
  };
  const queuedTasks = tasks.filter((task) => task.status === "Queued" || task.status === "Review");
  const runningTask = tasks.find((task) => task.status === "Running" || activeStages.has(currentStage(task)));
  const reviewTask = tasks.find((task) => task.status === "Review");
  const completedTasks = tasks.filter((task) => task.status === "Completed" || task.status === "Failed");
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) || runningTask || queuedTasks[0] || completedTasks[0] || null;
  const logTask = runningTask || selectedTask;
  const missionTask = runningTask || reviewTask || selectedTask;

  useEffect(() => {
    loadTaskLogs(logTask?.id || "");
    loadTaskEvents(logTask?.id || "");
  }, [loadTaskEvents, loadTaskLogs, logTask?.id]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      refresh();
      if (logTask?.id) {
        loadTaskLogs(logTask.id);
        loadTaskEvents(logTask.id);
      }
    }, 10000);
    return () => window.clearInterval(intervalId);
  }, [loadTaskEvents, loadTaskLogs, logTask?.id, refresh]);

  const openNewTask = () => {
    setForm(emptyForm);
    setEditingTaskId("");
    setDialogError("");
    setDialogMode("new");
  };

  const openEditTask = (task) => {
    setForm({
      project: task.project || "Command Center",
      workspace: task.workspace || "Development",
      title: task.title || "",
      goal: task.goal || "",
      constraints: (task.constraints || []).join("\n"),
      execution_mode: task.execution_mode || "safe_edit",
      allowed_paths: (task.allowed_paths || []).join("\n"),
      validation_commands: (task.validation_commands || [
        "python3 -m py_compile backend/app.py",
        "cd frontend-react && npm run build",
      ]).join("\n"),
      requires_manual_approval: Boolean(task.requires_manual_approval),
      priority: task.priority || "medium",
    });
    setSelectedTaskId(task.id);
    setEditingTaskId(task.id);
    setDialogError("");
    setDialogMode("edit");
  };

  const closeDialog = () => {
    setDialogMode(null);
    setEditingTaskId("");
    setDialogError("");
    setForm(emptyForm);
  };

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveTask = async (event) => {
    event.preventDefault();
    setSaving(true);
    setDialogError("");

    const payload = {
      project: form.project,
      workspace: form.workspace,
      title: form.title,
      goal: form.goal,
      constraints: form.constraints.split("\n").map((item) => item.trim()).filter(Boolean),
      execution_mode: form.execution_mode,
      allowed_paths: form.allowed_paths.split("\n").map((item) => item.trim()).filter(Boolean),
      validation_commands: form.validation_commands.split("\n").map((item) => item.trim()).filter(Boolean),
      requires_manual_approval: form.requires_manual_approval,
      priority: form.priority,
    };

    try {
      const savedTask = dialogMode === "edit" ? await updateTask(editingTaskId, payload) : await createTask(payload);
      setSelectedTaskId(savedTask.id);
      closeDialog();
      await loadTasks();
      await loadTaskLogs(savedTask.id);
    } catch (err) {
      setDialogError(err.response?.data?.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  const removeTask = async (task) => {
    if (!window.confirm(`Delete task "${task.title}"?`)) return;
    try {
      await deleteTask(task.id);
      if (selectedTaskId === task.id) setSelectedTaskId("");
      await loadTasks();
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
    }
  };

  const refreshTaskState = async (taskId) => {
    await loadTasks();
    await loadTaskLogs(taskId);
    await loadTaskEvents(taskId);
  };

  const beginTask = async (task) => {
    setBusyTaskId(task.id);
    setTaskError("");
    try {
      await startTask(task.id);
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
    } finally {
      setBusyTaskId("");
    }
  };

  const finishTask = async (task, action) => {
    const fallback = action === "complete" ? "Completed manually." : "Failed manually.";
    const resultSummary = window.prompt("Result summary", task.result_summary || fallback);
    if (resultSummary === null) return;

    setBusyTaskId(task.id);
    setTaskError("");
    try {
      if (action === "complete") {
        await completeTask(task.id, resultSummary);
      } else {
        await failTask(task.id, resultSummary);
      }
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
    } finally {
      setBusyTaskId("");
    }
  };

  const retryFailedTask = async (task) => {
    setBusyTaskId(task.id);
    setTaskError("");
    try {
      await retryTask(task.id);
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
    } finally {
      setBusyTaskId("");
    }
  };

  const advanceManualStage = async (task, nextStage) => {
    setBusyTaskId(task.id);
    setTaskError("");
    try {
      await setTaskExecutionStage(task.id, nextStage);
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
    } finally {
      setBusyTaskId("");
    }
  };

  const runWorkerAction = async (task, action) => {
    setCommandBusyTaskId(task.id);
    setTaskError("");
    setWorkerMessage(null);
    try {
      if (action === "validation") {
        await runTaskValidation(task.id);
        setWorkerMessage({ tone: "success", text: "Validation finished. Worker events refreshed." });
      } else if (action === "rebuild") {
        await runTaskRebuild(task.id);
        setWorkerMessage({ tone: "success", text: "Rebuild finished. Worker events refreshed." });
      } else if (action === "diff") {
        await runTaskCommand(task.id, "git_diff_stat");
        setWorkerMessage({ tone: "success", text: "Diff stat finished. Worker events refreshed." });
      }
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      const message = err.response?.data?.detail || err.message;
      setTaskError(message);
      setWorkerMessage({ tone: "failure", text: message });
      await loadTaskEvents(task.id);
    } finally {
      setCommandBusyTaskId("");
    }
  };

  const updateTaskPhase = async (task, phaseName, action) => {
    setPhaseBusyTaskId(task.id);
    setTaskError("");
    try {
      if (action === "start") {
        await startTaskPhase(task.id, phaseName);
      } else if (action === "complete") {
        const summary = window.prompt("Phase summary", "") || "";
        await completeTaskPhase(task.id, phaseName, summary);
      } else if (action === "fail") {
        const summary = window.prompt("Failure summary", "") || "";
        await failTaskPhase(task.id, phaseName, summary);
      } else if (action === "initialize") {
        await initializeTaskPhases(task.id);
      }
      setSelectedTaskId(task.id);
      await refreshTaskState(task.id);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message);
      await loadTaskEvents(task.id);
    } finally {
      setPhaseBusyTaskId("");
    }
  };

  const refreshWorkerEvents = async (task) => {
    setCommandBusyTaskId(task.id);
    setWorkerMessage(null);
    try {
      await loadTasks();
      await loadTaskEvents(task.id);
      setSelectedTaskId(task.id);
      setWorkerMessage({ tone: "success", text: "Worker events refreshed." });
    } catch (err) {
      const message = err.response?.data?.detail || err.message;
      setWorkerMessage({ tone: "failure", text: message });
    } finally {
      setCommandBusyTaskId("");
    }
  };

  return (
    <div className="page-content development-page">
      <header className="page-header">
        <div>
          <h1>Development Workspace</h1>
          <p className="page-subtitle">Structured engineering tasks, repository health, build readiness, and future Codex orchestration.</p>
        </div>
        <div className="dev-header-actions">
          <div>
            <div className="label">Last Updated</div>
            <strong>{lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Not loaded"}</strong>
          </div>
          <button disabled={loading || workersLoading || tasksLoading} onClick={refresh}>{loading || workersLoading || tasksLoading ? "Refreshing..." : "Refresh Now"}</button>
          <button type="button" onClick={openNewTask}>New Task</button>
        </div>
      </header>

      {error ? <div className="action-result failure">Development status error: {error}</div> : null}
      {workerError ? <div className="action-result failure">Worker Manager error: {workerError}</div> : null}
      {taskError ? <div className="action-result failure">Task error: {taskError}</div> : null}

      <TaskCountSummary counts={taskCounts} />

      <section className="dev-overview-grid">
        <div className="card dev-overview-card">
          <div className="label">Code Server</div>
          <strong>{codeServerRunning ? "Running" : status?.code_server?.exists ? "Stopped" : "Missing"}</strong>
          <StatusBadge active={codeServerRunning}>{status?.code_server?.state || "unknown"}</StatusBadge>
        </div>
        <div className="card dev-overview-card">
          <div className="label">Repository</div>
          <strong>{status?.repository_path || "/opt/command-center"}</strong>
          <StatusBadge active={gitStatus === "clean"}>{gitStatus}</StatusBadge>
        </div>
        <div className="card dev-overview-card">
          <div className="label">Task Queue</div>
          <strong>{queuedTasks.length} queued</strong>
          <StatusBadge active={Boolean(runningTask)}>{runningTask ? "Running" : "Idle"}</StatusBadge>
        </div>
      </section>

      <section className="workspace-grid">
        <div className="workspace-column">
          <Panel title="Workspace Overview">
            <div className="dev-kv-list">
              <div>
                <span>Repository Path</span>
                <strong>{status?.repository_path || "/opt/command-center"}</strong>
              </div>
              <div>
                <span>Code Server Container</span>
                <strong>{status?.code_server?.name || "code-server"}</strong>
              </div>
              <div>
                <span>Docker Access</span>
                <StatusBadge active={Boolean(status?.docker_available)}>{status?.docker_available ? "Available" : "Unavailable"}</StatusBadge>
              </div>
            </div>
            <div className="panel-actions">
              <a className="button-link" href={codeServerUrl} target="_blank" rel="noreferrer">Open Code Server</a>
            </div>
          </Panel>

          <Panel title="Tool Health">
            <ToolHealth status={status} />
          </Panel>

          <Panel title="Git Status">
            <div className="dev-kv-list">
              <div>
                <span>Branch</span>
                <strong>{status?.git?.branch || "unknown"}</strong>
              </div>
              <div>
                <span>Working Tree</span>
                <StatusBadge active={gitStatus === "clean"}>{gitStatus}</StatusBadge>
              </div>
            </div>
            <RecentCommits commits={status?.git?.recent_commits} />
          </Panel>

          <Panel title="Manual execution mode">
            <p className="answer">Codex task execution is not enabled yet.</p>
            <div className="dev-runner-row">
              <div>
                <span>Status</span>
                <StatusBadge active={false}>Queued</StatusBadge>
              </div>
              <div>
                <span>Future placeholder</span>
                <button disabled type="button">Run with Codex</button>
              </div>
              <div>
                <span>Review</span>
                <StatusBadge active={false}>Pending</StatusBadge>
              </div>
            </div>
          </Panel>
        </div>

        <div className="workspace-column">
          <Panel title="Worker Manager">
            <WorkerManager worker={workerStatus} loading={workersLoading} error={workerError} />
          </Panel>

          <Panel title="Mission Control">
            <MissionControl
              task={missionTask}
              events={taskEvents}
              eventError={taskEventError}
              busy={busyTaskId === missionTask?.id}
              commandBusy={commandBusyTaskId === missionTask?.id}
              phaseBusy={phaseBusyTaskId === missionTask?.id}
              workerStatus={workerStatus}
              workerMessage={workerMessage}
              lastUpdated={lastUpdated}
              onViewLog={(task) => setSelectedTaskId(task.id)}
              onComplete={(task) => finishTask(task, "complete")}
              onFail={(task) => finishTask(task, "fail")}
              onNextStage={advanceManualStage}
              onRunValidation={(task) => runWorkerAction(task, "validation")}
              onRunRebuild={(task) => runWorkerAction(task, "rebuild")}
              onRunDiffStat={(task) => runWorkerAction(task, "diff")}
              onRefreshEvents={refreshWorkerEvents}
              onPhaseAction={updateTaskPhase}
            />
          </Panel>

          <Panel title="Queued Tasks">
            <TaskList
              tasks={queuedTasks}
              emptyText="No queued tasks yet. Create a task to add it to the queue."
              onView={(task) => setSelectedTaskId(task.id)}
              onEdit={openEditTask}
              onDelete={removeTask}
              onStart={beginTask}
              onComplete={(task) => finishTask(task, "complete")}
              onFail={(task) => finishTask(task, "fail")}
              onRetry={retryFailedTask}
              busyTaskId={busyTaskId}
            />
          </Panel>

          <Panel title="Completed Tasks">
            <TaskList
              tasks={completedTasks}
              emptyText="No completed or failed tasks yet."
              onView={(task) => setSelectedTaskId(task.id)}
              onEdit={openEditTask}
              onDelete={removeTask}
              onStart={beginTask}
              onComplete={(task) => finishTask(task, "complete")}
              onFail={(task) => finishTask(task, "fail")}
              onRetry={retryFailedTask}
              busyTaskId={busyTaskId}
            />
          </Panel>

          <Panel title="Task Detail">
            <TaskDetailPanel task={selectedTask} onEdit={openEditTask} onDelete={removeTask} onRetry={retryFailedTask} busy={busyTaskId === selectedTask?.id} />
          </Panel>

          <Panel title="Task Log Viewer">
            <TaskLogViewer task={logTask} logs={taskLogs} loading={taskLogsLoading} error={taskLogError} />
          </Panel>
        </div>
      </section>

      {dialogMode ? (
        <TaskDialog
          form={form}
          mode={dialogMode}
          saving={saving}
          error={dialogError}
          onChange={updateForm}
          onSave={saveTask}
          onCancel={closeDialog}
        />
      ) : null}
    </div>
  );
}
