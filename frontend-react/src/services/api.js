import axios from "axios";

axios.defaults.withCredentials = true;

let csrfToken = "";

export async function login(username, password) {
  const res = await axios.post("/api/auth/login", { username, password });
  csrfToken = res.data.csrf_token;
  return res.data;
}

export async function getCurrentUser() {
  const res = await axios.get("/api/auth/me");
  csrfToken = res.data.csrf_token;
  return res.data.user;
}

export async function logout() {
  await axios.post("/api/auth/logout", null, {
    headers: { "X-CSRF-Token": csrfToken },
  });
  csrfToken = "";
}

export function csrfHeaders() {
  return { "X-CSRF-Token": csrfToken };
}

export async function getVeraControl() {
  const res = await axios.get("/api/vera/control");
  return res.data.control;
}

export async function changeVeraControl(action, reason, expectedVersion) {
  const res = await axios.post(
    `/api/vera/control/${action}`,
    { reason, expected_version: expectedVersion },
    { headers: csrfHeaders() },
  );
  return res.data.control;
}

export async function getCloudRouting() {
  const res = await axios.get("/api/vera/router/cloud");
  return res.data.cloud_routing;
}

export async function changeCloudRouting(enabled, reason, expectedVersion) {
  const action = enabled ? "enable" : "disable";
  const res = await axios.post(
    `/api/vera/router/cloud/${action}`,
    { reason, expected_version: expectedVersion },
    { headers: csrfHeaders() },
  );
  return res.data.cloud_routing;
}

export async function getVeraPermissions() {
  const res = await axios.get("/api/vera/permissions");
  return res.data.permissions;
}

export async function updateVeraPermission(domain, capability, effect) {
  const res = await axios.put(
    "/api/vera/permissions",
    { domain, capability, effect },
    { headers: csrfHeaders() },
  );
  return res.data.permission;
}

export async function getVeraAudit(limit = 100) {
  const res = await axios.get(`/api/vera/audit?limit=${encodeURIComponent(limit)}`);
  return res.data.events;
}

export async function getDecisionJournal(limit = 10, offset = 0) {
  const res = await axios.get(
    `/api/vera/journal?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
  );
  return res.data;
}

export async function getStatus() {
  const res = await axios.get("/api/status");
  return res.data;
}

export async function getHomeAssistantOverview() {
  const res = await axios.get("/api/home-assistant/overview");
  return res.data;
}

export async function getAnalysis() {
  const res = await axios.post("/api/analyze", null, { headers: csrfHeaders() });
  return res.data.analysis;
}

export async function getBriefing() {
  const res = await axios.post("/api/briefing", null, { headers: csrfHeaders() });
  return res.data.briefing;
}

export async function getMinecraftStatus() {
  const res = await axios.get("/api/minecraft/status");
  return res.data;
}

export async function minecraftStart() {
  const res = await axios.post("/api/minecraft/start");
  return res.data;
}

export async function minecraftStop() {
  const res = await axios.post("/api/minecraft/stop");
  return res.data;
}

export async function minecraftRestart() {
  const res = await axios.post("/api/minecraft/restart");
  return res.data;
}

export async function minecraftSave() {
  const res = await axios.post("/api/minecraft/save");
  return res.data;
}

export async function minecraftOp(player) {
  const res = await axios.post(`/api/minecraft/op?player=${encodeURIComponent(player)}`);
  return res.data;
}

export async function minecraftDeop(player) {
  const res = await axios.post(`/api/minecraft/deop?player=${encodeURIComponent(player)}`);
  return res.data;
}

export async function minecraftKick(player) {
  const res = await axios.post(`/api/minecraft/kick?player=${encodeURIComponent(player)}`);
  return res.data;
}

export async function minecraftBan(player) {
  const res = await axios.post(`/api/minecraft/ban?player=${encodeURIComponent(player)}`);
  return res.data;
}

export async function minecraftSay(message) {
  const res = await axios.post(`/api/minecraft/say?message=${encodeURIComponent(message)}`);
  return res.data;
}

export async function getMinecraftLogs(tail = 120) {
  const res = await axios.get(`/api/minecraft/logs?tail=${encodeURIComponent(tail)}`);
  return res.data;
}

export async function getAdvisorRecommendations() {
  const res = await axios.get("/api/advisor/recommendations");
  return res.data.recommendations;
}

export async function sendMinecraftCommand(command) {
  const res = await axios.post(`/api/minecraft/command`, { command });
  return res.data;
}

export async function getPlexStatus() {
  const res = await axios.get("/api/plex/status");
  return res.data;
}

export async function getPlexLogs(tail = 160) {
  const res = await axios.get(`/api/plex/logs?tail=${encodeURIComponent(tail)}`);
  return res.data;
}

export async function plexStart() {
  const res = await axios.post("/api/plex/start");
  return res.data;
}

export async function plexStop() {
  const res = await axios.post("/api/plex/stop");
  return res.data;
}

export async function plexRestart() {
  const res = await axios.post("/api/plex/restart");
  return res.data;
}

export async function getSecurityStatus() {
  const res = await axios.get("/api/security/status");
  return res.data;
}

export async function getDevelopmentStatus() {
  const res = await axios.get("/api/development/status");
  return res.data;
}

export async function getWorkersStatus() {
  const res = await axios.get("/api/workers/status");
  return res.data;
}

export async function getTasks() {
  const res = await axios.get("/api/tasks");
  return res.data.tasks;
}

export async function getTask(id) {
  const res = await axios.get(`/api/tasks/${encodeURIComponent(id)}`);
  return res.data;
}

export async function createTask(task) {
  const res = await axios.post("/api/tasks", task);
  return res.data;
}

export async function updateTask(id, task) {
  const res = await axios.patch(`/api/tasks/${encodeURIComponent(id)}`, task);
  return res.data;
}

export async function startTask(id) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/start`);
  return res.data;
}

export async function completeTask(id, resultSummary) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/complete`, { result_summary: resultSummary });
  return res.data;
}

export async function failTask(id, resultSummary) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/fail`, { result_summary: resultSummary });
  return res.data;
}

export async function retryTask(id) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/retry`);
  return res.data;
}

export async function setTaskExecutionStage(id, executionStage) {
  const res = await axios.patch(`/api/tasks/${encodeURIComponent(id)}/stage`, { execution_stage: executionStage });
  return res.data;
}

export async function appendTaskLog(id, message) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/log`, { message });
  return res.data;
}

export async function getTaskEvents(id) {
  const res = await axios.get(`/api/tasks/${encodeURIComponent(id)}/events`);
  return res.data.events;
}

export async function runTaskCommand(id, commandKey) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/run-command`, { command_key: commandKey }, { headers: csrfHeaders() });
  return res.data;
}

export async function runTaskValidation(id) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/run-validation`, null, { headers: csrfHeaders() });
  return res.data;
}

export async function runTaskRebuild(id) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/run-rebuild`, null, { headers: csrfHeaders() });
  return res.data;
}

export async function initializeTaskPhases(id) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/phases/initialize`);
  return res.data;
}

export async function startTaskPhase(id, phaseName) {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/phases/${encodeURIComponent(phaseName)}/start`);
  return res.data;
}

export async function completeTaskPhase(id, phaseName, summary = "") {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/phases/${encodeURIComponent(phaseName)}/complete`, { summary });
  return res.data;
}

export async function failTaskPhase(id, phaseName, summary = "") {
  const res = await axios.post(`/api/tasks/${encodeURIComponent(id)}/phases/${encodeURIComponent(phaseName)}/fail`, { summary });
  return res.data;
}

export async function getTaskLogs(id) {
  const res = await axios.get(`/api/tasks/${encodeURIComponent(id)}/logs`);
  return res.data.logs;
}

export async function deleteTask(id) {
  const res = await axios.delete(`/api/tasks/${encodeURIComponent(id)}`);
  return res.data;
}
