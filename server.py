"""
Citera Practice — Waitlist backend.

Stores incoming waitlist entries in a local SQLite file (citera.db).
Serves the static HTML pages from the same directory as this file.

Run:
    pip install fastapi uvicorn[standard]
    python server.py

Then open http://localhost:8000/ in your browser.
"""

from __future__ import annotations

import datetime as dt
import random
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "citera.db"

ALLOWED_ROLES = {"student", "postgrad", "researcher", "lecturer", "other"}
ALLOWED_DOMAINS = {
    "natural", "technical", "social", "medical", "interdisciplinary",
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS waitlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   TEXT    NOT NULL UNIQUE,
                email       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                role        TEXT,
                domain      TEXT,
                ip_address  TEXT,
                user_agent  TEXT,
                created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_waitlist_email ON waitlist(email)"
        )
        conn.commit()


def generate_ticket_id() -> str:
    """Generate a unique ticket ID like CT-2026-1042."""
    year = dt.datetime.now().year
    # Loop until we find a unique ticket id (collisions are extremely rare).
    for _ in range(20):
        candidate = f"CT-{year}-{random.randint(1000, 9999)}"
        with get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM waitlist WHERE ticket_id = ?", (candidate,)
            ).fetchone()
        if row is None:
            return candidate
    raise RuntimeError("Could not allocate a unique ticket id.")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WaitlistEntry(BaseModel):
    email: EmailStr
    role: Optional[str] = Field(default=None, max_length=32)
    domain: Optional[str] = Field(default=None, max_length=32)


class WaitlistResponse(BaseModel):
    ok: bool
    ticket_id: str
    email: str
    created_date: str  # DD.MM.YYYY for the receipt UI


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# Initialise the database eagerly. This way the schema is in place regardless
# of how the app is started (uvicorn, gunicorn, TestClient, ASGI workers).
init_db()

app = FastAPI(
    title="Citera Practice — Waitlist",
    description="Lightweight backend for the Citera waitlist.",
    version="0.1.0",
)

# Allow the frontend pages to call us when served from a different origin
# (e.g. opened directly via file:// or hosted on a different domain).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/waitlist", response_model=WaitlistResponse)
async def join_waitlist(entry: WaitlistEntry, request: Request):
    """Register a new email in the waitlist."""

    # Normalise / validate optional fields against the allowed values so that
    # clients can't dump arbitrary strings into the database.
    role = entry.role if entry.role in ALLOWED_ROLES else None
    domain = entry.domain if entry.domain in ALLOWED_DOMAINS else None

    email = entry.email.lower().strip()
    ticket_id = generate_ticket_id()
    now = dt.datetime.utcnow()
    created_date = now.strftime("%d.%m.%Y")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO waitlist
                    (ticket_id, email, role, domain, ip_address, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, email, role, domain, ip, ua, now.isoformat()),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        # Likely a duplicate email — return 409 so the client can show a nice
        # message rather than a generic error.
        raise HTTPException(
            status_code=409,
            detail="Этот адрес уже зарегистрирован в листе ожидания.",
        )

    return WaitlistResponse(
        ok=True,
        ticket_id=ticket_id,
        email=email,
        created_date=created_date,
    )


@app.get("/api/waitlist/stats")
async def stats():
    """Public head-count of the waitlist (no PII exposed)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM waitlist"
        ).fetchone()
    return {"count": row["n"]}


@app.get("/api/waitlist/list")
async def list_entries(token: str = "", limit: int = 100):
    """
    Admin-only listing of entries.

    Set `CITERA_ADMIN_TOKEN` in the environment and pass it as `?token=...`
    to view all entries. Defaults to "" which means the endpoint is locked.
    """
    import os
    expected = os.environ.get("CITERA_ADMIN_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT ticket_id, email, role, domain, created_at
            FROM waitlist
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 1000)),),
        ).fetchall()
    return {"entries": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

# Serve the two HTML files directly from the project directory so that the
# whole thing works as one process: `python server.py` and you're done.

@app.get("/")
async def root() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/index.html")
async def index_html() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/waitlist.html")
async def waitlist_html() -> FileResponse:
    return FileResponse(BASE_DIR / "waitlist.html")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
