import { describe, expect, it, vi } from "vitest";
import { handleVerifiedEnvelope } from "../src/index";

const baseEnv = {
  ALEXA_SKILL_ID: "skill-1",
  COMMAND_CENTER_URL: "https://origin.example/api/alexa/relay",
  RELAY_SECRET: "s".repeat(64),
} as Env;

describe("Vera Alexa relay", () => {
  it("handles launch without contacting the origin", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const response = await handleVerifiedEnvelope({
      session: { application: { applicationId: "skill-1" } },
      request: { type: "LaunchRequest" },
    }, baseEnv);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ response: { shouldEndSession: false } });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects a different skill id", async () => {
    const response = await handleVerifiedEnvelope({
      session: { application: { applicationId: "other" } },
      request: { type: "LaunchRequest" },
    }, baseEnv);
    expect(response.status).toBe(400);
  });

  it("uses recognized person identity before account identity", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ text: "Hello Bruce" }), { status: 200 }));
    const response = await handleVerifiedEnvelope({
      session: { sessionId: "session-1", application: { applicationId: "skill-1" }, user: { userId: "account-1" } },
      context: { System: { person: { personId: "person-1" } } },
      request: { type: "IntentRequest", requestId: "request-1", intent: { name: "AskVeraIntent", slots: { query: { value: "hello" } } } },
    }, baseEnv);
    expect(response.status).toBe(200);
    const call = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({ subject_id: "person:person-1", text: "hello" });
  });
});
