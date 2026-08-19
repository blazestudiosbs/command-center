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

- `backend/app.py` uses the OpenAI Python client via `OpenAI(api_key=..., timeout=..., max_retries=1)`.
- Chat-style features are implemented in `/api/ask`, `/api/analyze`, and `/api/briefing`.
- Relevant environment variables:
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL` (default `gpt-4.1-mini`)
  - `DISCORD_WEBHOOK`
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
