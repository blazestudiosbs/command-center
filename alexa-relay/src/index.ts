import { createVerify, X509Certificate } from "node:crypto";
import { TimestampVerifier } from "ask-sdk-express-adapter";

type AlexaEnvelope = {
  session?: {
    sessionId?: string;
    application?: { applicationId?: string };
    user?: { userId?: string };
  };
  context?: {
    System?: {
      application?: { applicationId?: string };
      user?: { userId?: string };
      person?: { personId?: string };
    };
  };
  request?: {
    type?: string;
    requestId?: string;
    intent?: { name?: string; slots?: Record<string, { value?: string }> };
  };
};

type RelayPayload = {
  provider: "amazon_alexa";
  subject_id: string;
  session_id: string;
  request_id: string;
  text: string;
};

const encoder = new TextEncoder();
const ALEXA_CERT_HOST = "s3.amazonaws.com";
const ALEXA_CERT_PATH_PREFIX = "/echo.api/";
const ALEXA_CERT_NAME = "echo-api.amazon.com";
const AMAZON_ROOT_CA_1_SHA256 = "87:DC:D4:DC:74:64:0A:32:2C:D2:05:55:25:06:D1:BE:64:F1:25:96:25:80:96:54:49:86:B4:85:0B:C7:27:06";
const certificateCache = new Map<string, X509Certificate[]>();

function headerValue(headers: Headers, name: string): string {
  return headers.get(name)?.trim() ?? "";
}

async function alexaCertificates(rawUrl: string): Promise<X509Certificate[]> {
  const cached = certificateCache.get(rawUrl);
  if (cached) return cached;
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" || url.hostname !== ALEXA_CERT_HOST || (url.port && url.port !== "443") || !url.pathname.startsWith(ALEXA_CERT_PATH_PREFIX)) {
    throw new Error("invalid_certificate_url");
  }
  const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(3000) });
  if (!response.ok) throw new Error("certificate_fetch_failed");
  const pem = await response.text();
  if (pem.length > 32 * 1024) throw new Error("certificate_chain_too_large");
  const blocks = pem.match(/-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----/g) ?? [];
  if (blocks.length < 2 || blocks.length > 5) throw new Error("invalid_certificate_chain");
  const certificates = blocks.map((block) => new X509Certificate(block));
  const now = Date.now();
  for (const certificate of certificates) {
    if (now < Date.parse(certificate.validFrom) || now > Date.parse(certificate.validTo)) throw new Error("certificate_expired");
  }
  if (!certificates[0].checkHost(ALEXA_CERT_NAME)) throw new Error("invalid_certificate_name");
  for (let index = 0; index < certificates.length - 1; index += 1) {
    if (!certificates[index].verify(certificates[index + 1].publicKey)) throw new Error("invalid_certificate_chain");
  }
  const trustAnchor = certificates[certificates.length - 1];
  if (trustAnchor.fingerprint256 !== AMAZON_ROOT_CA_1_SHA256) throw new Error("untrusted_certificate_root");
  certificateCache.set(rawUrl, certificates);
  return certificates;
}

async function verifyAlexaSignature(body: string, headers: Headers): Promise<void> {
  const certUrl = headerValue(headers, "SignatureCertChainUrl");
  const signature = headerValue(headers, "Signature-256");
  if (!certUrl || !signature) throw new Error("missing_signature_headers");
  const certificates = await alexaCertificates(certUrl);
  const verifier = createVerify("RSA-SHA256");
  verifier.update(body, "utf8");
  verifier.end();
  if (!verifier.verify(certificates[0].publicKey, signature, "base64")) throw new Error("invalid_request_signature");
}

function alexaResponse(text: string, shouldEndSession: boolean, reprompt?: string): Response {
  return Response.json({
    version: "1.0",
    response: {
      outputSpeech: { type: "PlainText", text },
      ...(reprompt ? { reprompt: { outputSpeech: { type: "PlainText", text: reprompt } } } : {}),
      shouldEndSession,
    },
  });
}

function applicationId(envelope: AlexaEnvelope): string {
  return envelope.context?.System?.application?.applicationId ?? envelope.session?.application?.applicationId ?? "";
}

function subjectId(envelope: AlexaEnvelope): string {
  const person = envelope.context?.System?.person?.personId;
  if (person) return `person:${person}`;
  const user = envelope.context?.System?.user?.userId ?? envelope.session?.user?.userId;
  return user ? `user:${user}` : "";
}

function queryText(envelope: AlexaEnvelope): string {
  const slots = envelope.request?.intent?.slots ?? {};
  return slots.query?.value?.trim() ?? "";
}

async function hmacSignature(timestamp: string, body: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(`${timestamp}.${body}`));
  return `sha256=${Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

async function forwardToVera(payload: RelayPayload, env: Env): Promise<{ text: string }> {
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signature = await hmacSignature(timestamp, body, env.RELAY_SECRET);
  const response = await fetch(env.COMMAND_CENTER_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Vera-Timestamp": timestamp,
      "X-Vera-Signature": signature,
    },
    body,
    signal: AbortSignal.timeout(6500),
  });
  const declaredLength = Number(response.headers.get("Content-Length") ?? "0");
  if (declaredLength > 16_384) throw new Error("oversized_origin_response");
  const text = await response.text();
  if (text.length > 16_384) throw new Error("oversized_origin_response");
  if (response.status === 403) throw new Error("unlinked_voice_identity");
  if (!response.ok) throw new Error(`origin_${response.status}`);
  const parsed = JSON.parse(text) as { text?: unknown };
  if (typeof parsed.text !== "string" || !parsed.text.trim()) throw new Error("invalid_origin_response");
  return { text: parsed.text };
}

export async function handleVerifiedEnvelope(envelope: AlexaEnvelope, env: Env): Promise<Response> {
  if (applicationId(envelope) !== env.ALEXA_SKILL_ID) return new Response("Invalid skill", { status: 400 });
  const requestType = envelope.request?.type;
  if (requestType === "LaunchRequest") {
    return alexaResponse("Vera is ready. What would you like?", false, "What would you like to ask Vera?");
  }
  if (requestType === "SessionEndedRequest") return new Response(null, { status: 200 });
  const intentName = envelope.request?.intent?.name;
  if (intentName === "AMAZON.StopIntent" || intentName === "AMAZON.CancelIntent") {
    return alexaResponse("Okay.", true);
  }
  if (intentName === "AMAZON.HelpIntent") {
    return alexaResponse("Ask me anything by saying, ask Vera, followed by your question.", false, "What would you like to ask Vera?");
  }
  if (requestType !== "IntentRequest" || intentName !== "AskVeraIntent") {
    return alexaResponse("I didn't understand that. Try saying, ask Vera, followed by your question.", false);
  }
  const text = queryText(envelope);
  const subject = subjectId(envelope);
  const sessionId = envelope.session?.sessionId ?? "";
  const requestId = envelope.request?.requestId ?? "";
  if (!text || !subject || !sessionId || !requestId) return alexaResponse("I couldn't identify that request safely.", true);
  try {
    const result = await forwardToVera({ provider: "amazon_alexa", subject_id: subject, session_id: sessionId, request_id: requestId, text }, env);
    console.log(JSON.stringify({ event: "alexa_request", outcome: "succeeded", request_id: requestId }));
    return alexaResponse(result.text, true);
  } catch (error) {
    const code = error instanceof Error ? error.message : "unknown";
    console.error(JSON.stringify({ event: "alexa_request", outcome: "failed", request_id: requestId, code }));
    if (code === "unlinked_voice_identity") return alexaResponse("This voice profile is not linked to your Vera household yet.", true);
    return alexaResponse("Vera isn't available quickly enough right now. Please try again.", true);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") return Response.json({ status: "ok" });
    if (request.method === "GET" && url.pathname === "/privacy") {
      return new Response("Vera Family Assistant Privacy Policy\n\nVoice requests are used only to provide the requested private household-assistant response. Voice audio is processed by Amazon Alexa. Vera receives the resulting text and a one-way hashed household identity. Request text and responses are retained in the household member's private Command Center conversation history and audit trail. Data is not sold or used for advertising.", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }
    if (request.method === "GET" && url.pathname === "/terms") {
      return new Response("Vera Family Assistant Terms of Use\n\nThis is a private household skill. Use is limited to authorized household members. Device and communication actions remain subject to Vera's permissions, confirmation requirements, audit logging, and emergency stop. Availability is not guaranteed.", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }
    if (url.pathname !== "/alexa" || request.method !== "POST") return new Response("Not found", { status: 404 });
    const body = await request.text();
    if (body.length > 64 * 1024) return new Response("Request too large", { status: 413 });
    try {
      await verifyAlexaSignature(body, request.headers);
      await new TimestampVerifier().verify(body);
      return await handleVerifiedEnvelope(JSON.parse(body) as AlexaEnvelope, env);
    } catch (error) {
      console.error(JSON.stringify({
        event: "alexa_verification",
        outcome: "rejected",
        code: error instanceof Error ? error.name : "unknown",
        detail: error instanceof Error ? error.message : "unknown",
      }));
      return new Response("Invalid Alexa request", { status: 400 });
    }
  },
} satisfies ExportedHandler<Env>;
