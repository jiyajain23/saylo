# SpeakEZ (MVP)

Context-aware mock interview practice with lightweight live nudges + post-session insights.

```

Three terminals, one per service:

## Terminal 1 — Analysis Service (port 8000)
```bash
cd services/analysis-service
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Terminal 2 — Backend API (port 5000)
```bash
cd backend
pip install -r requirements.txt
# First time only — create the DB tables:
python -c "import asyncio; from db import init_db; asyncio.run(init_db())"
uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```
Make sure [`backend/.env`](file:///c:/Users/jiya%20jain/Documents/GitHub/speakEz-JJ/backend/.env) has your `GEMINI_API_KEY` filled in.

## Terminal 3 — Frontend (port 3000)
```bash
cd frontend
npm install
npm run dev
```

