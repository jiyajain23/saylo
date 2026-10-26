"""Validate the configured Live model/setup without sending text or audio.

Run from backend: python check_live.py
This opens and closes one upstream session; it never sends a generation request.
Errors are reduced to a code so credential-bearing URLs cannot reach output.
"""
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from services.gemini import GeminiLiveSession, _live_model


async def main() -> int:
    service = Path(__file__).resolve().parent
    load_dotenv(service / ".env")
    load_dotenv(service.parent / ".env")
    session = GeminiLiveSession("INTERVIEW", None, lambda text: None)
    try:
        await session.start()
        print(f"Live setup accepted for {_live_model()}; no text/audio sent.")
        return 0
    except Exception as exc:
        print(f"Live setup failed ({type(exc).__name__}); check credentials, model access, and network.")
        return 1
    finally:
        await session.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
