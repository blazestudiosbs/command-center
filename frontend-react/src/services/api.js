import axios from "axios";

export async function getStatus() {
  const res = await axios.get("/api/status");
  return res.data;
}

export async function getAnalysis() {
  const res = await axios.post("/api/analyze");
  return res.data.analysis;
}

export async function getBriefing() {
  const res = await axios.post("/api/briefing");
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

export async function minecraftSay(message) {
  const res = await axios.post(`/api/minecraft/say?message=${encodeURIComponent(message)}`);
  return res.data;
}

export async function getMinecraftLogs(tail = 120) {
  const res = await axios.get(`/api/minecraft/logs?tail=${encodeURIComponent(tail)}`);
  return res.data;
}

export async function sendMinecraftCommand(command) {
  const res = await axios.post(`/api/minecraft/command`, { command });
  return res.data;
}
