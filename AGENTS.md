# AGENTS.md

This repository is a small home operations dashboard called Command Center.
It combines a Python FastAPI backend with a Vite React frontend and Docker Compose deployment.

## Key areas

- `backend/`
  - `backend/app.py` is the main FastAPI service.
  - It exposes REST endpoints for status, chat/AI analysis, Minecraft controls, alerts, and briefings.
  - `backend/services/minecraft_service.py` handles Minecraft RCON and Docker container inspection.
  - `backend/requirements.txt` lists Python dependencies.

- `frontend-react/`
  - Current UI source lives here.
  - Use `npm run dev`, `npm run build`, and `npm run preview` in `frontend-react`.
  - The production frontend is built with Vite and served by `frontend-react/Dockerfile` + `frontend-react/nginx.conf`.

- `frontend/`
  - Contains legacy/static frontend assets and should be treated as older output, not the active React source.

- `config/projects.json`
  - Holds project metadata consumed by the backend.

- `docker-compose.yml`
  - Defines `command-center` and `command-center-ui` services.
  - Backend uses `backend/Dockerfile`, frontend uses `frontend-react/Dockerfile`.

## Build and run

Preferred local workflow:
- `docker compose up --build`

Frontend-only:
- `cd frontend-react`
- `npm install`
- `npm run dev`

Backend development:
- Backend runs with `uvicorn app:app --host 0.0.0.0 --port 8787` inside `backend/`.

## Chat / AI integration

- `backend/services/openai_service.py` owns the OpenAI Python client; `backend/services/cloud_response_service.py` is the single guarded live-response path shared by the API and Vera conversations.
- Chat-style features are implemented in `/api/ask`, `/api/analyze`, and `/api/briefing`.
- Relevant environment variables:
  - `OPENAI_API_KEY` (optional; when blank or absent, cloud requests are disabled)
  - `OPENAI_MODEL` (default `gpt-4.1-mini`)
  - `VERA_LOCAL_MODEL` (default `qwen3:4b-instruct`; use a non-thinking model for user-visible conversations)
  - `VERA_LOCAL_MAX_OUTPUT_TOKENS` (default `512`, bounded from `128` to `2048`)
  - `DISCORD_WEBHOOK`
- `GET /api/openai/status` reports whether OpenAI is configured without exposing the key or making a billable API request.
- Budget simulation is owned by `backend/services/budget_service.py`; `/api/budget/status`, `/api/budget/simulate`, and `/api/budget/ledger` never make OpenAI requests.
- Budget limits and pricing estimates are configured with `VERA_BUDGET_*` and `VERA_OPENAI_*_COST_PER_MILLION` environment variables.
- Domain model, risk, approval, and spend policies are seeded by migration `005_domain_policies.sql` and evaluated by the existing `policy_service.py` in simulation mode.
- Authenticated policy inspection is available through `/api/vera/policies/domains` and `/api/vera/policies/evaluate`.
- Local-first routing simulation is owned by `backend/services/router_service.py` and records decisions without executing either local or cloud models.
- Authenticated router inspection is available through `/api/vera/router/status`, `/api/vera/router/simulate`, and `/api/vera/router/decisions`.
- The authenticated Decision Journal at `/api/vera/journal` merges route, control, simulation, and budget metadata without exposing prompts or conversation content.
- Cloud API access defaults off and is persisted through `cloud_routing_state`; authenticated CSRF-protected controls live at `/api/vera/router/cloud/*`.
- Live `/api/analyze` and `/api/briefing` calls require authentication, the cloud toggle, domain policy approval, and an atomic budget reservation.
- Vera conversations always try Ollama first. Only a genuine local failure may use the guarded cloud path, and only while cloud routing is enabled under the dedicated `conversation` domain policy.
- The Discord worker receives the server-side `.env` so it can use the same OpenAI and budget configuration; never expose those values in messages, APIs, or logs.
- Live OpenAI requests use `max_retries=0`; uncertain failures retain the worst-case reservation until reviewed rather than returning potentially spent budget.
- Preserve existing prompt structure and fallback messaging when updating AI behaviors.

## Agent guidance

- When asked to change UI behavior, work in `frontend-react/src`.
- When asked to change backend logic or add endpoints, edit `backend/app.py` and use `backend/services/` for service-specific helpers.
- When asked to adjust deployment or environment configuration, update `docker-compose.yml`, `backend/Dockerfile`, or `frontend-react/Dockerfile`.
- Avoid modifying `frontend/` unless explicitly maintaining the legacy/static assets.

## Notes for AI agents

- The backend executes host-level system commands (`lsblk`, `ip`, `ping`, `curl`) and inspects Docker containers, so changes may depend on the runtime environment.
- The current backend root route returns simple HTML and does not serve the React app itself.
- The repo does not have existing AI customization files, so this `AGENTS.md` is the first canonical guidance document.
