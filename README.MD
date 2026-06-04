# SpeakEZ (MVP)

Context-aware mock interview practice with lightweight live nudges + post-session insights.

## What’s implemented

- **Live simulation (Interview)**: Web UI sends your answers over a WebSocket; backend responds with an interviewer follow-up.
  - Uses **Gemini** if `GEMINI_API_KEY` is set; otherwise uses a safe fallback interviewer.
- **Context injection**: Optional context text is structured and injected into interviewer prompts + analysis relevance scoring.
- **Real-time nudges**: Basic filler-word + pace nudges (non-intrusive).
- **Analysis pipeline**: Python service computes speech metrics, language quality signals, purpose alignment, and a confidence score.
- **Progress tracking**: Sessions + transcripts + analysis results are persisted in a DB (SQLite for MVP dev; easily upgradable to Postgres).

## Quickstart (Docker)

1) Create `.env` in repo root:

- `GEMINI_API_KEY=` (optional, for better interviewer behavior)
- `OPENAI_API_KEY=` (optional, not required for MVP)

2) Run:

```bash
docker compose up --build
```

3) Open the API:

- `http://localhost:5000/health`

4) Start the web app (local dev):

```bash
cd apps/web
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Local dev (no Docker)

- Set `DATABASE_URL=file:./dev.db` (recommended for quickstart on Windows).
- Start analysis service:

```bash
cd services/analysis-service
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- Start API:

```bash
cd apps/api
npm install
npx prisma generate
npx prisma db push
npm run dev
```

- Start web:

```bash
cd apps/web
npm install
npm run dev
```

