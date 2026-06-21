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
