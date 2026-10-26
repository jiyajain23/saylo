"""One exact origin allowlist shared by HTTP and WebSocket entry points."""
import os


def allowed_origins():
    return [value.strip().rstrip("/") for value in
            os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if value.strip() and value.strip() != "*"]
